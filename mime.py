# Mime-type handling

# A central place for storing knowledge on dealing with different file
# types.  The intent is that this be easily extended for new file
# types.

import mimetypes
import fnmatch
from os import popen,stat
from select import select
from cStringIO import StringIO

# Allow BZip files
mimetypes.encodings_map['.bz2'] = 'bzip2'


_known_types = {}

def matchtype(types, matchlist):

    """ Match the best mime-type against the match-list.

    The match list is a series of (type, quality) tuples, where type
    may be a glob pattern, and quality is a floating-point number
    between 0 and 1.  Types is a list of strings.  This function
    returns the best matching element from types.  Types in matchlist
    with a q of 0 are not considered for matching. """

    matchlist.sort(lambda a,b: cmp(b[1],a[1]))

    for t,q in matchlist:
        if q == 0.0:
            continue

        res = fnmatch.filter(types, t)
        if len(res) != 0:
            return res[0]

    return None

class MimeType:
    " Abstract base class "

    def __init__(self, mimetype, ext=None):
        self.mimetype = mimetype

        self._ext = ext
        
        if ext is not None:
            pass
            #for e in ext:
            #    mimetypes.add_type(self.mimetype, e)

        _known_types[mimetype] = self

    def importer(self):
        ' Return a class for importing this type '
        raise Exception('Implement importer')

    def extensions(self):
        ' All possible extensions for this MimeType '
        if self._ext:
            return self._ext
        return [ e[1:] for e in mimetypes.guess_all_extensions(self.mimetype) ]

    def ext(self):
        if self._ext:
            return self._ext[0]
        return mimetypes.guess_extension(self.mimetype)[1:]

    def sizes(self):
        return { 'thumb': (160, 160) }

    def render_thumb(self, request):
        pass


    def canResize(self):
        " We know how to resize pictures of this type "
        return False
    def canRotate(self):
        " We know how to rotate pictures of this type "
        return False
    def canWatermark(self):
        " We know how to watermark pictures of this type "
        return False
    def canConvert(self):
        " We know how to convert the file format of pictures of this type "
        return False
    def canTransform(self):
        return self.canResize() or self.canRotate() or self.canWatermark() or self.canConvert()

    def thumb_size(self, p):
        tw = p.th_width
        th = p.th_height

        if p.orientation in (90, 270):
            assert self.canRotate(), 'Unrotatable image rotated'
            (tw,th) = (th,tw)

        return (tw,th)

class ImageMimeType(MimeType):
    def __init__(self, mimetype, ext=None):
        MimeType.__init__(self, 'image/' + mimetype, ext)

    def sizes(self):
        return { 'thumb':      (160, 160),
                 'tiny':       (320, 240),
                 'small':      (640, 480),
                 'medium':     (800, 600),
                 'large':      (1024, 768),
                 'full':       (10000, 10000),
                 }

    def canResize(self):
        return True
    def canRotate(self):
        return True
    def canWatermark(self):
        return True
    def canConvert(self):
        return True
    
    def transformed_size(self, p, size):
        debug = False
        
        (pw,ph) = (p.width, p.height)

        if p.orientation in (90, 270):
            (pw,ph) = (ph,pw)

        (sw,sh) = self.sizes()[size]

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

    def transformed_type(self, p, size):
        return 'image/jpeg'

    def transform(self, p, size = 'medium'):
        debug=False

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
        if self.canRotate() and p.orientation != 0:
            cvtargs += '-rotate %d ' % -p.orientation

        # Then scale - only scale down
        if self.canResize() and (tw < p.width or th < p.height):
            cvtargs += '-size %(w)dx%(h)d -resize %(w)dx%(h)d ' % { 'w': tw, 'h': th }

        # Watermark
        if self.canWatermark():
            copyright=p.copyright
            copyright.strip()
            if copyright is None or copyright == '':
                copyright='Copyright \xa9 %s %s' % (p.record_time.strftime('%Y'),
                                                    p.photographer.email)

            cvtargs += '-box "#00000070" -fill white -pointsize %(size)d -font %(font)s -encoding Unicode -draw "gravity SouthWest text 10,20 \\"Imagestore #%(id)d %(copy)s\\"" -quality %(qual)d' % {
                'font': font,
                'size': fontsize,
                'id': p.id,
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

        assert self.canConvert(), 'Attempting to convert unconvertable picture'

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


class VideoMimeType(MimeType):
    def __init__(self, mimetype, ext=None):
        MimeType.__init__(self, 'video/' + mimetype, ext)

    def transformed_type(self, p, size):
        if size == 'thumb':
            return 'image/jpeg'
        return p.mimetype

ImageMimeType('jpeg', [ 'jpg', 'jpeg' ])
ImageMimeType('tiff', [ 'tif', 'tiff' ])
VideoMimeType('mpeg', [ 'mpg', 'mpeg' ])

def getMimeType(type):
    return _known_types[type]
