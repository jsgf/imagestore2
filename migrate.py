#!/usr/bin/python

# Migrate from imagestore1 to imagestore2

import db
import MySQLdb
import sha, md5
import mx.DateTime

from SQLObject import *

#conn = MySQLConnection(host='127.0.0.1', db='imagestore', user='root', passwd='zwarp', debug=0)
conn = MySQLConnection(host='lurch', db='imagestore', user='imagestore', passwd='im_zwarp', debug=0)

__connection__ = conn

class MigImages(SQLObject):
    _table = 'images'
    _idName = 'img_id'

    image = StringCol(dbName='image', sqlType='MEDIUMBLOB', notNone=True)
    thumbnail = StringCol(dbName='thumbnail', sqlType='blob')
    mime_type = StringCol(length=32, dbName='mime_type')
    width = IntCol()
    height = IntCol()
    orientation = IntCol()
    camera_make = StringCol(length=32)
    record_time = DateTimeCol(dbName='create_time')
    modified_time = DateTimeCol(sqlType='timestamp')
    description = StringCol()
    comment = StringCol(length=127)
    copyright = StringCol(length=127)
    photographer = StringCol(length=127)
    exposure_time = StringCol(length=10)
    brightness = FloatCol()
    f_number = FloatCol()
    focal_length = IntCol()
    exposure_bias = IntCol()
    flash = EnumCol(enumValues=['y','n'])
    thumb_width = IntCol()
    thumb_height = IntCol()
    title = StringCol(length=127)
    #owner = ForeignKey('User')
    owner = IntCol()
    visible = EnumCol(enumValues=['public','private'])
    hash2 = StringCol(length=32, alternateID=True, unique=True)

class MigUser(SQLObject):
    _table = 'users'
    _idName = 'user_id'

    user_name=StringCol(length=127, alternateID=True)
    user_email=StringCol(length=127)
    passwd=StringCol(length=16)
    user_flags=IntCol()

class MigKeywords(SQLObject):
    _table = 'keywords'
    _idName = 'word_id'

    word = StringCol(length=127, alternateID=True)

class MigKeyImage(SQLObject):
    _table = 'image_kw'
    _idName = 'id'
    
    word_id = IntCol()
    img_id = IntCol()

catalogue = db.defaultCat()

import db, insert

for migp in MigImages.select():
    print 'migp %d: %s: image data=%d' % (migp.id, migp.record_time, len(migp.image))
    
    hash = md5.new()
    hash.update(migp.image)
    if migp.hash2 != hash.digest().encode('hex'):
        print 'WARNING: migrated image %d has bad md5 hash: has %s, expected %s' % (migp.id, migp.hash2, hash.digest().encode('hex'))

    owner = migp.owner
    if owner == 0:
        owner = 1
    mig_owner = MigUser(owner)
    u = insert.get_user(mig_owner.user_email, mig_owner.user_email, mig_owner.user_name)
    u.password = mig_owner.passwd

    if migp.photographer is not None:
        photog = insert.get_user(migp.photographer, migp.photographer, None)

    kwlist = MigKeywords.select(AND(MigKeyImage.q.word_id == MigKeywords.q.id,
                                    MigKeyImage.q.img_id == migp.id))
    kw = []
    for k in kwlist:
        kw.append(k.word)
    print '     %d keywords: %s' % (migp.id, kw)

    try :
        pid = insert.import_image(migp.image, u, migp.visible == 'public',
                                  keywords = kw,
                                  id = migp.id,              # preserve ID
                                  catalogue = catalogue,
                                  record_time = migp.record_time,
                                  photographer = photog,
                                  description = migp.description,
                                  title = migp.title,
                                  orientation = migp.orientation,
                                  copyright = migp.copyright)
    except:
        pid = -1
        print 'Import failed?'

    if pid > 0:
        p = db.Picture.get(pid)

        p.getimage(True)
        p.getthumb(True)

    # Add any comments
    if migp.comment is not None and migp.comment.strip() != '':
        c = db.Comment.new(user=0, picture=p, comment=migp.comment, timestamp=migp.modified_time)
    
