
from sqlobject.sqlbuilder import AND

from quixote.errors import AccessError
from quixote.html import htmltext as H

import imagestore
import imagestore.image as image
import imagestore.collection_page as collection_page
import imagestore.calendarui as calendarui
import imagestore.search as search
import imagestore.upload as upload
import imagestore.menu as menu

class CollectionUI:
    _q_exports = [ 'image', 'calendar', 'search', 'admin', 'upload' ]

    def __init__(self, dbobj, parent):
        self.parent = parent
        self.dbobj = dbobj  

        self.image = image.ImageUI(self)
        self.calendar = calendarui.CalendarUI(self)
        self.search = search.SearchUI(self)
        self.upload = upload.UploadUI(self)
        
    _q_index = collection_page._q_index

    def _q_access(self, request):
        if not self.mayViewCollection(request):
            raise AccessError, "You may not view this collection"

        m = menu.SubMenu(heading='Collection: %s' % self.dbobj.name)
        if self.mayAdminCol(request):
            m += [ menu.Link(link='Administer',
                             url=self.admin_path()) ]

        if self.mayUpload(request):
            um = menu.SubMenu(heading=menu.Link(link='Upload', url=self.upload.path()))
            if self.upload.have_pending(request.session.getuser()):
                um += [ menu.Link(link='Pending', url=self.upload.pending_path()) ]
            m += [ um ]

        request.context_menu += [ menu.Separator(), m ]
        request.context_menu += [ self.calendar.menupane_extra() ]
        request.context_menu += self.search.menupane_extra()
        
    def mayEdit(self, request, p):
        user = request.session.getuser()
        
        if user is None:
            return False

        perms = self.dbobj.permissions(user)
        
        return (perms and perms.mayEdit) or p.mayEdit(user)

    def mayViewCollection(self, request):
        user = request.session.getuser()

        if self.dbobj.visibility == 'public':
            return True
        if user and self.dbobj.visibility == 'private':
            perms = self.dbobj.permissions(user)
            return user.mayAdmin or self.dbobj.ownerID == user.id or (perms and perms.mayView)

        return False
    
    def mayViewOrig(self, request, p):
        user=request.session.getuser()

        if self.dbobj.visibility == 'public' and self.dbobj.showOriginal:
            return p.mayView(user)

        if user is None:
            return False

        if self.dbobj.owner == user or p.owner == user:
            return p.mayView(user)

        perms = self.dbobj.permissions(user)
        if perms is not None and (perms.mayAdmin or perms.mayViewall):
            return p.mayView(user)
        
        return False

    def mayView(self, request, p):
        user = request.session.getuser()

        if self.dbobj.visibility == 'public':
            return p.mayView(user)

        if user is None:
            return False

        if self.dbobj.owner == user:
            return p.mayView(user)

        perms = self.dbobj.permissions(user)
        if p.visibility == 'restricted' and perms.mayViewRestricted:
            return True

        return False

    def mayAdminCol(self, request):
        user = request.session.getuser()

        if user is None:
            return False

        if user.id == self.dbobj.ownerID:
            return True

        if user.mayAdmin:
            return True

        p = self.dbobj.permissions(user)
        if p and p.mayAdmin:
            return True

        return False

    def mayUpload(self, request):
        user = request.session.getuser()

        if not user:
            return False;

        if user.mayAdmin or user.mayUpload:
            return True

        p = self.dbobj.permissions(user)
        if p and p.mayUpload:
            return True

        return False

    def admin(self, request):
        if not self.mayAdminCol(request):
            raise AccessError('You may not modify this collection')
        
        return collection_page.admin_page(self, request)

    def path(self):
        return '%s%s/' % (self.parent.path(), self.dbobj.name)

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
