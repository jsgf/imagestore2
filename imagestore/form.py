import re
from quixote.form2 import Form, SingleSelectWidget

from db import *
from dbfilters import userFilter

def userOptList():
    users = User.select(userFilter(), orderBy=User.q.id)

    return [ (u.id, '%d: %s' % (u.id, u.fullname), u.id) for u in users ]
