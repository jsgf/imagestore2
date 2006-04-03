import re

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

def preferred_type():
    request = quixote.get_request()
    accept = request.get_header('Accept')

    accepts = accept.split(',');
    best = (None,0)
    for a in accepts:
        q=1
        type=a
        optidx = a.find(';')
        if optidx != -1:
            type = a[:optidx]
            m=re.search(';q=([0-9.]+)', a)
            if m is not None:
                q = float(m.group(1))
        if q > best[1]:
            best = (type, q)
    return best

_re_json = re.compile('(text|application)/(x-)?(json|javascript)')

def want_json():
    (pref,q) = preferred_type()

    return _re_json.match(pref) is not None
        
def json_response():
    """ Set up response headers to indicate json payload """
    response = quixote.get_response()
    response.set_content_type('text/json', 'utf-8')
