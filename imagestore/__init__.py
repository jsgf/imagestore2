
from quixote import enable_ptl
enable_ptl()

def path():
    return '/imagestore'

import os.path

from sqlobject import SQLObjectNotFound

from quixote.util import Redirector
from quixote.errors import TraversalError
from quixote.util import StaticDirectory, StaticFile

import imagestore.db as db
import imagestore.collection as collection
import imagestore.pages as page
import imagestore.dbfilters as dbfilters
import imagestore.style
import imagestore.menu as menu
import imagestore.nav as nav

_q_exports = [ 'user', 'admin', 'rss', 'static', ('style.css', 'style_css') ]

style_css = imagestore.style.style_css

def _q_index(request):
    ret = page.menupane(request)

    Redirector('%s/default/' % path())
    
    return page.html(request, 'Imagestore', ret)

def _q_lookup(request, component):
    try:
        return collection.CollectionUI(db.Collection.byName(component), imagestore)
    except SQLObjectNotFound, x:
        raise TraversalError(str(x))

def _q_access(request):
    # Install context menu stuff into request
    request.context_menu = menu.SubMenu()

    user = request.session.getuser()

    # Add collection list
    collections = db.Collection.select(dbfilters.mayViewCollectionFilter(user),
                                       orderBy=db.Collection.q.id)
    request.context_menu += [ menu.Separator(),
                              menu.SubMenu(heading='Collections:',
                                           items=[ menu.Link(link=c.name,
                                                             url=collection.CollectionUI(c, imagestore).path(),
                                                             extra={ 'title': c.description })
                                                   for c in collections ]) ]

    # add navigation
    request.navigation = nav.Nav(request)
    
def admin(request):
    return 'admin'

def rss(request):
    return 'rss'


class Q1StaticFile(StaticFile):
    def __call__(self, req):
        return StaticFile.__call__(self)
    
class Q1StaticDirectory(StaticDirectory):
    def _q_index(self, req):
        return StaticDirectory._q_index(self)

    def _q_lookup(self, req, name):
        return StaticDirectory._q_lookup(self, name)

    def __call__(self, req):
        return StaticDirectory.__call__(self)
    
static = Q1StaticDirectory(os.path.abspath('./static'),
                           file_class=Q1StaticFile)

def static_path():
    return path() + '/static/'
