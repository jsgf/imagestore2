from imagestore.image import ImageUI
from pages import html
import collection_page

class CollectionUI:
    _q_exports = [ 'details', 'image' ]

    def __init__(self, dbobj):
        self.dbobj = dbobj  

        self.image = ImageUI(dbobj)

    def details(self, request):
        return "details"

    def create(self, request):
        return "new collection here..."

    _q_index = collection_page._q_index
