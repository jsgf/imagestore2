import getopt
from dircache import listdir
from os.path import isfile, isdir
from string import split
import os.path, sys
import Image
from mx.DateTime import DateTime
from StringIO import StringIO

import sqlobject as SQLObject
import EXIF

from db import *

from ImageTransform import data_from_Image, Image_from_data

debug=True
quiet=False

_ignore = {
    'XVThumb': 1
}

_mimetypes = {
    'JPEG': 'image/jpeg',
    }

class ImportException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

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

def thumbnail(image, size):
    (x, y) = image.size

    if x > size[0]: y = y * size[0] / x; x = size[0]
    if y > size[1]: x = x * size[1] / y; y = size[1]
    size = (x, y)

    #print 'size=(%d, %d)' % size

    if size == image.size:
        return image

    return image.resize(size, resample=Image.ANTIALIAS)

def import_file(filename, owner, public, catalogue, keywords=[], **imgattr):
    data = open(filename, 'r').read()
    return import_image(data, owner, public, catalogue, **imgattr)

def import_image(imgdata, owner, public, catalogue, keywords=[], **imgattr):
    imgfile = StringIO(imgdata)

    try:
        img = Image_from_data(imgdata)
    except IOError:
        raise ImportException('Unsupported file type')
    
    if _ignore.has_key(img.format):
	return -1

    sha1 = sha.new(imgdata)
    hash=sha1.digest().encode('hex')

    s = Picture.select(Picture.q.hash==hash)
    if s.count() != 0:
        raise ImportException('already present: %d' % s[0].id)
        
    try:
        m = setmedia(imgdata)

        if False:
            data = getmedia(m.id, True)
            file("t.jpg", 'wb').write(data)

        thumbdata=None
        
        if img.format == 'JPEG':
            imgfile.seek(0)
            imgattr = get_EXIF_metadata(imgfile, imgattr)
            if imgattr.has_key('thumbnail'):
                thumbdata = imgattr['thumbnail']
                del imgattr['thumbnail']
            #print 'imgattr=%s' % imgattr
            
        if thumbdata is None:
            print "(generating thumbnail)",
            thimg=thumbnail(img, (160,160))
            thumbdata=data_from_Image(thimg, 'JPEG', quality=70, optimize=1)
            open('thumb.jpg', 'wb').write(thumbdata)

        thumb=setmedia(thumbdata)
        thimg=Image_from_data(thumbdata)

        if False:
            print "thumb size=(%d,%d)" % thimg.size        
            open('thumb.jpg', 'wb').write(thumbdata)

        width,height = img.size
        th_width,th_height = thimg.size

        pic = Picture(owner=owner,
                      visibility=public,
                      hash=m.hash,
                      media=m,
                      datasize=len(imgdata),
                      mimetype=_mimetypes[img.format],
                      width=width,
                      height=height,
                      thumb=thumb,
                      th_width=th_width,
                      th_height=th_height,
                      **imgattr)

        add_keywords(catalogue, pic, keywords)
    except Exception, x:
        print 'exception '% x
        print "(rollback)"
        raise

    return pic.id

def handle_file(file, owner, catalogue, public):
    if not quiet:
	print 'Processing %s... ' % file,

    try:
        ret = import_file(file, owner, public, catalogue,
                          photographer=owner)
    except ImportException, x:
        ret = '(%s)' % x
        
    if not quiet:
	print ret

def handle_dir(dir, owner, catalogue, public):
    if isfile(dir):
        handle_file(dir, owner, public, catalogue)
        return

    if not isdir(dir):
        return

    for f in listdir(dir):
        if f == '.' or f == '..':
            continue
        f = os.path.join(dir, f)
        if isdir(f):
            handle_dir(f, owner, public, catalogue)
        elif isfile(f):
            handle_file(f, owner, public, catalogue)

def add_keywords(cat, image, keywords=[]):
    for k in keywords:
        try:
            kw = Keyword.byWord(k)
        except SQLObjectNotFound, x:
            kw = Keyword(word=k, catalogue=cat)

        image.addKeyword(kw)
        cat.addKeyword(kw)
        
def get_user(username, email, fullname):
    u=User.select(User.q.username==username)
    if u.count() != 0:
        return u[0]
    return User(username=username, fullname=fullname, email=email)

if __name__ == '__main__':
    optlist, args = getopt.getopt(sys.argv[1:], 'o:p:qh')
    owner = get_user(username='jeremy', email='jeremy@goop.org', fullname='Jeremy Fitzhardinge')
    catalogue = defaultCat()
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
            catalogue = Catalogue.byName(v)
            
    for arg in args:
        handle_dir(arg, owner, public, catalogue)

__all__ = [ 'import_file',
            'import_image',
            'handle_file',
            'handle_dir',
            'add_keywords',
            'get_user' ]
