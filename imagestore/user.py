# User management

from sqlobject import SQLObjectNotFound

from quixote.errors import AccessError, TraversalError

from pages import pre, post, menupane, error, prefix
from user_page import login_form, user_details as user_details_ptl
from db import User

_q_exports = [ 'login', 'logout' ]            

def login(request):
    ret = [ pre(request, 'Imagestore Login') ]

    ret.append('<h1>Imagestore Login</h1>')

    session = request.session

    if request.form:
        username = request.form.get('username')
        password = request.form.get('password')
        referer = request.form.get('referer')

        failed = False
        try:
            user = User.byUsername(username)

            if False:
                print 'username=%s user.username=%s' % (username, user.username)
                print 'password="%s" user.password="%s"' % (password, user.password)

            if password == '':
                password = None

            if user.password != password:
                failed = True
        except SQLObjectNotFound, x:
            failed = True

        if failed:
            ret.append(error(request, 'User unknown or password incorrect', 'Please try again.'))
            ret.append(login_form(request, username=username))
        else:
            ret.append('<p>Hi, %s, you\'ve logged in' % user.fullname)
            session.user = user.id
            if referer is not None and referer != '':
                request.redirect(referer)
    else:
        ret.append(login_form(request, referer=request.get_environ('HTTP_REFERER')))

    ret.append(post())

    # Put this here so it accurately reflects the logged-in state
    ret.append(menupane(request))
    
    return ''.join([ str(r) for r in ret ])

def logout(request):
    request.session.user = None

    request.redirect(request.get_environ('HTTP_REFERER'))

    return 'logged out'

def _q_lookup(request, component):
    try:
        u = User.byUsername(component)
    except SQLObjectNotFound, x:
        raise TraversalError('User %s unknown' % component)

    return UserUI(u)

def _q_index(request):
    session = request.session

    user = session.getuser()

    if user is None:
        request.redirect('%s/user/login' % prefix)
    else:
        request.redirect('%s/user/%s/' % (prefix, user.username))

    return ''


class UserUI:
    _q_exports = []
    
    def __init__(self, u):
        self.user = u

    def _q_index(self, request):
        u = request.session.getuser()

        if u is None:
            request.redirect('%s/user/' % prefix)
            return ''

        if not u.mayAdmin and u != self.user:
            raise AccessError

        return self.user_details(request)

    user_details = user_details_ptl
        
