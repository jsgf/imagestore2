
import quixote
quixote.enable_ptl()

import os.path

from sqlobject import SQLObjectNotFound

from quixote.errors import TraversalError
from quixote.util import StaticDirectory, StaticFile

from imagestore.base_paths import *

import imagestore.db as db
import imagestore.collection as collection
import imagestore.dbfilters as dbfilters
import imagestore.style
import imagestore.menu as menu
import imagestore.nav as nav
import imagestore.auth as auth

#import imagestore.user as user

_q_exports = [ 'user', 'auth', 'admin', 'rss', 'static', ('style.css', 'style_css') ]

style_css = imagestore.style.style_css

def _q_index(request):
    return quixote.redirect('%sdefault/' % path())

def _q_lookup(request, component):
    """ Look up a collection by name.
    XXX TODO: make inaccessible collections invisible. """
    try:
        return collection.Collection(db.Collection.byName(component), imagestore)
    except SQLObjectNotFound, x:
        raise TraversalError('Collection "%s" does not exist' % component)

def _q_access(request):
    """ This _q_access is not really used for access checking, but as
    a hook which is always called when the path is traversed.  It installs
    the state needed for the context menu, which is hung off the request. """
    request = quixote.get_request()
    request.context_menu = menu.SubMenu()

    user = auth.login_user(quiet=True)

    # Add collection list
    collections = db.Collection.select(dbfilters.mayViewCollectionFilter(user),
                                       orderBy=db.Collection.q.id)
    request.context_menu += [ menu.Separator(),
                              menu.SubMenu(heading='Collections:',
                                           items=[ menu.Link(link=c.name,
                                                             url=collection.Collection(c, imagestore).path(),
                                                             extra={ 'title': c.description })
                                                   for c in collections ]) ]

    # add navigation
    request.navigation = nav.Nav(request)
    
def admin(request):
    return 'admin'

def rss(request):
    return 'rss'

# Some glue to make static files work with quixote.publisher1
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

