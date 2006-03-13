# User management

from sqlobject import SQLObjectNotFound
from sqlobject.sqlbuilder import AND, NOT, IN

from quixote.util import Redirector
from quixote.errors import AccessError, TraversalError, QueryError
from quixote.html import htmltext as H, TemplateIO
import quixote.form as form2

import imagestore
import imagestore.db as db
import imagestore.dbfilters as dbfilters
import imagestore.pages as page
import imagestore.user_page as user_page
import imagestore.menu as menu
import imagestore.config as config

_q_exports = [ 'login', 'logout', 'editmode', 'editusers', 'newuser' ]

def _q_access(request):
    sess_user = request.session.getuser()
    
    if sess_user and sess_user.mayAdmin:
        request.context_menu += [ menu.Separator(),
                                  menu.Link('User admin', '%s/user/editusers' % imagestore.path()) ]


def user_url(user):
    if user is None:
        return '%s/user/login' % imagestore.path()
    else:
        return '%s/user/%s/' % (imagestore.path(), user.username)

perms = [ ('mayAdmin', 'May administer'),
          ('mayViewall', 'May view everything'),
          ('mayUpload', 'May upload pictures'),
          ('mayComment', 'May comment'),
          ('mayCreateCat', 'May create collections') ]

def login(request):
    body = TemplateIO(html=True)
    
    body += H('<h1>Imagestore Login</h1>')

    session = request.session

    if request.form:
        username = request.form.get('username')
        password = request.form.get('password')
        referer = request.form.get('referer')

        failed = False
        try:
            user = db.User.byUsername(username)

            if password == '':
                password = None

            if user.password != password:
                failed = True
        except SQLObjectNotFound, x:
            failed = True

        if failed:
            body += page.error(request, 'User unknown or password incorrect', 'Please try again.')
            body += user_page.login_form(request, username=username)
        else:
            body += H('<p>Hi, %s, you\'ve logged in' % user.fullname)
            session.setuser(user.id)
            if referer is not None and referer != '':
                Redirector(referer)
            else:
                Redirector(user_url(user))
    else:
        body += user_page.login_form(request, referer=request.get_environ('HTTP_REFERER'))


    p = TemplateIO(html=True)

    p += page.pre(request, 'Imagestore Login', 'login', trail=False)
    p += page.menupane(request)
    p += H(body)
    p += page.post()

    return p.getvalue()

def newuser(request):
    user = request.session.getuser()

    if not ((user and user.mayAdmin) or config.users.unpriv_newuser):
        raise AccessError('You may not create a new user')

    form = form2.Form()
    
    form.add(form2.StringWidget, 'username', title='User name')
    form.add(form2.StringWidget, 'fullname', title='Full name')
    form.add(form2.StringWidget, 'email', title='email address')
    form.add(form2.PasswordWidget, 'pass1', title='Password')
    form.add(form2.PasswordWidget, 'pass2', title='Password verify')
    form.add_submit('create', 'Create user')
    
    render=False
    
    if form.is_submitted():
        username = form['username'].strip()
        if db.User.select(db.User.q.username == username).count() != 0:
            form.get_widget('username').set_error(H("Username '%s' already in use") % username)
        if form['pass1'] != form['pass2']:
            form.get_widget('pass1').set_error('Passwords do not match')
        fullname = form['fullname'].strip()
        if fullname == '':
            form.get_widget('fullname').set_error('Full name not set')
        email = form['email'].strip()
        if email == '':
            form.get_widget('email').set_error('Missing or bad email address')
            
        if not form.has_errors():
            u = db.User(username=username, fullname=fullname,
                        password=form['pass1'],
                        email=email,
                        mayAdmin=False,
                        mayViewall=False,
                        mayUpload=False,
                        mayComment=config.users.mayComment,
                        mayRate=config.users.mayRate)
            Redirector(user_url(u))
        else:
            render=True
    else:
        render=True

    if render:
        r = TemplateIO(html=True)
        
        r += page.pre(request, 'New User', 'newuser')
        r += page.menupane(request)
        r += form.render()
        r += page.post()

        return r.getvalue()
    else:
        return ''

    
def logout(request):
    request.session.setuser(None)

    Redirector(request.get_environ('HTTP_REFERER'))

    return 'logged out'

def _q_lookup(request, component):
    u = None
    try:
        u = db.User.byUsername(component)
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

    Redirector(user_url(user))

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
            self.add(form2.CheckboxWidget, 'perm.'+p, getattr(user, p), title=p[3:], hint=desc)
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
        r += H('<td><a href="%s">%d</a></td>') % (user_url(self.user), self.user.id)
        r += self.render_content()
        r += H('</tr>\n')
            
        return r.getvalue()

    def _parse(self, request):
        form2.CompositeWidget._parse(self, request)

        if self['delete']:
            count = db.Picture.select(db.Picture.q.ownerID == self.user.id).count()
            
            if count != 0 and self.get('replacement') == 0:
                raise form2.WidgetValueError('Must set replacement')

        if self['username'] != self.user.username and \
               db.User.select(db.User.q.username == self['username']).count() != 0:
            self.get_widget('username').set_error('New username must be unique')

    def has_changed(self):
        if self.get('skip') == 'skip':
            return False
        
        if self['delete']:
            return True

        for v in ['username', 'fullname', 'email']:
            if self[v] != getattr(self.user, v):
                return True

        for (p, desc) in perms:
            if self['perm.'+p] != getattr(self.user, p):
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
            setattr(self.user, p, self['perm.'+p])

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
            replacements = db.User.select(dbfilters.userFilter(NOT(IN(db.User.q.id, [ w.user.id for w in deleted ]))),
                                          orderBy=db.User.q.id)

            for w in deleted:
                pics = db.Picture.select(db.Picture.q.ownerID == w.user.id).count()
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

def editusers(request):
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

    userform = form2.Form()
    userform.add(UserListWidget, 'users')
    userlist = userform.get_widget('users')

    userform.add(form2.HiddenWidget, 'state', value=0)

    for u in db.User.select(dbfilters.userFilter(), orderBy=db.User.q.id):
        userlist.adduser(u)

    state = int(userform['state'])
    
    if state == 0:
        userform.get_widget('state').value = 1
        userform.add_submit('update', 'Update users')
    elif state == 1 or (state == 2 and userform.has_errors()):
        userform.get_widget('state').value = 2
        userform.add_submit('confirm', 'Confirm updates')
    elif state == 2:
        pass
    else:
        raise QueryError('Bad state %d' % state)

    if state > 0:
        userform.add_submit('cancel', 'Cancel changes')
    else:
        userform.add_reset('reset', 'Cancel changes')

    if userform.get_submit() == 'cancel' or (state > 0 and not userlist.changed()):
        print 'CANCEL'
        Redirector(request.get_path())
        return ''

    if state > 0:
        userlist.replace_deleted()
        for w in userlist.get_widgets():
            if not w.has_changed():
                w.skip_widget()

    def render():
        ret = TemplateIO(html=True)

        ret += page.pre(request, 'User administration', 'editusers')
        ret += page.menupane(request)
        ret += H('<h1>User administration</h1>\n')
        ret += userform.render()
        ret += page.post()

        return ret.getvalue()

    if not userform.is_submitted() or userform.has_errors() or state == 0 or state == 1:
        return render()

    assert state == 2, 'erk, otherwise'
    
    userlist.commit()

    Redirector(request.get_path()) # reload with the new details
    return ''
    


def editmode(request):
    """Set user preference on whether they want to edit pictures or not.

    Of course, they're still only allowed to edit the ones they're normally allowed to,
    but this means they can turn off all the edit controls."""
    
    session = request.session

    if session.user and request.form:
        session.wantedit = bool(int(request.form.get('wantedit')))

    Redirector(request.get_environ('HTTP_REFERER'))

    return ''

def editmode_url(onoff):
    return '%s/user/editmode?wantedit=%d' % (imagestore.path(), onoff)

class EditSwitchItem(menu.MenuItem):
    def __init__(self, session, classes=None, extra=None):
        menu.MenuItem.__init__(self, classes=classes, extra=extra)

        self.classes.append('editswitch')

        self.session = session

    def render(self, depth=0):
        assert self.session.getuser() is not None, "Only makes sense when someone's logged in"

        if self.session.wantedit:
            off = '<a href="%s">Off</a>' % editmode_url(not self.session.wantedit)
            on = '<span class="selected">On</span>'
        else:
            off = '<span class="selected">Off</span>'
            on = '<a href="%s">On</a>' % editmode_url(not self.session.wantedit)

        return H('<span %s>Editing:&nbsp%s&nbsp;%s</span>' % (self.tags(), off, on))
    
class UserUI:
    _q_exports = [ 'edit' ]
    
    def __init__(self, u):
        self.user = u

    def _q_access(self, request):
        sess_user = request.session.getuser()

        if not sess_user or (sess_user != self.user and not sess_user.mayAdmin):
            raise AccessError("You may not view this user's details")
            
    def _q_index(self, request):
        sess_user = request.session.getuser()

        if sess_user is None:
            Redirector(user_url(sess_user))
            return ''

        return user_page.user_page(request)

    edit = user_page.user_edit
