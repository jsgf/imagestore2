import db
import sha
import tempfile
from StringIO import StringIO
import Image

from os import popen,stat
from select import select

####################
# Config variables
####################

# ImageMagick "convert"
convert='/usr/bin/convert'

# IJG jpegtran
jpegtran='/usr/bin/jpegtran'

# Cache directory
cachedir="cache"

# Font
font = "/usr/share/fonts/bitstream-vera/Vera.ttf"
        
sizes = { 'thumb':      (160, 160),
          'tiny':       (320, 240),
          'small':      (640, 480),
          'medium':     (800, 600),
          'large':      (1024, 768),
          'full':       (10000, 10000),
          }

# map types to extensions
extmap = { 'image/jpeg':    'jpg',
           'image/tiff':    'tif',
           }
# map extensions to types
typemap = { 'jpg':          'image/jpeg',
            'jpeg':         'image/jpeg',
            'tiff':         'image/tiff',
            'tif':          'image/tiff',
            }

# Given an image ID and size, return a file handle to a stream
# containing the transformed image.  The image will always be
# 'image/jpeg'
def transform(id, size = 'medium'):
    debug=False

    p = db.Picture.get(id)
    (tw, th) = sizes[size]

    if size == 'thumb' and p.th_width <= tw and p.th_height <= th:
        if debug:
            print 'using thumb shortcut'
        d = StringIO()
        d.write(rotate_thumb(p))
        d.seek(0)
        return d

    cvtargs = ''

    if debug:
        print 'tw=%d th=%d  p.width=%d pheight=%d' % (tw, th, p.width, p.height)

    # Rotate first
    if p.orientation != 0:
        cvtargs += '-rotate %d ' % -p.orientation

    # Then scale - only scale down
    if tw < p.width or th < p.height:
        cvtargs += '-size %(w)dx%(h)d -resize %(w)dx%(h)d ' % { 'w': tw, 'h': th }

    copyright=p.copyright
    if copyright is None:
        copyright='Copyright \xa9 %s %s' % (p.record_time.strftime('%Y'), p.photographer.email)

    # Watermark
    cvtargs += '-box "#00000070" -fill white -font %(font)s -encoding Unicode -draw "gravity SouthWest text 10,20 \\"Imagestore #%(id)d %(copy)s\\"" -quality %(qual)d' % {
        'font': font,
        'id': id,
        'qual': 70,
        'copy': copyright }

    temp = tempfile.NamedTemporaryFile(mode='wb', suffix='.'+extmap[p.mimetype])
    tmplen=0
    for c in p.getimagechunks():
        tmplen += len(c)
        temp.write(c)
    temp.flush()

    if debug:
        print 'tmplen=%d p.datasize=%d stat=%d' % (tmplen, p.datasize, stat(temp.name).st_size)
    
    c='%s %s %s jpg:-' % (convert, cvtargs, temp.name)
    if debug:
        print 'running '+c
    ret = popen(c)

    if debug:
        print 'waiting for output...',
    while len(select([ret],[],[])[0]) == 0:
        pass
    if debug:
        print 'OK'
    
    return ret

# Assumes pixel aspect ratio is 1:1 (ie, square pixels)
def transformed_size(id, size):
    debug=False
    
    p = db.Picture.get(id)

    (pw,ph) = (p.width, p.height)

    if p.orientation in (90, 270):
        (pw,ph) = (ph,pw)

    (sw,sh) = sizes[size]

    if debug:
        print 'pw=%d ph=%d sw=%d sh=%d' % (pw, ph, sw, sh)
    
    # no scaling
    if pw < sw and ph < sh:
        return (pw,ph)

    # x and y scaling factors
    fx = sw / float(pw)
    fy = sh / float(ph)

    if debug:
        print 'fx=%f fy=%f' % (fx, fy)
    
    if fx < fy:
        return (sw, ph * fx)
    else:
        return (pw * fy, sh)


def data_from_Image(image, format, **kw):
    data=StringIO()
    image.save(data, format, **kw)
    return data.getvalue()

def Image_from_data(data, *kw):
    data=StringIO(data)
    return Image.open(data, *kw)

def thumb_size(id):
    p = db.Picture.get(id)

    tw = p.th_width
    th = p.th_height

    if p.orientation in (90, 270):
        (tw,th) = (th,tw)

    return (tw,th)

# Use PIL to rotate the thumbnail internally, since we don't need to
# do anything fancy with it.
def rotate_thumb(p):
    if p.orientation == 0:
        return p.getthumb()
    else:
        img = Image_from_data(p.getthumb())
        print 'orientation=%d' % p.orientation
        if p.orientation == 90:
            img = img.transpose(Image.ROTATE_90)
        elif p.orientation == 180:
            img = img.transpose(Image.ROTATE_180)
        elif p.orientation == 270:
            img = img.transpose(Image.ROTATE_270)
        else:
            img = img.rotate(p.orientation)

        return data_from_Image(img, 'JPEG')



if False:
    print 'transformed_size(1,small)=%dx%d' % transformed_size(1, 'small')

    f=transform(2,'small')
    out=open('output.jpg', 'wb')
    out.write(f.read())

