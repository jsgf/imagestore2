
import os.path

from quixote.util import StaticDirectory
from quixote import enable_ptl

enable_ptl()

import db, sqlobject

from catalogue import CatalogueUI
from pages import pre, post, html

_q_exports = [ 'catalogues', 'user', 'admin', 'rss', 'static' ]

def _q_index(request):
    ret='Catalogues:<br />'
    for c in db.Catalogue.select(orderBy=db.Catalogue.q.id):
        ret += '<a href="%(c)s/">%(c)s</a><br />' % { 'c': c.name }
    return html('Imagestore', ret)
        
def _q_lookup(request, component):
    try:
        return CatalogueUI(db.Catalogue.byName(component))
    except SQLObjectNotFound, x:
        raise TraversalError(str(x))
    
def catalogues(request):
    return html('Catalogues', 'catalogues')

def user(request):
    return pre('User') + 'user' + post()

def admin(request):
    return 'admin'

def rss(request):
    return 'rss'

static = StaticDirectory(os.path.abspath('./static'))
    
