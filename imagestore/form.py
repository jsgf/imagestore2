import re
from quixote.form2 import Form, SingleSelectWidget

from db import *
from dbfilters import userFilter

def userOptList():
    users = User.select(userFilter(), orderBy=User.q.id)

    return [ (u.id, '%d: %s' % (u.id, u.fullname), u.id) for u in users ]

def visibilityOptList():
    return [ 'public', 'restricted', 'private' ]

def cameraOptList():
    return [ (c.id, c.nickname, c.id) for c in Camera.select(orderBy=Camera.q.id) ]
    
def splitKeywords(keywords=None):
    keywords  = keywords or ''
    return [ k.strip() for k in keywords.split(',') if k.strip() ]

