import re
from quixote.form import Form, SingleSelectWidget

import imagestore.db as db
import imagestore.dbfilters as dbfilters

def userOptList():
    users = db.User.select(dbfilters.userFilter(), orderBy=db.User.q.id)

    return [ (u.id, '%d: %s' % (u.id, u.fullname), u.id) for u in users ]

def visibilityOptList():
    return [ 'public', 'restricted', 'private' ]

def cameraOptList():
    return [ (c.id, c.nickname, c.id) for c in db.Camera.select(orderBy=db.Camera.q.id) ]
    
def splitKeywords(keywords=None):
    keywords  = keywords or ''
    return [ k.strip() for k in keywords.split(',') if k.strip() ]

