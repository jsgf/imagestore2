from imagestore.image import ImageUI
from pages import html

class CollectionUI:
    _q_exports = [ 'details', 'image' ]

    def __init__(self, dbobj):
        self.dbobj = dbobj  

        self.image = ImageUI(dbobj)

    def details(self, request):
        return "details"

    def create(self, request):
        return "new collection here..."

    def _q_index(self, request):
        return html('Collection '+self.dbobj.name,
                    'whoot, collection #%d "%s"' % (self.dbobj.id, self.dbobj.name),
                    top='..')
