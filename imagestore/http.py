import quixote
from quixote.errors import PublishError

class MethodError(PublishError):
    status_code = 405
    title = 'Method Not Allowed'
    description = 'Method not allowed on this object'

    def __init__(self, allowed, public_msg=None, private_msg=None):
        PublishError.__init__(self, public_msg, private_msg)
        self.allowed = allowed

    def format(self):
        response = quixote.get_response()
        response.set_header('Allowed', ', '.join(self.allowed))

        return PublishError.format(self)
        

class ForbiddenError(PublishError):
    status_code = 403
    title = 'Forbidden'
    description = 'Action forbidden on this object'

