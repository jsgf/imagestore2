from SQLObject import *
from EXIF import Ratio
import sha
import mx.DateTime

conn = SQLiteConnection('imagestore.db', debug=0)
__connection__ = conn

_encode_media=True                      # use base64 for binary data (sqlite needs it)
_chunksize=128*1024                     # chunk Media into lumps

def defaultCat():
    return Catalogue.byName('default')

class Catalogue(SQLObject):
    """
    A Catalogue of Pictures

    Pictures are grouped into Catalogues, and each Catalogue has its
    own keywords; a Picture can be in at most one Catalogue(?)

    Catalogues have their own set of user permissions.
    """

    name = StringCol(length=100, notNone=True, unique=True, alternateID=True)

    # Keywords used in this catalogue
    keywords = RelatedJoin('Keyword')

    # Default visibility to anonymous/undefined users
    visibility = EnumCol(enumValues=["public","private"], default="public", notNone=True)

    # Whether to allow anonymous/non-privileged users to see original image files
    showOriginal = BoolCol(notNone=True, default=False)

class CataloguePerms(SQLObject):
    "Per-catalogue user permissions"
    user = ForeignKey('User')
    catalogue = ForeignKey('Catalogue')

    mayAdmin = BoolCol(notNone=False, default=False)    # update ACL
    mayViewAll = BoolCol(notNone=False, default=False)  # view all images
    mayView = BoolCol(notNone=False, default=False)     # view public images
    mayUpload = BoolCol(notNone=False, default=False)   # upload new images
    mayComment = BoolCol(notNone=False, default=False)  # add comments to images
    mayEdit = BoolCol(notNone=False, default=False)     # edit image metadata
    mayCurate = BoolCol(notNone=False, default=False)   # administer keywords
    
class User(SQLObject):
    "Imagestore user database"
    
    username = StringCol(length=100, unique=True, notNone=True, alternateID=True)
    email = StringCol(length=100, notNone=True)
    password = StringCol(length=32, default=None)
    fullname = StringCol(default=None)

    # Default/global capabilities
    mayAdmin = BoolCol(notNone=True, default=False)     # control users & perms
    mayViewall = BoolCol(notNone=True, default=False)   # view all images everywhere
    mayUpload = BoolCol(notNone=True, default=False)    # upload images everywhere
    mayComment = BoolCol(notNone=True, default=False)   # comment on images everywhere
    mayCreateCat = BoolCol(notNone=True, default=False) # may create new catalogues
    
class Camera(SQLObject):
    owner = ForeignKey("User")

    nickname = StringCol(unique=True)
    manufacturer = StringCol()
    model = StringCol()
    serial = StringCol()
    notes = StringCol()

class Media(SQLObject):
    """Media chunks; a single piece of data, like an image, will be
    chunked into one or more records in the Media table.  Each chunk
    will have the SHA1 hash of the combined data, and a sequence
    number starting from 0."""

    hash = StringCol(length=40, varchar=False, notNone=True)
    sequence = IntCol(notNone=True)
    data = StringCol(sqlType="MEDIUMBLOB")
    
    def _set_data(self, v):
        if _encode_media:
            v = v.encode('base64').replace('\n', '')
        self._SO_set_data(v)

    def _get_data(self):
        r = self._SO_get_data()
        if _encode_media:
            r = r.decode('base64')
        return r

def setmedia(data, hash=None):
    """Add a new piece of data to the Media table, possibly
    chunking and encoding it if necessary."""
    
    if hash is None:
        sha1 = sha.new(data)
        hash = sha1.digest().encode('hex')

    order = 0
    media=None

    # Make sure there's no old/partial/existing pieces of this data
    for m in Media.select(Media.q.hash == hash):
        m.destroySelf()
    
    while len(data) > 0:
        m = Media.new(data=data[:_chunksize], hash=hash, sequence=order)
        data=data[_chunksize:]
        order += 1
        if media is None:
            media = m
        
    return media

def getmediachunks(hash):
    """Generator to return each successive chunk of Media data id"""

    for c in Media.select(Media.q.hash==hash, orderBy='sequence'):
        #print "chunk id=%d, seq=%d, len=%d" % (c.id, c.sequence, len(c.data))
        yield c.data

def getmedia(id, verify=False):
    """Return media data for id"""
    
    if verify:
        sha1 = sha.new()

    m = Media(id)
        
    data=''
    for d in getmediachunks(m.hash):
        if verify:
            sha1.update(d)
        data += d

    if verify:
        hash = sha1.digest().encode('hex')
        if hash != m.hash:
            raise IOError, 'Media data %d is corrupt: expect SHA1 %s, got %s' % \
                  (id, m.hash, hash)
    
    return data

class Keyword(SQLObject):
    "Picture keywords"

    word = StringCol(length=20, unique=True, notNone=True, alternateID=True)
    pictures = RelatedJoin('Picture')

    catalogue = ForeignKey('Catalogue')

class Picture(SQLObject):
    "Pictures - including movies and other media"

    def getimage(self):
        return getmedia(self.mediaid)

    def getimagechunks(self):
        return getmediachunks(self.hash)
    
    def getthumb(self):
        return getmedia(self.thumbid)

    def converttime(self, timestr):
        return mx.DateTime.strptime(str(timestr), '%Y-%m-%d %H:%M:%S')

    def _get_record_time(self):
        return self.converttime(self._SO_get_record_time())

    def _get_modified_time(self):
        return self.converttime(self._SO_get_modified_time())

    hash = StringCol(length=40, varchar=False, notNone=True, unique=True, alternateID=True)
    mimetype = StringCol(notNone=True, length=40)

    datasize = IntCol(notNone=True)
    mediaid = ForeignKey("Media")
    link = ForeignKey("Picture", default=None)

    catalogue = ForeignKey('Catalogue', notNone=True, default=lambda: defaultCat().id)
    keywords = RelatedJoin('Keyword')
    comments = MultipleJoin('Comment')
    
    camera = ForeignKey('Camera', default=None)
    
    owner = ForeignKey("User", default=None)
    visibility = EnumCol(enumValues=["public","private"], default="public", notNone=True)
    photographer = ForeignKey('User', default=None)

    #title = StringCol(length=127,default=None)
    description = StringCol(default=None)
    copyright = StringCol(default=None)
    rating = IntCol(default=0, notNone=True)
    
    width = IntCol(notNone=True)
    height = IntCol(notNone=True)
    orientation = IntCol(default=0, notNone=True)

    thumbid = ForeignKey("Media", default=None)
    th_width = IntCol(default=None)
    th_height = IntCol(default=None)
    
    record_time = DateTimeCol()
    modified_time = DateTimeCol(default=mx.DateTime.gmt, notNone=True)

    exposure_program = StringCol(default=None)
    flash = BoolCol()
    f_number = StringCol(length=10)
    exposure_time = StringCol(length=10) # actually an EXIF.Ratio
    exposure_bias = IntCol()
    brightness = IntCol(default=None)
    focal_length = IntCol()

class Comment(SQLObject):
    user = ForeignKey('User')
    picture = ForeignKey('Picture')
    timestamp = DateTimeCol(default=mx.DateTime.gmt, notNone=True)

    comment = StringCol()
    

Catalogue.createTable(ifNotExists=True)
CataloguePerms.createTable(ifNotExists=True)
Picture.createTable(ifNotExists=True)
Comment.createTable(ifNotExists=True)
Media.createTable(ifNotExists=True)
Keyword.createTable(ifNotExists=True)
User.createTable(ifNotExists=True)
Camera.createTable(ifNotExists=True)

if User.select(User.q.username == 'admin').count() == 0:
    User.new(username='admin', password='admin', email='jeremy@goop.org',
             fullname='Administrator',
             mayAdmin=True, mayViewall=True, mayUpload=True, mayComment=False,
             mayCreateCat=True)
if Catalogue.select(Catalogue.q.name == 'default').count() == 0:
    Catalogue.new(name='default')

