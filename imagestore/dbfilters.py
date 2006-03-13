from sqlobject import SQLObjectNotFound
from sqlobject.sqlbuilder import *

import imagestore.db as db


# A set of functions which return SQLBuilder query objects to filter
# various DB requests

# There are two levels of visibility: collection visibility and picture visibility
#
# Collections are public or private.  If a collection is private, a user needs explicit
# permission to view anything.  If a collection is public, then only the picture visibility
# matters.
#
# Pictures may be public, restricted or private.  Public pictures may be seen by anyone,
# including anonymous users.  Restricted pictures mean that you need specific per-collection
# permission to view the image, even if the collection is public.  Private means that only
# the owner may see the picture.
#
# Users may have either the mayViewall or mayAdmin flags set.  Either of these allow the user
# to view all images, ignoring the checks above.  The owner of an image may also do anything
# to the image.

# Since collection and user are fixed, we can statically fetch the
# collection permissions for the user before the main query

def _inCollection(collection, filt):
    return AND(db.Picture.q.collectionID == collection.id, filt)

def mayViewFilter(collection, user = None):
    " Rules for which pictures a user may view - user==None for anonymous "

    ok = [ False ]

    if collection.visibility == 'public':
        ok.append(db.Picture.q.visibility == 'public')

    if user is not None:
        ok.append(db.Picture.q.ownerID == user.id)

        perms = collection.permissions(user)

        if user.mayViewall or user.mayAdmin or (perms and perms.mayViewall):
            ok = [ True ]               # overrides all
        else:

            if collection.visibility != 'public' and perms and perms.mayView:
                # if collection is public, we've already tested for this
                ok.append(db.Picture.q.visibility == 'public')

            if perms and perms.mayViewRestricted:
                ok.append(db.Picture.q.visibility == 'restricted')

    return _inCollection(collection, AND(db.Picture.q.uploadID == None, OR(*ok)))

def mayEditFilter(collection, user):
    ok = False

    if user is not None:
        perms = collection.permissions(user)
        if user.mayAdmin or (perms and perms.mayEdit):
            ok = True
        else:
            ok = (db.Picture.q.ownerID == user.id)

    return _inCollection(collection, ok)

def mayCurateFilter(collection, user):
    ok = False

    if user is not None:
        perms = collection.permissions(user)
        if perms and perms.mayCurate:
            ok = True
        else:
            ok = mayEditFilter(collection, user)

    return _inCollection(collection, ok)


def userFilter(sql=True):
    return AND(sql, db.User.q.enabled)

def mayViewCollectionFilter(user):
    ok = [ db.Collection.q.visibility == 'public' ]

    if user is not None:
        if user.mayAdmin:
            ok = [ True ]
        else:
            ok += [ db.Collection.q.ownerID == user.id ]
#             ok += [ AND(db.CollectionPerms.q.collectionID == db.Collection.q.id,
#                         db.CollectionPerms.q.userID == user.id,
#                         db.CollectionPerms.q.mayView) ]

    return OR(*ok)
