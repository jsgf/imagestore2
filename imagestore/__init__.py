
from quixote import enable_ptl
enable_ptl()

def path():
    return '/imagestore'

import os.path

from sqlobject import SQLObjectNotFound

from quixote.util import Redirector
from quixote.errors import TraversalError
from quixote.util import StaticDirectory

import imagestore.db as db
import imagestore.collection as collection
import imagestore.pages as page
import imagestore.dbfilters as dbfilters
import imagestore.style
import imagestore.menu as menu
import imagestore.nav as nav

_q_exports = [ 'collections', 'user', 'admin', 'rss', 'static', ('style.css', 'style_css') ]

style_css = imagestore.style.style_css

def _q_index(request):
    ret = page.menupane(request)

    Redirector('%s/default/' % path())
    
    return page.html(request, 'Imagestore', ret)

def _q_lookup(request, component):
    try:
        return collection.CollectionUI(db.Collection.byName(component))
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
                                                             url=collection.CollectionUI(c).collection_url(),
                                                             extra={ 'title': c.description })
                                                   for c in collections ]) ]

    # add navigation
    request.navigation = nav.Nav(request)
    
def collections(request):
    return page.html(request, 'Collections', 'collections')

def admin(request):
    return 'admin'

def rss(request):
    return 'rss'

static = StaticDirectory(os.path.abspath('./static'))
    
