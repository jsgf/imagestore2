import sha
import md5
import os
import re
import time
import struct
import binascii

import json

from sqlobject import SQLObjectNotFound

import quixote
from quixote.errors import AccessError, QueryError

import imagestore
import imagestore.db as db
import imagestore.config as config
import imagestore.http as http

# Store persistently if nonce needs to survive over server restarts.
# Alternatively, change regularly to force digest renegotations.  We
# return the 'stale' flag in these cases, so the browser should just
# do it without pestering the user.
_private = os.urandom(20)

_nonce_random = 12
_sha_len = 20
_pack_hash = '>l%ds%ds' % (_nonce_random, len(_private))
_pack_nonce = '>l%ds%ds' % (_nonce_random, _sha_len)

_schemes_allowed = config.get('auth', 'schemes').split(', ')
_realm = config.get('auth', 'realm')

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
    if expire != 0 and expire != 'unlimited':
        e = int(expire) + int(time.time())

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

def _auth_challenge(scheme, realm, stale=False):
    if scheme == 'basic':
        return { 'realm': realm }
    if scheme == 'digest':
        return {
            'realm': realm,
            'nonce': makenonce(config.get('auth', 'nonce_life')),
            'uri': imagestore.path(),
            'algorithm': 'MD5',
            'qop': 'auth',
            'stale': stale and 'true' or 'false'
            }
    
class UnauthorizedError(AccessError):
    """The request requires user authentication.
    
    This subclass of AccessError sends a 401 instead of a 403,
    hinting that the client should try again with authentication.
    """
    status_code = 401
    title = "Unauthorized"
    description = "You are not authorized to access this resource."

    def __init__(self, realm, scheme='digest',
                 public_msg=None, private_msg=None, stale=None):
        self.realm = realm
        self.scheme = scheme
        self.stale = stale
        AccessError.__init__(self, public_msg, private_msg)

    def format(self):
        response = quixote.get_response()
        dict = _auth_challenge(self.scheme, self.realm, self.stale)

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

def _check_basic(dict):
    return getpass(dict['username']) == dict['password']

def _check_digest(dict):
    #print dict

    H = lambda x: md5.md5(x).digest().encode('hex')

    if 'algorithm' in dict and dict['algorithm'].lower() == 'sha':
        H = lambda x: sha.sha(x).digest().encode('hex')

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
        raise UnauthorizedError(realm=_realm, scheme=_schemes_allowed[0], stale=True)

    return digest == dict['response']


_schemes = { 'digest':      _check_digest,
             'basic':       _check_basic }

def do_authenticate(scheme, dict):
    response = quixote.get_response()
    session = quixote.get_session()

    username = dict.get('username')

    try:
        user = db.User.byUsername(username)
    except SQLObjectNotFound:
        return None

    response.set_cookie('imagestore_auth', json.write((scheme,dict)),
                        path=imagestore.path())

    session.setuser(user.id)
    return user
    

def login_user(quiet=False):
    """ Return the currently logged-in user.  If the user has
    logged in with a session cookie, use that, otherwise use
    HTTP authentication.  If quiet is true, then this will
    not force an authentication request. """

    session = quixote.get_session()
    user = session.getuser()
    if user is not None:
        return user

    request = quixote.get_request()

    auth_hdr = request.get_header('authorization')

    if auth_hdr is not None:
        scheme,dict = parse_auth_header(auth_hdr)

        try:
            if scheme in _schemes_allowed and _schemes[scheme](dict):
                return do_authenticate(scheme, dict)
        except KeyError:
            pass
        except SQLObjectNotFound:
            pass

    if not quiet:
        #raise 'oops'
        raise UnauthorizedError(realm=_realm, scheme=_schemes_allowed[0])

    return None

_q_exports = [ 'nonce', 'authenticate' ]

def nonce(request):
    response = quixote.get_response()
    response.set_content_type('text/plain')
    return makenonce(config.get('auth', 'nonce_life'))

def authenticate(request):
    request = quixote.get_request()
    response = quixote.get_response()

    if request.get_method() == 'GET':
        d = _auth_challenge(_schemes_allowed[0], _realm)
        return json.write((_schemes_allowed[0], d))
    elif request.get_method() != 'POST':
        raise http.MethodError(['GET', 'POST'])

    scheme = request.form.get('scheme')

    if scheme not in _schemes or \
           scheme not in _schemes_allowed:
        raise QueryError('bad scheme')

    if do_authenticate(scheme, request.form) is None:
        raise QueryError('authentication failed')

    response.set_status(204)            # no content
    return ''
