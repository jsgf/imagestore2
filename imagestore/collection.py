from imagestore.image import ImageUI
from pages import html
import collection_page
from calendar import CalendarUI

from sqlobject.sqlbuilder import AND
from db import User, CollectionPerms

class CollectionUI:
    _q_exports = [ 'image', 'calendar' ]

    def __init__(self, dbobj):
        self.dbobj = dbobj  

        self.image = ImageUI(self)
        self.calendar = CalendarUI(self)
        
    _q_index = collection_page._q_index

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
            
        return p.mayEdit(user)

    def mayViewOrig(self, request, p):
        user=request.session.getuser()

        if self.dbobj.visibility == 'public' and self.dbobj.showOriginal:
            return p.mayView(user)

        if user is None:
            return False

        if self.dbobj.owner == user or p.owner == user:
            return p.mayView(user)

        perms = self.getperms(user)
        if perms is not None and (perms.mayAdmin or perms.mayViewAll):
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
