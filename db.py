from SQLObject import *
from EXIF import Ratio
import sha
import mx.DateTime

conn = SQLiteConnection('imagestore.db', debug=0)
__connection__ = conn

_encode_media=True                      # use base64 for binary data (sqlite needs it)
_chunksize=512*1024                     # chunk Media into lumps

class User(SQLObject):
    "Imagestore user database"
    
    username = StringCol(length=100, unique=True, notNone=True)
    password = StringCol(length=32, default=None)
    fullname = StringCol(default=None)

    admin = BoolCol(notNone=True,default=False)
    viewall = BoolCol(notNone=True,default=False)
    upload = BoolCol(notNone=True,default=False)
    
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
    while len(data) > 0:
        m = Media.new(data=data[:_chunksize], hash=hash, sequence=order)
        data=data[_chunksize:]
        order += 1
        if media is None:
            media = m
        
    return media

def getmediachunk(hash):
    """Generator to return each successive chunk of Media data id"""

    for c in Media.select(Media.q.hash==hash, orderBy='sequence'):
        #print "chunk id=%d, seq=%d, len=%d" % (c.id, c.sequence, len(c.data))
        yield c.data

def getmedia(id, verify=False):
    """Return media data for id"""
    
    data=''
    sha1 = sha.new()
    m = Media(id)
    for d in getmediachunk(m.hash):
        if verify:
            sha1.update(d)
        data = data+d

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

class Picture(SQLObject):
    "Pictures - including movies and other media"
    
    hash = StringCol(length=40, varchar=False, notNone=True, unique=True, alternateID=True)
    mimetype = StringCol(notNone=True, length=40)

    mediaid = ForeignKey("Media")
    link = ForeignKey("Picture", default=None)

    keywords = RelatedJoin('Keyword')
    comments = MultipleJoin('Comment')
    
    camera = ForeignKey('Camera', default=None)
    
    owner = ForeignKey("User", default=None)
    visibility = EnumCol(enumValues=["public","private"], default="public", notNone=True)
    photographer = ForeignKey('User', default=None)
    
    description = StringCol(default=None)
    copyright = StringCol(default=None)
    
    width = IntCol()
    height = IntCol()
    orientation = IntCol()

    thumbid = ForeignKey("Media", default=None)
    th_width = IntCol(default=None)
    th_height = IntCol(default=None)
    
    record_time = DateTimeCol()
    modified_time = DateTimeCol(default=mx.DateTime.now)

    exposure_program = StringCol(default=None)
    flash = BoolCol()
    f_number = StringCol(length=10)
    exposure_time = FloatCol()
    exposure_bias = IntCol()
    brightness = IntCol(default=None)
    focal_length = IntCol()

class Comment(SQLObject):
    user = ForeignKey('User')
    picture = ForeignKey('Picture')
    comment = StringCol()


Picture.createTable(ifNotExists=True)
Comment.createTable(ifNotExists=True)
Media.createTable(ifNotExists=True)
Keyword.createTable(ifNotExists=True)
User.createTable(ifNotExists=True)
Camera.createTable(ifNotExists=True)
