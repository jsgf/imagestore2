import quixote 
from quixote.errors import AccessError
from base64 import b64decode

class UnauthorizedError(AccessError):
    """The request requires user authentication.
    
    This subclass of AccessError sends a 401 instead of a 403,
    hinting that the client should try again with authentication.
    """
    status_code = 401
    title = "Unauthorized"
    description = "You are not authorized to access this resource."

    def __init__(self, realm='Protected', public_msg=None, private_msg=None):
        self.realm = realm
        AccessError.__init__(self, public_msg, private_msg)

    def format(self):
        quixote.get_request().response.set_header('WWW-Authenticate',
                                                  'Basic realm="%s"' % self.realm)
        return AccessError.format(self)

class testauth:
    _q_exports = []

    def _q_index(self, request):
        return 'Whoo, OK!'

    def _q_access(self, request):
        ha = request.get_environ('HTTP_AUTHORIZATION', None)

        if ha:
            type,string = ha.split()
            login,passwd = b64decode(string).split(':')

            if login == 'foo' and passwd == 'bar':
                return

        raise UnauthorizedError
