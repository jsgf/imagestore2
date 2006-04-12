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

_auth_cookie = 'IS-authorization'

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
        e = int(expire)

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
        ret =(0, { 'realm': realm })
    if scheme == 'digest':
        expire = 0
        life=config.get('auth', 'nonce_life')
        if life != 'unlimited' and int(life) != 0:
            expire = int(time.time()) + int(life)
            
        ret = (expire, {
            'realm': realm,
            'nonce': makenonce(expire),
            'uri': imagestore.path(),
            'algorithm': 'MD5',
            'qop': 'auth',
            'stale': stale and 'true' or 'false'
            })

    return ret
    
def _format_auth(scheme, dict):
    return '%s %s' % (scheme.capitalize(),
                      ', '.join([ '%s="%s"' % (k, v.encode('string-escape'))
                                  for k,v in dict.items() ]))

class UnauthorizedError(AccessError):
    """The request requires user authentication.
    
    This subclass of AccessError sends a 401 instead of a 403,
    hinting that the client should try again with authentication.
    """
    status_code = 401
    title = "Unauthorized"
    description = "You are not authorized to access this resource."

    def __init__(self, realm, scheme='digest',
                 public_msg=None, private_msg=None, stale=False):
        self.realm = realm
        self.scheme = scheme
        self.stale = stale
        AccessError.__init__(self, public_msg, private_msg)

    def format(self):
        response = quixote.get_response()
        (exp,dict) = _auth_challenge(self.scheme, self.realm, self.stale)

        auth = _format_auth(self.scheme, dict)

        #print 'auth=%s' % auth
        response.set_header('WWW-Authenticate', auth)

        return AccessError.format(self)


re_nameval = re.compile(r'\s*([a-z_][a-z0-9_-]*)'       # match identifier, with leading whitespace
                        r'(?:\s*=\s*('                  # start optional ' = ...' block
                            r'[a-z_][a-z0-9_-]*|'           # ident
                            r'[0-9a-f]+|'                   # hex number
                            r'"((?:[^"\\]|'                 # string - normal chars
                              r'\\[^0-7x]|'                 # \" quoting
                              r'\\[0-7]{1,3}'               # \NNN octal quoting
                              r'\\x[0-9a-f]{1,2}'           # \xNN hex quoting
                            r')*)"'
                          r')'
                        r')?'                           # end ' = ... ' block
                        r'(?:\s*,)?'                    # match trailing ' , '
                        r'\s*(.*)$',                    # match rest of string
                        re.I)

class TokException(Exception):
    pass

def _parse_value(str, dict):
    """Parse the next name=value in the string, and adds it to the
    dictionary.  If '=value' is missing, then it adds 'name: None'
    to the dictionary.  Returns the remains of the string, with any
    trailing ',' consumed."""

    m = re_nameval.match(str)

    #print 'str=\"%s\" m=%r' % (str, m)
    
    if not m:
        raise TokException

    #print 'm.group="%s" "%s" "%s" "%s"' % (m.group(1), m.group(2), m.group(3), m.group(4))

    name = m.group(1)
    value = (m.group(3) or m.group(2))
    if value is not None:
        value = value.decode('string-escape')
    str = m.group(4)

    dict[name] = value
    return str

def parse_auth_header(header):
    """Parse an Authorization header and return the scheme
    and a dictionary of parameters for that scheme."""
    try:
        scheme,rest = header.split(None, 1)
    except ValueError:
        return (None, None)
    
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

def _check_basic(dict, method):
    return getpass(dict['username']) == dict['password']

def _check_digest(dict, method):
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

    pieces += [ H(A2(method, dict['uri'])) ]

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
        # XXX need to make sure username is actually valid before returning stale=True
        raise UnauthorizedError(realm=_realm, scheme=_schemes_allowed[0], stale=False)

    return digest == dict['response']


_schemes = { 'digest':      _check_digest,
             'basic':       _check_basic }

def _do_authenticate(auth_hdr, method):
    user = None

    response = quixote.get_response()
    session = quixote.get_session()

    try:
        if auth_hdr is None:
            return None

        scheme,dict = parse_auth_header(auth_hdr)

        if scheme not in _schemes_allowed:
            return None

        method = dict.get('method', method)
        dict['method'] = method

        try:
            if _schemes[scheme](dict, method):
                username = dict.get('username')
                user = db.User.byUsername(username)
        except KeyError:
            pass
        except SQLObjectNotFound:
            pass

        # If we got an auth string but login failed, then delay a bit
        # to prevent being pounded with bad requests.
        if user is None:
            time.sleep(2)
    finally:
        if user is None:
            response.expire_cookie(_auth_cookie, path=imagestore.path())
        else:
            response.set_cookie(_auth_cookie, _format_auth('digest', dict), path=imagestore.path())

    return user

def login_user(quiet=False):
    """ Return the currently logged-in user.  If the user has
    logged in with a session cookie, use that, otherwise use
    HTTP authentication.  If quiet is true, then this will
    not force an authentication request. """

    request = quixote.get_request()

    try:
        ret = request._cached_user
        if ret is None and not quiet:
            del request._cached_user
            raise UnauthorizedError(realm=_realm, scheme=_schemes_allowed[0])            
    except AttributeError:
        pass
    
    request._cached_user = None

    # Use the official Authorization header last, since it seems to
    # have made-up stuff in it sometimes.
    auth_hdr = request.get_header('x-authorization') or \
               request.get_cookie(_auth_cookie) or \
               request.get_header('authorization')

    ret = None
    try:
        ret = _do_authenticate(auth_hdr, request.get_method())
    except UnauthorizedError, x:
        if not quiet:
            raise x
        
    if ret is not None:
        request._cached_user = ret
        return ret

    if not quiet:
        #raise 'oops'
        raise UnauthorizedError(realm=_realm, scheme=_schemes_allowed[0])

    return None

_q_exports = [ 'challenge', 'user' ]

def challenge(request):
    """ Generate a HTTP Digest authentication challenge, along with an expiry time. """
    request = quixote.get_request()
    response = quixote.get_response()

    if request.get_method() != 'GET':
        raise http.MethodError(['GET'])

    http.json_response()

    scheme = _schemes_allowed[0]
    (expire,dict) = _auth_challenge(scheme, _realm)
    
    auth = '%s %s' % (scheme.capitalize(),
                      ', '.join([ '%s="%s"' % (k, v.encode('string-escape'))
                                  for k,v in dict.items() ]))

    # XXX use expire header instead/as well?
    return json.write({ 'expire': expire,
                        'challenge': auth })

def user(request):
    """ Return the currently authenticated user, if any. """

    quiet = True
    if request.form.get('force'):
        quiet = False

    u = login_user(quiet=quiet)

    ret = None
    if u is not None:
        ret = { 'id': u.id, 'username': u.username, 'fullname': u.fullname }
        
    http.json_response()
    return json.write(ret)
