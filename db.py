from sqlobject import *
from EXIF import Ratio
import sha
import mx.DateTime
import os.path

lazycol=True

dbinfo = {
    'lurch':    { 'conn': 'mysql://imagestore:im_zwarp@lurch/imagestore2',
                  'encode': False,
                  },
    'lurch-local':    { 'conn': 'mysql://imagestore@localhost/imagestore2',
                  'encode': False,
                  },
    'local':    { 'conn': 'sqlite:' + os.path.abspath('imagestore.db'),
                  'encode': True,
                  },
    'localmysql':{ 'conn': 'mysql://imagestore@localhost/imagestore2',
                  'encode': False,
                  },
    }

#db='localmysql'
#db='local'
db='lurch-local'

conn = None

def db_connect():
    global conn, __connection__
    print 'path='+dbinfo[db]['conn']
    uri=dbinfo[db]['conn']

    # disable caching
    uri += '?cache=0'
    
    conn = connectionForURI(uri)
    conn.debug = 0
    __connection__ = conn

    # Create tables if necessary
    for c in [ Collection, CollectionPerms, Picture, Comment,
               Media, Keyword, User, Camera, Upload ]:
        #print 'c=%s' % c
        c.setConnection(conn)
	if not conn.tableExists(c._table):
	    c.createTable(ifNotExists=True)
            if c == Media and conn.dbName == 'mysql':
                # allow media table to grow big
                conn.query('alter table media max_rows=10000000 avg_row_length=%d' % _chunksize)

    # Create a default user and collection
    if User.select(User.q.username == 'admin').count() == 0:
        User(username='admin', password='admin', email='jeremy@goop.org',
             fullname='Administrator',
             mayAdmin=True, mayViewall=True, mayUpload=True, mayComment=False,
             mayCreateCat=True)
    if Collection.select(Collection.q.name == 'default').count() == 0:
        Collection(name='default', owner=User.byUsername('admin'),
                   description='The default collection')

    #print 'connection: %s' % conn

_encode_media=dbinfo[db]['encode']      # use base64 for binary data (sqlite needs it)
_chunksize=63*1024                      # chunk Media into lumps

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
    visibility = EnumCol(enumValues=["public","restricted","private"],
                         default="public", notNone=True)

    # Whether to allow anonymous/non-privileged users to see original image files
    showOriginal = BoolCol(notNone=True, default=False)

    # Pictures in this collection
    pictures = MultipleJoin('Picture')

    def permissions(self, user):
        if user is None:
            return None
        
        cp = CollectionPerms.select((CollectionPerms.q.collectionID == self.id) & (CollectionPerms.q.userID == user.id)).distinct()
        assert cp.count() == 0 or cp.count() == 1, 'Unexpected number of collection permissions'

        if cp.count() == 0 or not cp[0].mayView:
            return None
        return cp[0]
    
class CollectionPerms(SQLObject):
    "Per-Collection user permissions"
    user = ForeignKey('User')
    collection = ForeignKey('collection')

    mayAdmin = BoolCol(notNone=True, default=False)     # update ACL
    mayViewall = BoolCol(notNone=True, default=False)   # view all images
    mayView = BoolCol(notNone=True, default=True)       # view public images
    mayViewRestricted = BoolCol(notNone=True, default=False) # view restricted images
    mayUpload = BoolCol(notNone=True, default=False)    # upload new images
    mayComment = BoolCol(notNone=True, default=False)   # add comments to images
    mayEdit = BoolCol(notNone=True, default=False)      # edit image metadata
    mayCurate = BoolCol(notNone=True, default=False)    # administer keywords
    
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
    mayRate = BoolCol(notNone=True, default=False)      # may rate pictures

    enabled = BoolCol(notNone=True, default=True)
    
    
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

    _cacheValues = False

    hash = StringCol(length=40, varchar=False, notNone=True)
    sequence = IntCol(notNone=True)

    idx = Index((hash,sequence), unique=True)

    # XXX we need MEDIUMBLOB for MySQL, but not for SQLite and
    # possibly something else for other DBs
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
    """ Add a new piece of data to the Media table, possibly chunking
    and encoding it if necessary.  If the data already exists (same
    hash), then just that (after verifying for integrity, since it
    could be a left over from a failed previous attempt.
    """
    debug = False
    
    if hash is None:
        sha1 = sha.new(data)
        hash = sha1.digest().encode('hex')

    order = 0
    media=None
    m=None
    
    # Make sure there's no old/partial/existing pieces of this data
    try:
        # get the ID for this hash
        m = Media.select(Media.q.hash == hash, orderBy='sequence')[0]

        # verify its integrity
        verifymedia(m.id)

        if debug:
            print 'media already present for %s -> %d' % (hash, m.id)

        return m                        # OK, already here
    except:
        if debug:
            if m is None:
                print 'media missing for %s (adding)' % hash
            else:
                print 'media corrupted for %d/%s (replacing)' % (m.id, hash)
            
        # It didn't exist, or was corrupt
        pass

    # Make sure we're not about to trash someone's image/thumbnail data
    if m is not None:
        pics = Picture.select((Picture.q.mediaid == m.id) | (Picture.q.thumbid == m.id))
        if pics.count() != 0:
            raise IOError('CONSISTENCY PROBLEM: Found pictures using corrupt media (hash=%s, images: %s)' % (hash, ', '.join([ str(p.id) for p in pics])))
    
    # Just make sure there were no left-overs
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

def verifymedia(id):
    """Verify that all the media chunks are there; returns nothing on
    success, exception on error"""    
    m = Media.get(id)
    sha1 = sha.new()

    for d in getmediachunks(m.hash):
        sha1.update(d)
    hash = sha1.digest().encode('hex')
    if hash != m.hash:
        raise IOError, 'Media %d data is corrupt: expect SHA1 %s, got %s' % \
              (id, m.hash, hash)

def getmedia(id, verify=False):
    """Return media data for id"""
    
    m = Media.get(id)

    if verify:
        sha1 = sha.new()

    data=[]
    for d in getmediachunks(m.hash):
        if verify:
            sha1.update(d)
        data.append(d)

    if verify:
        myhash = sha1.digest().encode('hex')
        if myhash != m.hash:
            raise IOError, 'Media %d data is corrupt: expect SHA1 %s, got %s' % \
                  (id, m.hash, myhash)
    
    return ''.join(data)

class Keyword(SQLObject):
    "Picture keywords"

    word = StringCol(length=50, unique=True, notNone=True, alternateID=True)
    pictures = RelatedJoin('Picture')

    collection = ForeignKey('Collection', notNone=True)

def strToKeyword(word, collection, create):
    try:
        word = Keyword.byWord(word)
    except SQLObjectNotFound:
        if create:
            word = Keyword(word=word, collection=collection)
        else:
            word = None
    return word


class Picture(SQLObject):
    "Pictures - including movies and other media"

    def getimage(self, verify=False):
        return getmedia(self.mediaid, verify)

    def getimagechunks(self):
        return getmediachunks(self.hash)
    
    def getthumb(self, verify=False):
        #print 'id=%d thumbid=%d' % (self.id, self.thumbid)
        return getmedia(self.thumbid, verify)


    def mayView(self, user):
        if self.visibility == 'public':
            return True

        if user is None:
            return False
        
        if user.mayViewall or user.mayAdmin:
            return True
        
        if self.owner == user:
            return True

        return False

    def mayEdit(self, user):
        if user is None:
            return False
        
        if self.owner == user:
            return True
        if user.mayAdmin:
            return True

        return False

    def isPending(self):
        return self.uploadID is not None

    def addKeywords(self, kwlist):
        " Add a list of keywords to this Picture "
        kwlist = [ strToKeyword(k, self.collection, True) for k in kwlist ]
        for k in kwlist:
            if k not in self.keywords:
                self.addKeyword(k)
                
    def delKeywords(self, kwlist):
        " Remove a list of keywords from this Picture "
        kwlist = [ strToKeyword(k, self.collection, False) for k in kwlist ]
        kwlist = [ k for k in kwlist if k is not None ]
        for k in self.keywords:
            if k in kwlist:
                self.removeKeyword(k)
                
    def setKeywords(self, kwlist):
        " Set the Picture's keywords to list "
        kwlist = [ strToKeyword(k, self.collection, True) for k in kwlist ]
        
        for k in self.keywords:
            if k not in kwlist:
                self.removeKeyword(k)

        for k in kwlist:
            if k not in self.keywords:
                self.addKeyword(k)

    hash = StringCol(length=40, varchar=False, notNone=True, unique=True, alternateID=True)
    mimetype = StringCol(notNone=True, length=40)

    datasize = IntCol(notNone=True)
    mediaid = ForeignKey("Media", unique=True)
    link = ForeignKey("Picture", default=None)

    collection = ForeignKey('Collection', notNone=True)
    keywords = RelatedJoin('Keyword')
    comments = MultipleJoin('Comment')

    # If non-NULL, then this picture is still pending, and doesn't really
    # exist in the collection
    upload = ForeignKey('Upload', default=None)

    camera = ForeignKey('Camera', default=None)
    
    owner = ForeignKey("User", default=None)
    visibility = EnumCol(enumValues=["public", "restricted" ,"private"],
                         default="public", notNone=True)
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

    owner_idx = Index(owner)
    date_idx = Index(record_time)
    mod_idx = Index(modified_time)
    vis_idx = Index(visibility)
    md5_idx = Index(md5hash)
    rating_idx = Index(rating)

class Comment(SQLObject):
    user = ForeignKey('User')
    picture = ForeignKey('Picture')
    timestamp = DateTimeCol(default=mx.DateTime.gmt, notNone=True)

    comment = StringCol(notNone=True)
    
class Upload(SQLObject):
    user = ForeignKey('User')
    collection = ForeignKey('Collection')
    pictures = MultipleJoin('Picture')

    import_time = DateTimeCol(default=mx.DateTime.gmt, notNone=True)

    time_idx = Index(import_time)
    user_idx = Index(user)


