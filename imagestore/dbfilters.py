from db import User, Picture, Collection, CollectionPerms
from sqlobject import SQLObjectNotFound
from sqlobject.sqlbuilder import *

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
def _collectionPerm(collection, user):
    cp = CollectionPerms.select(AND(CollectionPerms.q.collectionID == collection.id,
                                    CollectionPerms.q.userID == user.id))
    if cp.count():
        assert cp.count() == 1, "duplicate collection permissions?"
        perms = cp[0]
        if perms.mayView:               # mayView is the prerequisite for everything else
            return perms

    return None

def _inCollection(collection, filt):
    return AND(Picture.q.collectionID == collection.id, filt)

def mayViewFilter(collection, user = None):
    " Rules for which pictures a user may view - user==None for anonymous "

    ok = [ False ]

    if collection.visibility == 'public':
        ok.append(Picture.q.visibility == 'public')

    if user is not None:
        ok.append(Picture.q.ownerID == user.id)

        perms = _collectionPerm(collection, user)

        if user.mayViewall or user.mayAdmin or (perms and perms.mayViewall):
            ok = [ True ]               # overrides all
        else:

            if collection.visibility != 'public' and perms and perms.mayView:
                # if collection is public, we've already tested for this
                ok.append(Picture.q.visibility == 'public')

            if perms and perms.mayViewRestricted:
                ok.append(Picture.q.visibility == 'restricted')

    return _inCollection(collection, OR(*ok))

def mayEditFilter(collection, user):
    ok = False

    if user is not None:
        perms = _collectionPerm(collection, user)
        if user.mayAdmin or (perms and perms.mayEdit):
            ok = True
        else:
            ok = (Picture.q.ownerID == user.id)

    return _inCollection(collection, ok)

def mayCurateFilter(collection, user):
    ok = False

    if user is not None:
        perms = _collectionPerm(collection, user)
        if perms and perms.mayCurate:
            ok = True
        else:
            ok = mayEditFilter(collection, user)

    return _inCollection(collection, ok)


def userFilter(sql=True):
    return sql

    if sql is not True:
        return AND(sql, User.q.enabled)
    return User.q.enabled
