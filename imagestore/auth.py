import sha
import md5
import os
import re
import time
import struct
import binascii

import quixote
from quixote.errors import AccessError

import imagestore

# Store persistently if nonce needs to survive over server restarts.
# Alternatively, change regularly to force digest renegotations.  We
# return the 'stale' flag in these cases, so the browser should just
# do it without pestering the user.
_private = os.urandom(20)

_nonce_random = 12
_sha_len = 20
_pack_hash = 'l%ds%ds' % (_nonce_random, len(_private))
_pack_nonce = 'l%ds%ds' % (_nonce_random, _sha_len)

def _hash_nonce(e, r):
    return sha.sha(struct.pack(_pack_hash, e, r, _private)).digest()

def makenonce(expire=0):
    """Generate a unique nonce.  If expire is non-zero, it specifies
    the number of seconds the nonce should be valid for."""
    def enc(s):
        """base64 ends with \n, which is just confusing"""
        s=s.encode('base64')
        while s.endswith('\n'):
            s = s[:-1]
        return s

    e = 0
    if expire != 0:
        e = expire + int(time.time())

    r = os.urandom(_nonce_random)
    s = _hash_nonce(e, r)
    return enc(struct.pack(_pack_nonce, e, r, s))

def checknonce(n):
    """Check that a string is a nonce we created,
    and that it hasn't expired."""
    try:
        e, r, s = struct.unpack(_pack_nonce, n.decode('base64'))
    except struct.error:
        return False
    except binascii.Error:
        return False
    
    if e != 0 and int(time.time()) > e:
        return False
    
    return _hash_nonce(e, r) == s

assert checknonce(makenonce())

class UnauthorizedError(AccessError):
    """The request requires user authentication.
    
    This subclass of AccessError sends a 401 instead of a 403,
    hinting that the client should try again with authentication.
    """
    status_code = 401
    title = "Unauthorized"
    description = "You are not authorized to access this resource."

    def __init__(self, realm='Protected', scheme='digest',
                 public_msg=None, private_msg=None, stale=None):
        self.realm = realm
        self.scheme = scheme
        self.stale = stale
        AccessError.__init__(self, public_msg, private_msg)

    def format(self):
        response = quixote.get_request().response
        if self.scheme == 'basic':
            dict = { 'realm': self.realm }
        elif self.scheme == 'digest':
            dict = {
                'realm': self.realm,
                'nonce': makenonce(),
                'uri': imagestore.path(),
                'algorithm': 'MD5',
                'qop': 'auth',
                'stale': self.stale and 'true' or 'false'
                }

        auth = '%s %s' % (self.scheme.capitalize(),
                          ', '.join([ '%s="%s"' % (k, v.encode('string-escape'))
                                      for k,v in dict.items() ]))

        #print 'auth=%s' % auth
        response.set_header('WWW-Authenticate', auth)

        return AccessError.format(self)


re_ident=re.compile('[a-z_][a-z0-9_]+', re.I)
re_string=re.compile(r'"((?:[^"\\]|\\[^0-9]|\\[0-9]{1,3})*)"')
re_number=re.compile('[0-9][0-9a-f]*')       # hex number ambigious with ident

_tokens = {
    (lambda s: re_ident.match(s)):  ('ident',                   # type
                                     lambda x: x.group(0),      # value
                                     lambda x: x.end(0)),       # chomp
    (lambda s: re_string.match(s)): ('string',
                                     lambda x: x.group(1).decode('string-escape'),
                                     lambda x: x.end(0)),
    (lambda s: re_number.match(s)): ('number',
                                     lambda x: x.group(0),
                                     lambda x: x.end(0)),
    (lambda s: s.startswith(',')):  (',', lambda x: ',', lambda x: 1),
    (lambda s: s.startswith('=')):  ('=', lambda x: '=', lambda x: 1)
    }

def _gettok(s):
    """Fetch the next token from the string, and return a
    (toktype, tokval, remains) triple.  Returns None if the next
    part of the string isn't tokenizable."""
    
    s = s.lstrip()                      # skip whitespace
    ret = None
    chomp = 0

    for f in _tokens:
        m = f(s)
        if m:
            type,strfn,chompfn = _tokens[f]
            chomp = chompfn(m)
            value = strfn(m)
            ret = (type, value, s[chomp:])
            break
        
    return ret

class TokException(Exception):
    pass

def _next(str):
    p = _gettok(str)
    if p:
        return p[0]
    
def _expect(tok, str):
    """Expect one of a set of tokens at the start of the string.
    Returns a (remains,value) pair if present; otherwise it raises
    TokException."""
    t = _gettok(str)
    if t is None or t[0] not in tok:
        raise TokException
    return (t[2], t[1])

def _parse_value(str, dict):
    """Parse the next name=value in the string, and adds it to the
    dictionary.  If '=value' is missing, then it adds 'name: None'
    to the dictionary.  Returns the remains of the string, with any
    trailing ',' consumed."""
    str,name = _expect(('ident',), str)

    value=None

    if _next(str) == '=':
        str,x = _expect(('=',), str)

        str,value = _expect(('string', 'number', 'ident'), str)

    if _next(str) == ',':
        str = str[1:]
    dict[name] = value
    return str

def parse_auth_header(header):
    """Parse an Authorization header and return the scheme
    and a dictionary of parameters for that scheme."""
    scheme,rest = header.split(None, 1)

    scheme = scheme.lower()
    dict = {}
    
    if scheme == 'basic':
        user,password = rest.decode('base64').split(':', 1)
        dict = { 'username': user, 'password': password }
    elif scheme == 'digest':
        dict = {}
        try:
            while rest:
                rest = _parse_value(rest, dict)
        except TokException:
            pass
    else:
        scheme=None
        dict=None

    return (scheme, dict)

def getpass(username):
    from sqlobject import SQLObjectNotFound
    import imagestore.db as db

    try:
        user=db.User.byUsername(username)
        return user.password
    except SQLObjectNotFound:
        raise KeyError

#def getpass(x):
#    return { 'foo': 'bar' }[x]
    
class testauth:
    def __init__(self):
        self.scheme='digest'

        self.schemes = { 'digest':      self.check_digest,
                         'basic':       self.check_basic }

    _q_exports = []

    def _q_index(self, request):
        return 'Whoo, OK!'

    def check_basic(self, dict):
        return getpass(dict['username']) == dict['password']

    def check_digest(self, dict):
        #print dict

        def H(x):
            return md5.md5(x).digest().encode('hex')

        if 'algorithm' in dict and dict['algorithm'].lower() == 'sha':
            def H(x):
                return sha.sha(x).digest().encode('hex')

        def KD(secret, data):
            #print 'KD(%s, %s)' % (secret, data)
            return H('%s:%s' % (secret, data))

        def A1(user, realm, password):
            #print 'A1(%s, %s, %s)' % (user, realm, password)
            return '%s:%s:%s' % (user, realm, password)

        def A2(method, uri):
            #print 'A2(%s, %s)' % (method, uri)
            return '%s:%s' % (method, uri)

        request = quixote.get_request()

        pieces = [ dict['nonce'] ]

        if 'qop' in dict:
            pieces += [ dict['nc'],
                        dict['cnonce'],
                        dict['qop'] ]

        pieces += [ H(A2(request.get_method(), dict['uri'])) ]

        digest = KD(H(A1(dict['username'],
                         dict['realm'],
                         getpass(dict['username']))),
                    ':'.join(pieces))
        
        #print 'digest=%s response=%s' % (digest, dict['response'])

        if digest != dict['response']:
            return False
        
        if not checknonce(dict['nonce']):
            # stale nonce; the client knows the username/password,
            # but passed a bad nonce
            raise UnauthorizedError(scheme=self.scheme, stale=True)
        
        return digest == dict['response']

    def _q_access(self, request):
        #ha = request.get_environ('HTTP_AUTHORIZATION', None)
        ha = request.get_header('Authorization')

        #print ha
        
        if ha is not None:
            scheme,dict = parse_auth_header(ha)

            try:
                if scheme == self.scheme and self.schemes[scheme](dict):
                    return
            except KeyError:
                pass

        raise UnauthorizedError(scheme=self.scheme)
