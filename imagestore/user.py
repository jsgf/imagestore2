# User management

from sqlobject import SQLObjectNotFound
from sqlobject.sqlbuilder import AND, NOT, IN

from quixote.errors import AccessError, TraversalError, QueryError
from quixote.html import htmltext, TemplateIO
import quixote.form2 as form2

from pages import pre, post, menupane, error, prefix
from user_page import login_form, user_details as user_details_ptl
from db import User, getColByName, setColByName, Picture
from dbfilters import userFilter

from form import extract_form_data    

H=htmltext

_q_exports = [ 'login', 'logout', 'editmode', 'edituser' ]

perms = [ ('mayAdmin', 'May administer'),
          ('mayViewall', 'May view everything'),
          ('mayUpload', 'May upload pictures'),
          ('mayComment', 'May comment'),
          ('mayCreateCat', 'May create collections') ]

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
    u = None
    try:
        u = User.byUsername(component)
        if 0 and not u.enabled:
            u = None
    except SQLObjectNotFound, x:
        pass

    if u is None:
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


class UserWidget(form2.CompositeWidget):
    """Manage the form<->user mapping.

    This widget assumes its being presented in a tables of other users.  It manages the
    mapping between the User database object, and the fields relating to this user in the
    form.

    The special hidden input 'skip' is for marking users which were not changed in stage 1
    of the user form input, and therefore should not be presented in later stages, and
    not considered changed.
    """
    def __init__(self, name, user, **kwargs):
        form2.CompositeWidget.__init__(self, name, **kwargs)
        self.user = user

        self.add(form2.HiddenWidget, name='skip', title=None, value=0)
        self.add(form2.StringWidget, 'username', user.username, title='User name')
        self.add(form2.StringWidget, 'fullname', user.fullname, title='Full name')
        self.add(form2.StringWidget, 'email', user.email, title='Email')
        for (p, desc) in perms:
            self.add(form2.CheckboxWidget, 'perm.'+p, getColByName(user, p), title=p[3:], hint=desc)
        self.add(form2.CheckboxWidget, 'delete', False, 'Delete user')

        for w in self.get_widgets():
            w.render_br = False

    def column_titles(self):
        return [ 'ID' ] + [ w.get_title() for w in self.get_widgets() if w.get_title() ]
            
    def render_content(self):
        r = TemplateIO(html=True)
        for widget in self.get_widgets():
            if widget.get_title():
                classnames = '%s widget' % widget.__class__.__name__
                r += H('<td title="%s" class="%s">') % (widget.get_hint(), classnames)
                r += widget.render_content()
                r += widget.render_error(widget.get_error())
                r += H('</td>')
            else:
                r += widget.render_content()
        return r.getvalue()

    def render(self):
        if self._parsed and (self.get('skip') == 'skip' or not self.has_changed()):
            return self.get_widget('skip').render()

        r = TemplateIO(html=True)

        classnames = '%s widget' % self.__class__.__name__
        if self['delete']:
            classnames += ' deleted'
        r += H('<tr title="%s" class="%s">') % (self.get_hint(), classnames)
        r += H('<td>%d</td>') % self.user.id
        r += self.render_content()
        r += H('</tr>\n')
            
        return r.getvalue()

    def _parse(self, request):
        form2.CompositeWidget._parse(self, request)

        if self['delete']:
            count = Picture.select(Picture.q.ownerID == self.user.id).count()
            
            if count != 0 and self.get('replacement') == 0:
                raise form2.WidgetValueError('Must set replacement')

        if self['username'] != self.user.username and \
               User.select(User.q.username == self['username']).count() != 0:
            self.get_widget('username').set_error('New username must be unique')

    def has_changed(self):
        if self.get('skip') == 'skip':
            return False
        
        if self['delete']:
            return True

        for v in ['username', 'fullname', 'email']:
            if self[v] != getColByName(self.user, v):
                return True

        for (p, desc) in perms:
            if self['perm.'+p] != getColByName(self.user, p):
                return True

        return False

    def isdeleted(self):
        return self['delete']

    def add_replacement(self, replacementlist, npics):
        options = [ ( 0, 'Select user to inherit %d pics' % npics, 0 ) ]
        options += [ ( r.id, r.username, r.id ) for r in replacementlist ]
        self.add(form2.SingleSelectWidget, 'replacement', title='Replacement owner',
                 hint='Who should take ownership of the deleted users pictures?',
                 options = options)

    def skip_widget(self):
        self.get_widget('skip').value = 'skip'


    def commit(self):
        if not self.has_changed():
            return

        if self['delete']:
            self.user.enabled = False
            return

        for (p, desc) in perms:
            setColByName(self.user, p, self['perm.'+p])

        self.user.username = self['username']
        self.user.fullname = self['fullname']
        self.user.email = self['email']
        
class UserListWidget(form2.CompositeWidget):
    def __init__(self, name, **kwargs):
        form2.CompositeWidget.__init__(self, name, **kwargs)

    def adduser(self, user):
        name = '%s[%d]' % (self.name, user.id)
        self.add(UserWidget, name, user)

    def replace_deleted(self):
        deleted = []
        for w in self.get_widgets():
            if w.isdeleted():
                print 'deleting %d' % w.user.id
                deleted.append(w)

        if deleted:
            replacements = User.select(userFilter(NOT(IN(User.q.id, [ w.user.id for w in deleted ]))),
                                       orderBy=User.q.id)

            for w in deleted:
                pics = Picture.select(Picture.q.ownerID == w.user.id).count()
                if pics != 0:
                    w.add_replacement(replacements, pics)

    def render_content(self):
        r = TemplateIO(html=True)
        for widget in self.get_widgets():
            r += widget.render()
        return r.getvalue()

    def render(self):
        r = TemplateIO(html=True)
        classnames = '%s widget' % self.__class__.__name__
        r += H('<table class="%s">\n') % classnames
        r += H('<thead>\n<tr>')
        for t in self.get_widgets()[0].column_titles():
            r += H('<td>%s</td>') % t
        r += self.render_title(self.get_title())
        r += H('</tr>\n</thead>\n')
        r += H('<tbody>\n')
        r += self.render_content()
        r += H('</table>\n')

        return r.getvalue()

    def changed(self):
        for w in self.get_widgets():
            if w.has_changed():
                return True
        return False

    def commit(self):
        for w in self.get_widgets():
            if w.has_changed():
                w.commit()

def edituser(request):
    """Generate a table-form for doing mass edits of users.

    This allows an administrator to edit users' usernames, real names,
    email addresses and permissions, as well as "deleting" users (ie, disabling them).

    Form submission is in three phases:
     1. present form with current values
     2. when submitted, that presents the form with only the changed users, asking for
        confirmation
     3. commit the changes to the database
    """

    user = request.session.getuser()

    if user is None or not user.mayAdmin:
        raise AccessError("You may not change user information")

    form = form2.Form()
    form.add(UserListWidget, 'users')
    userlist = form.get_widget('users')

    form.add(form2.HiddenWidget, 'state', value=0)

    for u in User.select(userFilter(), orderBy=User.q.id):
        userlist.adduser(u)

    state = int(form['state'])
    
    if state == 0:
        form.get_widget('state').value = 1
        form.add_submit('update', 'Update users')
    elif state == 1 or (state == 2 and form.has_errors()):
        form.get_widget('state').value = 2
        form.add_submit('confirm', 'Confirm updates')
    elif state == 2:
        pass
    else:
        raise QueryError('Bad state %d' % state)

    if state > 0:
        form.add_submit('cancel', 'Cancel changes')
    else:
        form.add_reset('reset', 'Cancel changes')

    if form.get_submit() == 'cancel' or (state > 0 and not userlist.changed()):
        print 'CANCEL'
        request.redirect(request.get_path())
        return ''

    if state > 0:
        userlist.replace_deleted()
        for w in userlist.get_widgets():
            if not w.has_changed():
                w.skip_widget()

    def render():
        ret = []
        ret.append(pre(request, 'Edit users', 'edituser'))
        ret.append(form.render())
        ret.append(post())

        return '\n'.join([ str(s) for s in ret ])

    if not form.is_submitted() or form.has_errors() or state == 0 or state == 1:
        return render()

    assert state == 2, 'erk, otherwise'
    
    userlist.commit()

    request.redirect(request.get_path()) # reload with the new details
    return ''
    


def editmode(request):
    """Set user preference on whether they want to edit pictures or not.

    Of course, they're still only allowed to edit the ones they're normally allowed to,
    but this means they can turn off all the edit controls."""
    
    session = request.session

    if session.user and request.form:
        session.wantedit = bool(int(request.form.get('wantedit')))

    request.redirect(request.get_environ('HTTP_REFERER'))

    return pre(request, 'Lost') + ('<h1><a href="%s/">You seem lost</a></h1>' % prefix)+post()



class UserUI:
    _q_exports = []
    
    def __init__(self, u):
        self.user = u

    def _q_index(self, request):
        sess_user = request.session.getuser()

        if sess_user is None:
            request.redirect('%s/user/' % prefix)
            return ''

        print self.user
        print sess_user
        
        if sess_user != self.user and not sess_user.mayAdmin:
            raise AccessError("You may not view this user's details")

        return self.user_details(request)

    user_details = user_details_ptl
