
from quixote import enable_ptl
enable_ptl()

def path():
    return '/imagestore'

import os.path

from sqlobject import SQLObjectNotFound

from quixote.util import Redirector
from quixote.errors import TraversalError
from quixote.util import StaticDirectory

from db import Collection

from collection import CollectionUI
from pages import pre, post, html, menupane
from style import style_css
from dbfilters import mayViewCollectionFilter

import menu

from nav import Nav

_q_exports = [ 'collections', 'user', 'admin', 'rss', 'static', ('style.css', 'style_css') ]

def _q_index(request):
    ret = menupane(request)

    Redirector('%s/default/' % path())
    
    return html(request, 'Imagestore', ret)

def _q_lookup(request, component):
    try:
        return CollectionUI(Collection.byName(component))
    except SQLObjectNotFound, x:
        raise TraversalError(str(x))

def _q_access(request):
    # Install context menu stuff into request
    request.context_menu = menu.SubMenu()

    user = request.session.getuser()

    # Add collection list
    collections = Collection.select(mayViewCollectionFilter(user), orderBy=Collection.q.id)
    request.context_menu += [ menu.Separator(),
                              menu.SubMenu(heading='Collections:',
                                           items=[ menu.Link(link=c.name,
                                                             url=CollectionUI(c).collection_url(),
                                                             extra={ 'title': c.description })
                                                   for c in collections ]) ]

    # add navigation
    request.navigation = Nav(request)
    
def collections(request):
    return html(request, 'Collections', 'collections')

def admin(request):
    return 'admin'

def rss(request):
    return 'rss'

static = StaticDirectory(os.path.abspath('./static'))
    
