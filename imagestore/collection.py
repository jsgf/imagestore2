from quixote.errors import AccessError

from imagestore.image import ImageUI
from pages import html
import collection_page
from calendarui import CalendarUI

from sqlobject.sqlbuilder import AND
from db import User, CollectionPerms

class CollectionUI:
    _q_exports = [ 'image', 'calendar' ]

    def __init__(self, dbobj):
        self.dbobj = dbobj  

        self.image = ImageUI(self)
        self.calendar = CalendarUI(self)
        
    _q_index = collection_page._q_index

    def _q_access(self, request):
        if not self.mayViewCollection(request):
            raise AccessError, "You may not view this collection"

    def getperms(self, user):
        perms = CollectionPerms.select(AND(CollectionPerms.q.userID == user.id,
                                           CollectionPerms.q.collectionID == self.dbobj.id))
        if perms.count() == 0:
            return None
        return perms[0]
    
    def mayEdit(self, request, p):
        user = request.session.getuser()
        
        if user is None:
            return False
            
        return request.session.wantedit and p.mayEdit(user)

    def mayViewCollection(self, request):
        user = request.session.getuser()

        if self.dbobj.visibility == 'public':
            return True
        if user and self.dbobj.visibility == 'private':
            perms = self.getperms(user)
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

        perms = self.getperms(user)
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

        return False
