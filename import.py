import getopt
from dircache import listdir
from os.path import isfile, isdir
import os.path
import sys
import Image
from ArrayStream import ArrayStream
from db import *
import SQLObject
import EXIF

debug=True
quiet=False

ignore = {
    'XVThumb': 1
}

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
        'exposure_time':	[ 'EXIF ExposureTime' ],
        'f_number':		[ 'EXIF FNumber' ],
        'focal_length':		[ 'EXIF FocalLength' ],
        'exposure_bias':	[ 'EXIF ExposureBiasValue' ],
        'flash':		[ 'EXIF Flash' ],
        'brightness':		[ 'EXIF BrightnessValue' ],
        'exposure_program':     [ 'EXIF ExposureProgram' ],
        
        'thumbnail':            [ 'JPEGThumbnail' ],
        
        # Image orientation (size comes from outer info)
        'orientation':		[ 'Image Orientation' ],
    }

    for a in attrmap.keys():
        for e in attrmap[a]:
            if exif.has_key(e) and exif[e] is not None:
                #print "a=%s e=%s" % (a, e)
                imgattr[a] = exif[e]
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

def data_from_Image(image, format, **kw):
    data=ArrayStream()
    image.save(data, format, **kw)
    return data.data()

def Image_from_data(data, *kw):
    data=ArrayStream(data)
    return Image.open(data, *kw)

def getimage(filename, owner, public, **imgattr):
    try:
	img = Image.open(filename)
    except IOError:
	return 'I/O error'

    if ignore.has_key(img.format):
	return 'unwanted type'

    imgfile = open(filename, 'r')
    imgdata = imgfile.read()

    sha1 = sha.new(imgdata)
    hash=sha1.digest().encode('hex')

    s = Picture.select(Picture.q.hash==hash)
    if s.count() != 0:
        print "(already present) ",
        return s[0].id
        
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

        pic = Picture.new(owner=owner,
                          visibility=public,
                          hash=m.hash,
                          media=m,
                          mimetype='image/jpeg',
                          width=width,
                          height=height,
                          thumb=thumb,
                          th_width=th_width,
                          th_height=th_height,
                          **imgattr)
    except:
        print "(rollback)"
        raise

    return pic.id

def handlefile(file, owner, public):
    if not quiet:
	print 'Processing %s... ' % file,
    ret = getimage(file, owner, public,
                   photographer=owner)
    if not quiet:
	print ret

def handledir(dir, owner, public):
    if isfile(dir):
        handlefile(dir, owner, public)
        return

    if not isdir(dir):
        return

    for f in listdir(dir):
        if f == '.' or f == '..':
            continue
        f = os.path.join(dir, f)
        if isdir(f):
            handledir(f, owner, public)
        elif isfile(f):
            handlefile(f, owner, public)

def getuser(username):
    u=User.select(User.q.username==username)
    if u.count() != 0:
        return u[0]
    return User.new(username=username)

if __name__ == '__main__':
    optlist, args = getopt.getopt(sys.argv[1:], 'o:p:qh')
    owner = getuser('jeremy@goop.org')
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
        
    for arg in args:
        handledir(arg, owner, public)
