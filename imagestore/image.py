import re
from cStringIO import StringIO
import json

from sqlobject import SQLObjectNotFound

import quixote
from quixote.errors import PublishError, TraversalError, AccessError, QueryError
from quixote.html import htmltext as H, TemplateIO
import quixote.form as form2
import quixote.http_request
from quixote.http_response import Stream

import imagestore
import imagestore.db as db
import imagestore.pages as page
import imagestore.form
import imagestore.ImageTransform as ImageTransform
import imagestore.style as style
import imagestore.auth as auth
import imagestore.insert as insert
import imagestore.image_page as image_page
import imagestore.http as http
import imagestore.EXIF as EXIF

def sizere():
    return '|'.join(ImageTransform.sizes.keys())

# Save preferred size as a cookie rather than a user preference
# since it's most likely to depend on whichever machine/browser
# they're using.  (XXX Could also default from user preference)
def preferred_size(request, default='small'):
    ret = request.get_cookie('imagestore-preferred-size', default)
    if ret not in ImageTransform.sizes.keys():
        ret = default
    return ret

def set_preferred_size(request, size):
    request.response.set_cookie('imagestore-preferred-size', size)


# Split an image name into a (id, size, isPreferred, ext) tuple
def split_image_name(name):
    ids = [ '[0-9]+', 'sha1:[0-9a-fA-F]{40}' ]
    regexp='^(%s)(-(%s|orig)(!)?)?(.[a-z]+)$' % ('|'.join([ '(?:%s)' % i for i in ids]), sizere())

    #print 'image looking up >%s< with %s' % (name, regexp)
    
    m = re.search(regexp, name)

    if m is None:
        raise TraversalError('Bad image name format: %s' % name)

    id=m.group(1).lower()
    if id.startswith('sha1:'):
        try:
            id = db.Picture.byHash(id[5:]).id
        except SQLObjectNotFound:
            raise QueryError('hash %s not found' % id)

    return (int(id), m.group(3), m.group(4) is not None, m.group(5))

class EditUI:
    " class for /COLLECTION/image/edit/NNNN "
    _q_exports = []
    
    def __init__(self, image, coll):
        self.coll = coll
        self.image = image

    def path(self, p):
        return '%sedit/%d.html' % (self.image.path(), p.id)

    def _q_lookup(self, request, component):
        (id, size, pref, ext) = split_image_name(component)

        try:
            p = db.Picture.get(id)
        except SQLObjectNotFound, x:
            raise TraversalError(str(x))

        return self.editdetails(request, p)

    def editdetails(self, request, p):
        form = form2.Form(name='editdetails')

        form.add(form2.StringWidget, name='title', size=50,
                 value=p.title or '', title='Title')
        form.add(form2.StringWidget, name='keywords', size=40,
                 value=', '.join([ k.word for k in p.keywords]),
                 title='Keywords')
        form.add(form2.StringWidget, name='description', size=50,
                 value=p.description, title='Description')
# FIXME form layout
#        form.add(form2.TextWidget, name='description', cols=50, rows=10,
#                 value=p.description, title='Description')

        form.add(form2.SingleSelectWidget, name='owner', value=p.ownerID, title='Picture owner',
                 options=imagestore.form.userOptList())
        form.add(form2.SingleSelectWidget, name='visibility',
                 value=p.visibility, title='Visibility',
                 options=[ s for s in ['public', 'restricted', 'private']])

        (prev,next) = request.session.get_results_neighbours(p.id)

        if next is not None:
            form.add_submit('submit-next', H('Update picture and go to next >>'))
        else:
            form.add_submit('submit', 'Update picture details')
        form.add_reset('reset', 'Revert changes')

        if not form.is_submitted() or form.has_errors():
            from image_page import detail_table
            
            self.image.set_prevnext(request, p.id,
                                    urlfn=lambda pic, size, s=self.image: s.edit.path(pic))
            
            ret = TemplateIO(html=True)
            
            ret += page.pre(request, 'Edit details', 'editdetails', trail=False)
            ret += page.menupane(request)
            ret += self.image.view_rotate_link(request, p, wantedit=True)
            ret += detail_table(p)
            ret += form.render()
            ret += page.post()

            ret = ret.getvalue()
        else:
            keywords = form['keywords']
            keywords = imagestore.form.splitKeywords(keywords)

            p.setKeywords(keywords)

            p.visibility = form['visibility']

            if form.get_submit() == 'submit-next' and next:
                ret = quixote.redirect(self.image.edit.path(db.Picture.get(next)))
            else:
                ret = quixote.redirect(request.get_path())

        return ret

class ImageExif:
    _q_exports = []

    def __init__(self, image):
        self.image = image

    def path(self):
        return self.image.path() + 'exif/'

    def get_exif(self):
        p = self.image.pic()
        if p.mimetype != 'image/jpeg':
            return None
        
        pixfp = StringIO(p.getimage())
        exif = EXIF.process_file(pixfp)

        def decode_values(v, map):
            if v.tag not in EXIF.EXIF_TAGS:
                return

            tag = EXIF.EXIF_TAGS[v.tag]
            if len(tag) > 1:
                ret = None
                mapper = tag[1]
                if type(mapper) == dict:
                    ret = [ tag[1].get(val, None) for val in v.values ]
                elif callable(mapper):
                    ret = mapper(v.values)

                map['decoded'] = ret

            return map
        
        def json_map(v):
            fieldtype = EXIF.FIELD_TYPES

            ret = v.values
            
            if fieldtype[v.field_type][1] == 'A': # ascii
                ret = ''.join(v.values)
            if fieldtype[v.field_type][1] in ('SR', 'R'): # signed ratio or ratio
                ret = [ { 'ratio': (v.num, v.den), 'real': (float(v.num) / v.den) }
                             for v in v.values ]
            return ret

        for k,v in exif.items():
            if type(v) == EXIF.IFD_Tag:
                v.values = json_map(v)
                exif[k] = decode_values(v, { 'tag': v.tag, 'values': v.values })
        
        return exif
    
    def _q_index(self, request):
        request = quixote.get_request()
        response = quixote.get_response()

        if request.get_method() not in ('GET', 'HEAD'):
            raise http.MethodError(('GET', 'HEAD'))

        exif = self.get_exif()
        if exif is None:
            raise TraversalError('Image has no EXIF data')
        http.json_response()
        return json.write(exif.keys())

    def _q_lookup(self, request, component):
        response = quixote.get_response()
        
        exif = self.get_exif()
        if exif is None:
            raise TraversalError('Image has no EXIF data')

        if component not in exif:
            raise TraversalError('No such EXIF tag')
        
        if component == 'JPEGThumbnail':
            response.set_content_type('image/jpeg')
            return exif[component]
        elif component == 'TIFFThumbnail':
            response.set_content_type('image/tiff')
            return exif[component]

        http.json_response()
        return json.write(exif[component])
    
class ImageMeta:
    _q_exports = []

    get_fields = {
        'id':           lambda p: p.id,
        'hash':         lambda p: p.hash,
        'md5hash':      lambda p: p.md5hash,
        'mimetype':     lambda p: p.mimetype,
        'datasize':     lambda p: p.datasize,
        'collection':   lambda p: (p.collection.id, p.collection.name),
        'keywords':     lambda p: [ w.word for w in p.keywords ],
        'title':        lambda p: p.title,
        'description':  lambda p: p.description,
        'copyright':    lambda p: p.copyright,
        'visibility':   lambda p: p.visibility,
        'record_time':  lambda p: p.record_time.isoformat(),
        'modified_time':lambda p: p.modified_time.isoformat(),
        'owner':        lambda p: (p.owner.id, p.owner.username),
        'photographer': lambda p: (p.photographer.id, p.photographer.username),
        'camera':       lambda p: p.camera,
        'rating':       lambda p: p.rating,
        'dimensions':   lambda p: ImageTransform.transformed_size(p, 'full'),
        'thumb_dimensions': lambda p: ImageTransform.thumb_size(p),

        'orientation':  lambda p: p.orientation,
        'flash':        lambda p: p.flash,
        'fnumber':      lambda p: p.f_number,
        'exposure_time':lambda p: p.exposure_time,
        'exposure_bias':lambda p: p.exposure_bias,
        'brightness':   lambda p: p.brightness,
        'focal_length': lambda p: p.focal_length,
        }
    
    def set_title(p, t):
        p.title = t
        return t

    def set_description(p, d):
        p.description = d
        return d

    def set_visibility(p, v):
        if v not in ('public', 'restricted', 'private'):
            raise QueryError('bad visibility')
        p.visibility = v
        return v

    def set_orientation(p, o):
        try:
            o = int(o)
        except ValueError:
            raise QueryError('bad orientation')
        except TypeError:
            raise QueryError('bad orientation')
        if o not in (0, 90, 180, 270):
            raise QueryError('bad orientation')
        p.orientation = o
        return o

    def set_keywords(p, kw):
        pass

    set_fields = {
        'title':        set_title,
        'description':  set_description,
        'visibility':   set_visibility,
        'orientation':  set_orientation,
        'keywords':     set_keywords,
        }
        
    def __init__(self, image):
        self.image = image

    def set_meta(self, name, value):
        p = self.image.pic()

        user = auth.login_user()
        if not p.mayEdit(user):
            raise AccessError('Must log in to change picture')

        if name not in self.set_fields:
            raise http.ForbiddenError("can't change '%s' field" % name)

        return self.set_fields[name](p, value)

    def get_meta(self):
        p = self.image.pic()
        meta = {}

        for k,fn in self.get_fields.items():
            meta[k] = fn(p)

        return meta
    
    def _q_access(self, request):
        request = quixote.get_request()
        if request.get_method() in ('POST', 'PUT'):
            auth.login_user()

    def _q_index(self, request):
        request = quixote.get_request()
        response = quixote.get_response()

        http.json_response()

        if request.get_method() in ('POST', 'PUT'):
            if '_json' in request.form:
                ret = {}
                try:
                    changes = json.read(request.form['_json'])

                    for n,v in changes.items():
                        ret[n] = self.set_meta(n, v)

                    return json.write(ret)
                except json.ReadException:
                    raise QueryError('badly formatted JSON')

            response.set_status(204) # no content
            return ''
            
        meta = self.get_meta()

        return json.write(meta)

    def _q_lookup(self, request, component):
        request = quixote.get_request()
        response = quixote.get_response()

        if component not in self.get_fields:
            raise TraversalError('No meta key "%s"' % component)

        http.json_response()
        
        if request.get_method() in ('POST', 'PUT'):
            if '_json' in request.form:
                data = json.read(request.form['_json'])
                # Return a callable thing
                return lambda r: self.set_meta(component, data)
            
            respose.set_status(204)     # no content
            return ''
        
        p = self.image.pic()
        return json.write(self.get_fields[component](p))

    def path(self):
        return self.image.path() + 'meta/'

_re_xform_image = re.compile('^([a-z]+|([0-9]+)x([0-9]+))\.([a-z]+)$')

class Image:
    """ Class for a specific image, and its namespace. """
    _q_exports = [ 'download', 'meta', 'exif', 'details' ]

    def __init__(self, collection, pic):
        self.collection = collection
        if type(pic) == int:
            self.id = pic
        else:
            self.id = pic.id
            self.pic = lambda : pic
        self.details = image_page.DetailsUI(self)
        self.meta = ImageMeta(self)
        self.exif = ImageExif(self)
        self.ui = image_page.ImageUI(self)
        
    def path(self):
        return '%s%d/' % (self.collection.path(), self.id)

    def thumb_path(self):
        return self.path() + 'thumb.jpg'

    def image_path(self, size='default'):
        p = self.pic()
        return '%s%s.%s' % (self.path(), size, ImageTransform.extmap[p.mimetype])

    def download_path(self):
        return self.path() + 'download'
    
    def rotate_path(self, angle):
        return self.path() + 'rotate?angle=%d' % angle

    def pic(self):
        """ Defer looking up the picture until we actually need it. """
        try:
            p = db.Picture.get(self.id)
        except SQLObjectNotFound:
            raise TraversalError('Image %d not found' % self.id)
        
        self.pic = lambda : p
        return p
    
    def etag(self, size):
        p = self.pic()
        return '%s.%s.%s' % (p.hash, p.orientation, size)

    def if_none_match(self, etag):
        request = quixote.get_request();
        inm = request.get_header('If-None-Match')

        if inm is None:
            return False

        if inm == '*':
            return True
        
        return etag in inm.split(', ')

    def _q_index(self, request):
        """ Returns the raw data of a Picture """
        request = quixote.get_request()
        response = quixote.get_response()

        p = self.pic()
        
        if not self.collection.mayViewOrig(p):
            raise AccessError('You may not view this original image')

        etag = self.etag('orig')

        response.buffered = False
        response.set_content_type(p.mimetype)
        response.set_header('Content-Disposition',
                            'inline; filename="%d-orig.%s"' % \
                            (self.id, ImageTransform.extmap[p.mimetype]))
        response.set_header('Content-MD5',
                            p.md5hash.decode('hex').encode('base64')[:-1])
        response.set_header('ETag', etag)

        if self.if_none_match(etag):
            response.set_status(304)    # not modified
            return ''

        return Stream(p.getimagechunks(), p.datasize)

    def _q_access(self, request):
        user = auth.login_user(quiet=True)

        p = self.pic()
        if not p.mayView(user):
            user = auth.login_user()
            if not p.mayView(user):
                raise AccessError('may not view picture')

    def download(self, request=None):
        """ Get the raw image, but set the content disposition
        to attachment to get the browser to download it. """
        ret = self._q_index(request)

        p = self.pic()
        response = quixote.get_response()
        response.set_header('Content-Disposition',
                            'attachment; filename="%d-orig.%s"' % \
                            (self.id, ImageTransform.extmap[p.mimetype]))
        return ret

    def display_image(self, size, ext):
        """ Display a transformed (rotated and scaled) image """
        
        request = quixote.get_request()

        if size in ImageTransform.sizes:
            width,height = ImageTransform.sizes[size]

        if width is None or height is None:
            raise TraversalError('Unknown image size: %s' % size)

        p = self.pic()

        if not self.collection.mayView(p, quiet=True):
            raise AccessError('You may not view this image')
        if p.collection != self.collection.db:
            raise TraversalError('Image %d is not part of this collection' % p.id)

        request = quixote.get_request()
        response = quixote.get_response()

        etag = self.etag(size)
        response.set_content_type(ImageTransform.transformed_type(p, size))
        response.set_header('ETag', etag)
        response.set_header('Content-Disposition',
                            'inline; filename="%d-%s.%s"' % \
                            (self.id, size,
                             ImageTransform.extmap[ImageTransform.transformed_type(p, size)]))

        if self.if_none_match(etag):
            response.set_status(304)    # not modified
            return ''

        file = ImageTransform.transform(p, size)

        #ret = Stream(file)     # deadlocks
        ret = file.read()
        return ret
        

    def _q_lookup(self, request, component):
        """ Match against SIZE.FORMAT """

        m = _re_xform_image.match(component)
        if m is None:
            raise TraversalError('Bad image name format: %s' % component)

        size,width,height,ext = m.groups()

        if ext == 'html':
            return self.ui.view(size)

        return self.display_image(size, ext)

_re_old_style_url = re.compile('^([0-9]+)(?:-([a-z]+)!?)?\.([a-z]+)$')

class ImageDir:
    """ Class for /COLLECTION/image/ namespace (not an individual image).
    This is soley for backwards compatibility. """
    _q_exports = [ 'edit', 'rotate' ]

    def __init__(self, collection):
        self.collection = collection

        self.edit = EditUI(self, collection)

    def rotate(self, request):
        try:
            id = int(request.get_field('id'))
            angle = int(request.get_field('angle'))
            returnurl = request.get_field('fromurl')

            p = db.Picture.get(id)

            if not self.collection.mayEdit(p):
                raise AccessError('may not edit image')

            if angle not in (0, 90, 180, 270):
                raise QueryError('Bad angle')
        except SQLObjectNotFound, x:
            raise QueryError('Bad id')
        except ValueError, x:
            raise QueryError('Bad value' + str(x))

        p.orientation = angle

        ret = 'rotate done, I guess'
        if returnurl is not None:
            ret = quixote.redirect(returnurl)
        
        return ret

    def _q_lookup(self, request, component):
        """ Create an Image() instance for a requested image.  If the
        component is an old-style URL, then generate a redirect for it. """

        if component == '':
            return quixote.redirect(self.collection.path())
            
        # Look for old-style URL, and generate a redirect
        m = _re_old_style_url.match(component)
        if m is not None:
            # group 1: id, 2: size (optional), 3: extension
            id,size,ext = m.groups()
            if size is None:
                size = 'default'
            p = '%s%s/%s.%s' % (self.collection.path(), id, size, ext)
            return lambda r: quixote.util.Redirector(p)()

        raise TraversalError('Bad image identifier "%s"' % component)

    # Various URL generating functions
    def path(self):
        return self.collection.path() + 'image/'
    
    def set_prevnext(self, request, id, size=None, urlfn=None):
        (first, last) = request.session.get_result_ends()
        (prev,next) = request.session.get_results_neighbours(id)

        if urlfn is None:
            urlfn = lambda pic, size: self.view_path(pic, size)

        if first is not None and first != id and first != prev:
            first = db.Picture.get(first)
            request.navigation.set_first(urlfn(first, size), title='Image %d' % first.id)
        if last is not None and last != id and last != next:
            last = db.Picture.get(last)
            request.navigation.set_last(urlfn(last, size), title='Image %d' % last.id)

        if prev is not None:
            prev = db.Picture.get(prev)
            request.navigation.set_prev(urlfn(prev, size), title='Image %d' % prev.id)

        if next is not None:
            next = db.Picture.get(next)
            request.navigation.set_next(urlfn(next, size), title='Image %d' % next.id)

