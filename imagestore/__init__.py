
from quixote import enable_ptl
enable_ptl()

import os.path

from sqlobject import SQLObjectNotFound
from quixote.errors import TraversalError
from quixote.util import StaticDirectory

import db, sqlobject

from collection import CollectionUI
from pages import pre, post, html, menupane, prefix
from style import style_css

_q_exports = [ 'collections', 'user', 'admin', 'rss', 'static', ('style.css', 'style_css') ]

def _q_index(request):
    ret = menupane(request)

    request.redirect('%s/default/' % prefix)
    
    return html(request, 'Imagestore', ret)

def _q_lookup(request, component):
    try:
        return CollectionUI(db.Collection.byName(component))
    except SQLObjectNotFound, x:
        raise TraversalError(str(x))
    
def collections(request):
    return html(request, 'Collections', 'collections')

def admin(request):
    return 'admin'

def rss(request):
    return 'rss'

static = StaticDirectory(os.path.abspath('./static'))
    
