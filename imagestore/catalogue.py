from imagestore.image import ImageUI
from pages import html

class CatalogueUI:
    _q_exports = [ 'details', 'image' ]

    def __init__(self, dbobj):
        self.dbobj = dbobj  

        self.image = ImageUI(dbobj)

    def details(self, request):
        return "details"

    def create(self, request):
        return "new catalogue here..."

    def _q_index(self, request):
        return html('Catalogue '+self.dbobj.name,
                    'whoot, catalogue #%d "%s"' % (self.dbobj.id, self.dbobj.name),
                    top='..')
