
import os.path

from quixote.util import StaticDirectory
from quixote import enable_ptl

enable_ptl()

import db, sqlobject

from collection import CollectionUI
from pages import pre, post, html

_q_exports = [ 'collections', 'user', 'admin', 'rss', 'static' ]

def _q_index(request):
    ret='Collections:<br />'
    for c in db.Collection.select(orderBy=db.Collection.q.id):
        ret += '<a href="%(c)s/">%(c)s</a><br />' % { 'c': c.name }
    return html('Imagestore', ret)
        
def _q_lookup(request, component):
    try:
        return CollectionUI(db.Collection.byName(component))
    except SQLObjectNotFound, x:
        raise TraversalError(str(x))
    
def collections(request):
    return html('Collections', 'collections')

def user(request):
    return pre('User') + 'user' + post()

def admin(request):
    return 'admin'

def rss(request):
    return 'rss'

static = StaticDirectory(os.path.abspath('./static'))
    
