from sqlobject import *
from EXIF import Ratio
import sha
import mx.DateTime
import os.path

lazycol=False

dbinfo = {
    'lurch':    { 'conn': 'mysql://imagestore:im_zwarp@lurch/imagestore',
                  'encode': False,
                  },
    'local':    { 'conn': 'sqlite:' + os.path.abspath('imagestore.db'),
                  'encode': True,
                  },
    }

db='local'

print 'path='+dbinfo[db]['conn']
conn = connectionForURI(dbinfo[db]['conn'])
conn.debug = 0

__connection__ = conn

#print 'connection: %s' % conn

_encode_media=dbinfo[db]['encode']      # use base64 for binary data (sqlite needs it)
_chunksize=128*1024                     # chunk Media into lumps

def defaultCollection():
    return Collection.byName('default')

class Collection(SQLObject):
    """
    A Collection of Pictures

    Pictures are grouped into Collections; each Collections has its
    own keywords; a Picture can be in at most one Collection

    Collections have their own set of user permissions.
    """

    # Short URL-friendly name
    name = StringCol(length=20, notNone=True, unique=True, alternateID=True)

    # Description
    description = StringCol(length=100, default='')

    # Owner
    owner = ForeignKey('User')

    # Keywords used in this collection
    keywords = RelatedJoin('Keyword')

    # Default visibility to anonymous/undefined users
    visibility = EnumCol(enumValues=["public","private"], default="public", notNone=True)

    # Whether to allow anonymous/non-privileged users to see original image files
    showOriginal = BoolCol(notNone=True, default=False)

    # Pictures in this collection
    pictures = MultipleJoin('Picture')
    
class CollectionPerms(SQLObject):
    "Per-Collection user permissions"
    user = ForeignKey('User')
    collection = ForeignKey('collection')

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
    fullname = StringCol(default=None,length=100)

    # Default/global capabilities
    mayAdmin = BoolCol(notNone=True, default=False)     # control users & perms
    mayViewall = BoolCol(notNone=True, default=False)   # view all images everywhere
    mayUpload = BoolCol(notNone=True, default=False)    # upload images everywhere
    mayComment = BoolCol(notNone=True, default=False)   # comment on images everywhere
    mayCreateCat = BoolCol(notNone=True, default=False) # may create new collections
    
class Camera(SQLObject):
    owner = ForeignKey("User")

    nickname = StringCol(length=32,unique=True,alternateID=True)
    manufacturer = StringCol(length=80)
    model = StringCol(length=80)
    serial = StringCol(length=80)
    notes = StringCol()

class Media(SQLObject):
    """Media chunks; a single piece of data, like an image, will be
    chunked into one on more records in the Media table.  Each chunk
    will have the SHA1 hash of the combined data, and a sequence
    number starting from 0."""

    hash = StringCol(length=40, varchar=False, notNone=True)
    sequence = IntCol(notNone=True)

    # XXX we need MEDIUMBLOB for MySQL, but not for SQLite and
    # possibly something else for other DBs
    data = StringCol() #sqlType="MEDIUMBLOB"
    
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
    # XXX What if this is legit, ie, genuine duplicate data?
    for m in Media.select(Media.q.hash == hash, orderBy='sequence', lazyColumns=lazycol):
        #print 'deleting hash id (%d,%s,%d)' % (m.id, m.hash, m.sequence)
        m.destroySelf()
    
    while len(data) > 0:
        #print 'inserting hash %s seq %d, datasize=%d, chunksize=%d' % (hash, order, len(data), len(data[:_chunksize]))
        m = Media(data=data[:_chunksize], hash=hash, sequence=order)
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

    m = Media.get(id)
        
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

    collection = ForeignKey('Collection')

class Picture(SQLObject):
    "Pictures - including movies and other media"

    def getimage(self, verify=False):
        return getmedia(self.mediaid, verify)

    def getimagechunks(self):
        return getmediachunks(self.hash)
    
    def getthumb(self, verify=False):
        #print 'id=%d thumbid=%d' % (self.id, self.thumbid)
        return getmedia(self.thumbid, verify)

##    def converttime(self, timestr):
##        print 'class=%s timestr=%s' % (timestr.class, timestr)
##        try:
##            return mx.DateTime.strptime(str(timestr), '%Y-%m-%d %H:%M:%S')
##        except:
##            return mx.DateTime.strptime(str(timestr), '%Y-%m-%d %H:%M:%S.00')

##    def _get_record_time(self):
##        return self.converttime(self._SO_get_record_time())

##    def _get_modified_time(self):
##        return self.converttime(self._SO_get_modified_time())

    hash = StringCol(length=40, varchar=False, notNone=True, unique=True, alternateID=True)
    mimetype = StringCol(notNone=True, length=40)

    datasize = IntCol(notNone=True)
    mediaid = ForeignKey("Media", unique=True)
    link = ForeignKey("Picture", default=None)

    collection = ForeignKey('Collection', notNone=True, default=lambda: defaultCollection().id)
    keywords = RelatedJoin('Keyword')
    comments = MultipleJoin('Comment')
    
    camera = ForeignKey('Camera', default=None)
    
    owner = ForeignKey("User", default=None)
    visibility = EnumCol(enumValues=["public","private"], default="public", notNone=True)
    photographer = ForeignKey('User', default=None)

    title = StringCol(length=127,default='')
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
    flash = BoolCol(default=False)
    f_number = StringCol(default=None, length=10)
    exposure_time = StringCol(default=None, length=10) # actually an EXIF.Ratio
    exposure_bias = IntCol(default=0)
    brightness = IntCol(default=None)
    focal_length = IntCol(default=0)

    # This is present on imaged imported from Imagestore1
    md5hash = StringCol(length=32, varchar=False, default=None)

class Comment(SQLObject):
    user = ForeignKey('User')
    picture = ForeignKey('Picture')
    timestamp = DateTimeCol(default=mx.DateTime.gmt, notNone=True)

    comment = StringCol(notNone=True)
    

Collection.createTable(ifNotExists=True)
CollectionPerms.createTable(ifNotExists=True)
Picture.createTable(ifNotExists=True)
Comment.createTable(ifNotExists=True)
Media.createTable(ifNotExists=True)
Keyword.createTable(ifNotExists=True)
User.createTable(ifNotExists=True)
Camera.createTable(ifNotExists=True)

if User.select(User.q.username == 'admin').count() == 0:
    User(username='admin', password='admin', email='jeremy@goop.org',
         fullname='Administrator',
         mayAdmin=True, mayViewall=True, mayUpload=True, mayComment=False,
         mayCreateCat=True)
if Collection.select(Collection.q.name == 'default').count() == 0:
    Collection(name='default', owner=User.byUsername('admin'), description='The default collection')

