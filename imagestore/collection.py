
import re

import json

from sqlobject import SQLObjectNotFound

import quixote
from quixote.errors import AccessError
from quixote.html import htmltext as H

import imagestore
import imagestore.image as image
import imagestore.collection_page as collection_page
import imagestore.calendarui as calendarui
import imagestore.search as search
import imagestore.upload as upload
import imagestore.menu as menu
import imagestore.auth as auth
import imagestore.insert as insert
import imagestore.http as http
import imagestore.collection_page as collection_page

_re_number = re.compile('^[0-9]+$')
_re_hash = re.compile('^(?:hash|sha1?):([0-9a-f]{40})$', re.I)
_re_md5hash = re.compile('^md5:([0-9a-f]{32})$', re.I)

class Collection:
    _q_exports = [ 'image', 'calendar', 'search', 'admin', 'upload' ]

    def __init__(self, db, parent):
        self.parent = parent
        self.db = db  

        self.calendar = calendarui.CalendarUI(self)
        self.search = search.SearchUI(self)
        self.upload = upload.Upload(self)
        self.ui = collection_page.CollectionUI(self)

        self.image = image.ImageDir(self)      # keep old URLs alive
        
    def _q_index(self, request):
        request = quixote.get_request()

        if request.get_method() == 'POST':
            return self.handle_upload()

        return self.ui._q_index()

    def _q_lookup(self, request, component):
        """ Handle COLLECTION/NNNN namespace """
        # Check for plain ID number
        m = _re_number.match(component)
        if m is not None:
            return image.Image(self, int(m.group(0)))

        # Check for lookup by hash
        m = _re_hash.match(component)
        if m is not None:
            hash = m.group(1)
            try:
                id = int(db.Picture.byHash(hash).id)
                return lambda r: quixote.util.Redirector('%s%d' % (self.path(), id))()
            except SQLObjectNotFound:
                raise TraversalError('Bad image hash')

        m = _re_md5hash.match(component)
        if m is not None:
            hash = m.group(1)
            try:
                id = int(db.Picture.byMd5hash(hash).id)
                return lambda r: quixote.util.Redirector('%s%d' % (self.path(), id))()
            except SQLObjectNotFound:
                raise TraversalError('Bad image MD5 hash')
                
    def _q_access(self, request):
        if not self.mayViewCollection(request, quiet=True):
            raise AccessError, "You may not view this collection"

        m = menu.SubMenu(heading='Collection: %s' % self.db.name)
        if self.mayAdminCol(request, quiet=True):
            m += [ menu.Link(link='Administer',
                             url=self.admin_path()) ]

        if self.mayUpload(request, quiet=True):
            um = menu.SubMenu(heading=menu.Link(link='Upload', url=self.upload.path()))

            if False and self.upload.have_pending(auth.login_user(quiet=True)):
                um += [ menu.Link(link='Pending', url=self.upload.pending_path()) ]
                
            m += [ um ]

        request.context_menu += [ menu.Separator(), m ]
        request.context_menu += [ self.calendar.menupane_extra() ]
        request.context_menu += self.search.menupane_extra()

    def do_upload(self, img, user, added, skipped):
        request = quixote.get_request()

        if not isinstance(img, quixote.http_request.Upload):
            return
        
        visibility=request.form.get('visibility', 'public')
        keywords=request.form.get('keywords', [])
        if not isinstance(keywords, list):
            keywords = [ keywords ]

        try:
            id=insert.import_image(img.fp,
                                   orig_filename=img.orig_filename,
                                   owner=user,
                                   photographer=user,
                                   public=visibility,
                                   collection=self.db,
                                   keywords=keywords)
            added.append(id)
        except insert.AlreadyPresentException, x:
            skipped[img.orig_filename] = x.id

    def handle_upload(self):
        request = quixote.get_request()
        response = quixote.get_response()
        
        user = auth.login_user()
        perm = self.db.permissions(user)

        mayupload = (user and user.mayUpload) or (perm and perm.mayUpload)

        if not mayupload:
            raise AccessError('You may not upload images')

        if 'image' not in request.form:
            response.set_status(204)    # no content
            return ''

        added = []
        skipped = {}
        if isinstance(request.form['image'], list):
            for img in request.form['image']:
                self.do_upload(img, user, added, skipped)
        else:
            img = request.form['image']
            self.do_upload(img, user, added, skipped)
            
        added = [ image.Image(self, id) for id in added ]
        added = [ (p.path(), p.meta.get_meta()) for p in added ]

        http.json_response()
        response.set_status(201)        # created
        
        return json.write({ 'added': added, 'skipped': skipped })
        
    
    def mayEdit(self, request, p, quiet=False):
        user = auth.login_user(quiet=quiet)
        
        if user is None:
            return False

        perms = self.db.permissions(user)
        
        return (perms and perms.mayEdit) or p.mayEdit(user)

    def mayViewCollection(self, request, quiet=False):
        user = auth.login_user(quiet=quiet)

        if self.db.visibility == 'public':
            return True
        if user and self.db.visibility == 'private':
            perms = self.db.permissions(user)
            return user.mayAdmin or self.db.ownerID == user.id or (perms and perms.mayView)

        return False
    
    def mayViewOrig(self, request, p, quiet=False):
        user = auth.login_user(quiet=quiet)

        if self.db.visibility == 'public' and self.db.showOriginal:
            return p.mayView(user)

        if user is None:
            return False

        if self.db.owner == user or p.owner == user:
            return p.mayView(user)

        perms = self.db.permissions(user)
        if perms is not None and (perms.mayAdmin or perms.mayViewall):
            return p.mayView(user)
        
        return False

    def mayView(self, request, p, quiet=False):
        user = auth.login_user(quiet=quiet)

        if self.db.visibility == 'public':
            return p.mayView(user)

        if user is None:
            return False

        if self.db.owner == user:
            return p.mayView(user)

        perms = self.db.permissions(user)
        if p.visibility == 'restricted' and perms.mayViewRestricted:
            return True

        return False

    def mayAdminCol(self, request, quiet=False):
        user = auth.login_user(quiet=quiet)

        if user is None:
            return False

        if user.id == self.db.ownerID:
            return True

        if user.mayAdmin:
            return True

        p = self.db.permissions(user)
        if p and p.mayAdmin:
            return True

        return False

    def mayUpload(self, request, quiet=False):
        user = auth.login_user(quiet=quiet)

        if not user:
            return False;

        if user.mayAdmin or user.mayUpload:
            return True

        p = self.db.permissions(user)
        if p and p.mayUpload:
            return True

        return False

    def admin(self, request):
        if not self.mayAdminCol(request):
            raise AccessError('You may not modify this collection')
        
        return self.ui.admin_page()

    def path(self):
        return '%s%s/' % (self.parent.path(), self.db.name)

    def admin_path(self):
        return self.path() + 'admin'

    def collection_link(self, link, extra=None):
        if extra:
            extra = join_extra(extra)

        return H('<a %s href="%s">%s</a>') % (extra or '', self.path(), link)

    def collection_admin_link(self, link, extra=None):
        if extra:
            extra = join_extra(extra)

        return H('<a %s href="%s">%s</a>') % (extra or '', self.admin_path(), link)
