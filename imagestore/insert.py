import getopt
from dircache import listdir
from os.path import isfile, isdir, splitext
from os import stat
import os.path
from sys import argv
from string import split
import Image
from mx.DateTime import DateTime, localtime
from cStringIO import StringIO

import sqlobject as SQLObject
import EXIF

import imagestore.db as db

from ImageTransform import data_from_Image, Image_from_data

debug=True
quiet=False

_ignore = {
    'XVThumb': 1
}

# Map from filename extensions to mimetypes
_ext_map = {}

# Map from mimetypes to Importers
_type_map = {}

def find_importer_ext(file):
    ext = splitext(file)[1]

    if not ext:
        return None

    if ext[0] == '.':
        ext = ext[1:]

    ext = ext.lower()

    try:
        return find_importer_type(_ext_map[ext])
    except KeyError:
        return None

def find_importer_data(data):
    img = Image_from_data(data)
    mime = Image.MIME[img.format]
    return find_importer_type(mime)

def find_importer_type(mime):
    try:
        return _type_map[mime]
    except KeyError:
        return None

def update_maps(map, importer):
    for k in map.keys():
        for e in map[k]:
            _ext_map[e] = k
        _type_map[k] = importer

class Importer:
    def import_file(self, filename, owner, public, collection, mimetype=None, keywords=[], **imgattr):
        # If we have no better information, assume the record time is the
        # earliest timestamp on the file itself
        st = stat(filename)
        record_time = localtime(min(st.st_mtime, st.st_ctime))
        imgattr['record_time'] = record_time
        
        data = open(filename).read()
        return self.import_image(data, owner, public, collection, mimetype=mimetype, keywords=[], **imgattr)

class StillImageImporter(Importer):

    # Types which Image could possibly find but we don't want it to deal with
    image_ignore = {
        'XVThumb': 1,
        'MPEG': 1,
        }

    def import_image(self, imgdata, owner, public, collection, mimetype=None, keywords=None, **imgattr):
        imgfile = StringIO(imgdata)

        keywords = keywords or None
        try:
            img = Image.open(imgfile)
        except IOError:
            raise ImportException('Unsupported file type')

        if self.image_ignore.has_key(img.format):
            return -1

        sha1 = sha.new(imgdata)
        hash=sha1.digest().encode('hex')

        s = db.Picture.select(db.Picture.q.hash==hash)
        if s.count() != 0:
            raise AlreadyPresentException('%d' % s[0].id)

        try:
            m = setmedia(imgdata)

            if False:
                data = getmedia(m.id, True)
                file("t.jpg", 'wb').write(data)

            thumbdata=None

            if img.format == 'JPEG' or img.format == 'TIFF':
                imgfile.seek(0)
                imgattr = get_EXIF_metadata(imgfile, imgattr)
                if imgattr.has_key('thumbnail'):
                    thumbdata = imgattr['thumbnail']
                    del imgattr['thumbnail']
                #print 'imgattr=%s' % imgattr

            if thumbdata is None:
                print "(generating thumbnail)",
                thimg = img.copy()
                thimg.thumbnail((160,160), Image.ANTIALIAS)
                thumbdata = data_from_Image(thimg, 'JPEG', quality=70, optimize=1)
                #open('thumb.jpg', 'wb').write(thumbdata)

            thumb=setmedia(thumbdata)
            th_img=Image_from_data(thumbdata)

            if False:
                print "thumb size=(%d,%d)" % th_img.size        
                open('thumb.jpg', 'wb').write(thumbdata)

            width,height = img.size
            th_width,th_height = th_img.size

            pic = db.Picture(owner=owner,
                             visibility=public,
                             collection=collection,
                             hash=m.hash,
                             media=m,
                             datasize=len(imgdata),
                             mimetype=mimetype or Image.MIME[img.format],
                             width=width,
                             height=height,
                             thumb=thumb,
                             th_width=th_width,
                             th_height=th_height,
                             **imgattr)

            add_keywords(collection, pic, keywords)
        except Exception, x:
            print 'exception '% x
            print "(rollback)"
            raise

        pic.expire();
        return pic.id

update_maps({
    'image/jpeg':   [ 'jpg', 'jpeg', 'pjpeg' ],
    'image/pjpeg':  [ 'jpg', 'jpeg', 'pjpeg' ],
    'image/tiff':   [ 'tif', 'tiff' ],
    'image/png':    [ 'png' ],
    'image/gif':    [ 'gif' ],      # ?!
    }, StillImageImporter)


class MPEGImporter(Importer):
    def import_image(self, imgdata, owner, public, collection, mimetype=None, keywords=[], **imgattr):
        sha1 = sha.new(imgdata)
        hash = sha1.digest().encode('hex')

        s = db.Picture.select(db.Picture.q.hash == hash)
        if s.count() != 0:
            raise AlreadyPresentException('%d' % s[0].id)

        try:
            m = setmedia(imgdata)

            thumbdata = open('static/thumb-mpeg.jpg').read()
            th_img = Image_from_data(thumbdata)
            thumb = setmedia(thumbdata)

            width, height = (320, 240)  # XXX FIXME
            th_width, th_height = th_img.size

            pic = db.Picture(owner=owner,
                             visibility=public,
                             collection=collection,
                             hash=m.hash,
                             media=m,
                             datasize=len(imgdata),
                             mimetype=mimetype or 'video/mpeg',
                             width=width,
                             height=height,
                             thumb=thumb,
                             th_width=th_width,
                             th_height=th_height,
                             **imgattr)
            add_keywords(collection, pic, keywords)
        except Exception, x:
            print 'exception '% x
            print "(rollback)"
            raise

        return pic.id
    
update_maps({
    'video/mpeg':   [ 'mpg', 'mpeg' ],
    'video/quicktime':   [ 'mov' ],
    }, MPEGImporter)


class ImportException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

class AlreadyPresentException(ImportException):
    def __init__(self, value):
        ImportException.__init__(self, value)
        
def mkDateTime(s):
    s=str(s)
    return mx.DateTime.strptime(s, '%Y:%m:%d %H:%M:%S')

def get_EXIF_metadata(file, imgattr):
    exif = EXIF.process_file(file, 0)

    #print 'exif=%s' % exif
    
    if exif is None:
        return
    
    attrmap = {
        # Who, where, when, what
        'record_time':		[ 'EXIF DateTimeDigitized',
                                  'EXIF DateTimeOriginal',
                                  'Image DateTime' ],
        #'copyright':		[ 'Copyright' ],
        'photographer':		[ 'Image Artist' ],
        'description':		[ 'Image ImageDescription' ],
        #'comment':		[ 'Image UserComment' ],
        
        # Exposure details
        'exposure_time':	[ 'EXIF ExposureTime',
                                  'EXIF ShutterSpeedValue' ],
        'f_number':		[ 'EXIF FNumber',
                                  'EXIF ApertureValue' ],
        'focal_length':		[ 'EXIF FocalLength' ],
        'exposure_bias':	[ 'EXIF ExposureBiasValue' ],
        'flash':		[ 'EXIF Flash' ],
        'brightness':		[ 'EXIF BrightnessValue' ],
        'exposure_program':     [ 'EXIF ExposureProgram' ],
        
        'thumbnail':            [ 'JPEGThumbnail' ],

        'manufacturer':         [ 'IFD Make' ],
        'model':                [ 'IFD Model' ],
        
        # Image orientation (size comes from outer info)
        'orientation':		[ 'Image Orientation' ],

    }

    typemap = {
        'record_time':          mkDateTime,
        'orientation':          lambda o: { 1:0, 3: 180, 6: 270, 8: 90, 9: 0 }[int(str(o))]
    }

    # These fields are overridden, even if the EXIF has info, since
    # the camera often doesn't know
    override = ('orientation')
    
    for a in attrmap.keys():
        if imgattr.has_key(a) and a in override:
            continue
        for e in attrmap[a]:
            if exif.has_key(e) and exif[e] is not None:
                #print "a=%s e=%s" % (a, e)
                v = exif[e]
                if typemap.has_key(a):
                    v = typemap[a](v)
                imgattr[a] = v
                break

    if debug:
        pass
        #print 'imgattr= ', imgattr, 'hash=', hash

    return imgattr

def handle_file(file, owner, collection, public):
    if not quiet:
	print 'Processing %s... ' % file,

    try:
        importer = find_importer(file)

        if importer is not None:
            importer = importer()
            
            ret = importer.import_file(file, owner, public, collection,
                                       photographer=owner)
        else:
            ret = '(unknown extension)'
            
    except ImportException, x:
        ret = '(%s)' % x
        
    if not quiet:
	print ret

def handle_dir(dir, owner, collection, public):
    if isfile(dir):
        handle_file(dir, owner, public, collection)
        return

    if not isdir(dir):
        return

    for f in listdir(dir):
        if f == '.' or f == '..':
            continue
        f = os.path.join(dir, f)
        if isdir(f):
            handle_dir(f, owner, public, collection)
        elif isfile(f):
            handle_file(f, owner, public, collection)

def add_keywords(coll, image, keywords=None):
    keywords = keywords or []
    for k in keywords:
        try:
            kw = db.Keyword.byWord(k)
        except SQLObjectNotFound, x:
            kw = db.Keyword(word=k, collection=coll)

        image.addKeyword(kw)
        coll.addKeyword(kw)
        
def get_user(username, email, fullname):
    u=db.User.select(db.User.q.username==username)
    if u.count() != 0:
        return u[0]
    return db.User(username=username, fullname=fullname, email=email)

def import_image(data, owner, orig_filename, public, collection, keywords, mimetype=None, **attr):
    #print 'import_image(orig_filename=%s, mimetype=%s)' % (orig_filename,mimetype)
    if mimetype is not None:
        importer = find_importer_type(mimetype)
    else:
        importer = find_importer_ext(orig_filename)
    if importer is None:
        raise ImportException('Unknown file type')
    
    return importer().import_image(data, owner, public, collection, mimetype=mimetype, keywords=keywords, **attr)
    
if __name__ == '__main__':
    optlist, args = getopt.getopt(argv[1:], 'o:p:qh')
    owner = get_user(username='jeremy', email='jeremy@goop.org', fullname='Jeremy Fitzhardinge')
    collection = db.defaultCollection()
    public='public'

    for opt in optlist:
        o,v = opt
        if o == '-o':
            owner = v;
	if o == '-p' and (v == 'public' or v == 'private'):
	    public = v;
	if o == '-q':
	    quiet=1
	if o == '-h':
	    printhash=1
        if o == '-c':
            collection = db.Collection.byName(v)
            
    for arg in args:
        handle_dir(arg, owner, public, collection)

__all__ = ['import_image',
            'handle_file',
            'handle_dir',
            'add_keywords',
            'get_user' ]
