import re
from rfc822 import formatdate
import json

from sqlobject import SQLObjectNotFound

import quixote
from quixote.errors import PublishError, TraversalError, AccessError, QueryError
from quixote.html import htmltext as H, TemplateIO
import quixote.form as form2
from quixote.http_response import Stream

import imagestore
import imagestore.db as db
import imagestore.pages as page
import imagestore.form
import imagestore.ImageTransform as ImageTransform
import imagestore.style as style
import imagestore.auth as auth
import imagestore.insert as insert

class MethodError(PublishError):
    status_code = 405
    title = 'Method Not Allowed'
    description = 'Method not allowed on this object'

class ForbiddenError(PublishError):
    status_code = 403
    title = 'Forbidden'
    description = 'Action forbidden on this object'

    
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

class DetailsUI:
    " class for /COLLECTION/image/details/NNNN "
    _q_exports = []
    
    def __init__(self, image, coll):
        self.coll = coll
        self.image = image

    def path(self, p):
        return '%sdetails/%d.html' % (self.image.path(), p.id)
    
    def _q_lookup(self, request, component):
        (id, size, pref, ext) = split_image_name(component)

        try:
            p = db.Picture.get(id)
        except SQLObjectNotFound, x:
            raise TraversalError(str(x))

        return self.details(request, p)

    from image_page import details as details_ptl
    details = details_ptl

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
                quixote.redirect(self.image.edit.path(db.Picture.get(next)))
            else:
                quixote.redirect(request.get_path())
            ret = ''

        return ret

class ImageMeta:
    _q_exports = []

    class fields:
        def get_id(p):          return p.id
        def get_hash(p):        return p.hash
        def get_md5hash(p):     return p.md5hash
        def get_mimetype(p):    return p.mimetype
        def get_datasize(p):    return p.datasize
        def get_collection(p):  return (p.collection.id, p.collection.name)
        def get_keywords(p):    return [ w.word for w in p.keywords ]
        def get_title(p):       return p.title
        def get_description(p): return p.description
        def get_copyright(p):   return p.copyright
        def get_visibility(p):  return p.visibility
        def get_record_time(p): return p.record_time.isoformat()
        def get_modified_time(p):       return p.modified_time.isoformat()
        def get_owner(p):       return (p.owner.id, p.owner.username)
        def get_photographer(p):return (p.photographer.id, p.photographer.username)
        def get_camera(p):      return p.camera
        def get_rating(p):      return p.rating
        def get_dimensions(p):  return (p.width, p.height)
        def get_thumb_dimensions(p):    return (p.th_width, p.th_height)

        def get_orientation(p): return p.orientation
        def get_flash(p):       return p.flash
        def get_fnumber(p):     return p.f_number
        def get_exposure_time(p):return p.exposure_time
        def get_exposure_bias(p):return p.exposure_bias
        def get_brightness(p):  return p.brightness
        def get_focal_length(p):return p.focal_length

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
        
    def __init__(self, image):
        self.image = image

    def set_meta(self, name, value):
        p = self.image.pic()

        user = auth.login_user()
        if not p.mayEdit(user):
            raise AccessError('Must log in to change picture')

        try:
            fn = self.fields.__dict__['set_'+name]
        except KeyError:
            raise ForbiddenError("can't change '%s' field" % name)

        return fn(p, value)
    
    def _q_access(self, request):
        request = quixote.get_request()
        if request.get_method() in ('POST', 'PUT'):
            auth.login_user()

    def _q_index(self, request):
        request = quixote.get_request()
        response = quixote.get_response()
        
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
            
        p = self.image.pic()
        meta={}
        for k,fn in self.fields.__dict__.items():
            if k.startswith('get_'):
                meta[k[4:]] = fn(p)

        response = quixote.get_response()
        #response.set_content_type('application/x-json')

        return json.write(meta)

    def _q_lookup(self, request, component):
        request = quixote.get_request()
        response = quixote.get_response()

        try:
            fn = self.fields.__dict__['get_' + component]
        except KeyError:
            raise TraversalError('No meta key "%s"' % component)

        if request.get_method() in ('POST', 'PUT'):
            if '_json' in request.form:
                data = json.read(request.form['_json'])
                # Return a callable thing
                return lambda r: self.set_meta(component, data)
            
            respose.set_status(204)     # no content
            return ''
        
        #response.set_content_type('application/x-json')

        p = self.image.pic()
        return json.write(fn(p))

    def path(self):
        return self.image.path() + 'meta/'

_re_xform_image = re.compile('^([a-z]+|([0-9]+)x([0-9]+))\.([a-z]+)$')

class Image:
    """ Class for a specific image, and its namespace. """
    _q_exports = [ 'download', 'meta' ]

    def __init__(self, parent, id):
        self.collection = parent.coll
        self.id = id
        self.parent = parent

        self.meta = ImageMeta(self)

    def path(self):
        return '%s%d/' % (self.parent.path(), self.id)

    def thumb_path(self):
        return self.path() + 'thumb.jpg'

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
        
        if not self.collection.mayViewOrig(request, p):
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
        user = None
        try:
            user = auth.login_user()
        except auth.UnauthorizedError:
            pass

        p = self.pic()
        if not p.mayView(user):
            user = auth.login_user()
            if not p.mayView(user):
                raise AccessError('may not view picture')

    def download(self, request):
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

        if not self.collection.mayView(request, p):
            raise AccessError('You may not view this image')
        if p.collection != self.collection.dbobj:
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

        if size == 'default':
            size = 'small'              # TODO get user pref cookie

        if ext == 'html':
            pass                        # TODO return HTML page

        return self.display_image(size, ext)

_re_number = re.compile('^[0-9]+$')
_re_hash = re.compile('^(?:hash|sha1?):([0-9a-f]{40})$', re.I)
_re_md5hash = re.compile('^md5:([0-9a-f]{32})$', re.I)
_re_old_style_url = re.compile('^([0-9]+)(?:-([a-z]+)!?)?\.([a-z]+)$')

class ImageUI:
    " class for /COLLECTION/image namespace (not an individual image) "
    _q_exports = [ 'details', 'edit', 'rotate' ]

    def __init__(self, coll):
        self.coll = coll

        self.details = DetailsUI(self, coll)
        self.edit = EditUI(self, coll)

    def rotate(self, request):
        try:
            id = int(request.get_field('id'))
            angle = int(request.get_field('angle'))
            returnurl = request.get_field('fromurl')

            p = db.Picture.get(id)

            if not self.coll.mayEdit(request, p):
                raise AccessError('may not edit image')

            if angle not in (0, 90, 180, 270):
                raise QueryError('Bad angle')
        except SQLObjectNotFound, x:
            raise QueryError('Bad id')
        except ValueError, x:
            raise QueryError('Bad value' + str(x))

        p.orientation = angle

        if returnurl is not None:
            quixote.redirect(returnurl)
        
        return 'rotate done, I guess'

    def _q_index(self, request):
        """ POSTing to images will upload new images. """
        request = quixote.get_request()
        response = quixote.get_response()
        
        method = request.get_method()

        response.set_header('Allowed', 'POST')

        if request.get_method() != 'POST':
            raise MethodError()

        user = auth.login_user()
        perm = self.coll.dbobj.permissions(user)

        mayupload = (user and user.mayUpload) or (perm and perm.mayUpload)

        if not mayupload:
            raise AccessError('You may not upload images')

        print 'upload'
        added=[]

        if 'image' not in request.form:
            response.set_status(204)    # no content
            return ''

        visibility=request.form.get('visibility', 'public')
        keywords=request.form.get('keywords', [])
        if not isinstance(keywords, list):
            keywords = [ keywords ]
            
        if isinstance(request.form['image'], list):
            for img in request.form['image']:
                id=insert.import_image(img.fp,
                                       orig_filename=img.orig_filename,
                                       owner=user,
                                       photographer=user,
                                       public=visibility,
                                       collection=self.coll.dbobj,
                                       keywords=keywords)
                added.append(id)
        else:
            img = request.form['image']
            id=insert.import_image(img.fp,
                                   orig_filename=img.orig_filename,
                                   owner=user,
                                   photographer=user,
                                   public=visibility,
                                   collection=self.coll.dbobj,
                                   keywords=keywords)
            added.append(id)

        return json.write(added)

    def _q_lookup(self, request, component):
        """ Create an Image() instance for a requested image.  If the
        component is an old-style URL, then generate a redirect for it. """

        # Check for plain ID number
        m = _re_number.match(component)
        if m is not None:
            return Image(self, int(m.group(0)))

        # Check for lookup by hash
        m = _re_hash.match(component)
        if m is not None:
            hash = m.group(1)
            try:
                id = int(db.Picture.byHash(hash).id)
                return lambda r: quixote.util.Redirector('%s%d' % (self.path(), id))()
            except SQLObjectNotFound:
                raise TraversalError('Bad image hash')

        m = _re_md5hash.match(component)
        if m is not None:
            hash = m.group(1)
            try:
                id = int(db.Picture.byMd5hash(hash).id)
                return lambda r: quixote.util.Redirector('%s%d' % (self.path(), id))()
            except SQLObjectNotFound:
                raise TraversalError('Bad image MD5 hash')
                
            
        # Look for old-style URL, and generate a redirect
        m = _re_old_style_url.match(component)
        if m is not None:
            # group 1: id, 2: size (optional), 3: extension
            id,size,ext = m.groups()
            if size is None:
                size = 'default'
            p = '%s%s/%s.%s' % (self.path(), id, size, ext)
            return lambda r: quixote.util.Redirector(p)()

        raise TraversalError('Bad image identifier %s' % component)

    # view is a PTL function
    from image_page import view as view_ptl, view_rotate_link as view_rotate_link_ptl
    view = view_ptl
    view_rotate_link = view_rotate_link_ptl

    # Various URL generating functions
    def path(self):
        return self.coll.path() + 'image/'
    
    def view_path(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''

        return '%s%d%s.html' % (self.path(), p.id, size)

    def thumb_path(self, p):
        return '%s%d-thumb.jpg' % (self.path(), p.id)

    def picture_url(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''
        return "%s%d%s.%s" % (self.path(), p.id, size,
                              ImageTransform.extmap[p.mimetype])

    def rotate_path(self, p, angle, frompage):
        angle = int(angle)
        return '%srotate?id=%d&angle=%d&fromurl=%s' % (self.path(), p.id, angle, frompage)

    def picture_img(self, p, size, preferred=False, extra={}):
        e = page.join_extra(extra)

        (pw,ph) = ImageTransform.transformed_size(p, size)

        r = TemplateIO(html=True)

        # Don't worry about the visibility marker on full-sized pictures for now
        
        r += H('<img class="picture" style="width:%(w)dpx; height:%(h)dpx;" alt="%(alt)s" %(extra)s src="%(ref)s">') % \
             { 'w': pw,
               'h': ph,
               'alt': 'Picture %d' % p.id,
               'extra': e,
               'ref': self.picture_url(p, size, preferred) }

        return r.getvalue()

    def thumb_img(self, p, showvis, extra={}):
        e = page.join_extra(extra)
        (tw,th) = ImageTransform.thumb_size(p)

        r = TemplateIO(html=True)

        r += H('<span class="thumb-img" style="width:%dpx; height=%dpx>">') % (tw, th)

        r += H('<img id="thumb:%(id)d" class="thumb" style="width:%(w)dpx; height:%(h)dpx;" alt="%(alt)s" %(extra)s src="%(ref)s">') % {
            'w': tw,
            'h': th,
            'alt': 'Thumbnail of %d' % p.id,
            'id': p.id,
            'extra': e,
            'ref': self.thumb_path(p) }

        if showvis:
            r += H('<img class="visibility" title="%(v)s" alt="%(v)s" src="%(p)s%(v)s.png">') % {
                'v': p.visibility, 'p': imagestore.static_path()
                }

        r += H('</span>')

        return r.getvalue()

    def view_link(self, request, p, size=None, link=None, preferred=False, url=None, extra={}):
        if link is None:
            user = request.session.getuser()
            link = self.thumb_img(p=p, showvis=(user and p.ownerID == user.id))

        url = url or self.view_path(p=p, size=size, preferred=preferred)

        e = page.join_extra(extra)

        return H('<a id="pic%(id)d" %(extra)s href="%(url)s">%(link)s</a>' % {
            'id': p.id,
            'url': url,
            'link': link,
            'extra': e })

    def edit_newwin_link(self, request, p, link=None, extra=None):
        extra = extra or {}

        extra['target'] = str(p.id)

        return self.view_link(request, p, url=self.edit.path(p), link=link, extra=extra)
        
    def view_newwin_link(self, request, p, size=None, link=None, preferred=False, extra=None):
        extra = extra or {}
        
        if size is None:
            size = preferred_size(request, None)
        extra['target'] = str(p.id)

        if size is not None:
            (tw,th) = ImageTransform.transformed_size(p, size)
        else:
            (tw,th) = (640,480)

        extra['onClick'] = "newwin = window.open('', '%(id)d', 'width=%(w)d,height=%(h)d,resizable=1,scrollbars=0');" % {
            'id': p.id,
            'w': tw + (2*style.view_margin),
            'h': th + (2*style.view_margin),
            }
        return self.view_link(request, p=p, size=size, link=link, preferred=preferred, extra=extra)

    def details_link(self, p, link):
        return H('<a href="%s">%s</a>' % (self.details.path(p), link))

    def edit_link(self, p, link):
        return H('<a href="%s">%s</a>' % (self.edit.path(p), link))

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

