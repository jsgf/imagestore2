import re
from rfc822 import formatdate

from sqlobject import SQLObjectNotFound

from quixote.util import Redirector
from quixote.errors import TraversalError, AccessError
from quixote.html import htmltext as H, TemplateIO
import quixote.form as form2
from quixote.http_response import Stream

import imagestore
import imagestore.db as db
import imagestore.pages as page
import imagestore.form
import imagestore.ImageTransform as ImageTransform
import imagestore.style as style

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
                                    urlfn=lambda pic, size, s=self.image: s.edit_url(pic))
            
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
                Redirector(self.image.edit_url(db.Picture.get(next)))
            else:
                Redirector(request.get_path())
            ret = ''

        return ret

class ImageUI:
    " class for /COLLECTION/image namespace (not an individual image) "
    _q_exports = [ 'details', 'edit', 'rotate' ]

    def __init__(self, coll):
        self.coll = coll
        self.dbcoll = coll.dbobj

        self.details = DetailsUI(self, coll)
        self.edit = EditUI(self, coll)

    # generate the original image
    def image_orig(self, request, p):
        if not self.coll.mayViewOrig(request, p):
            raise AccessError('You may not view this original image')
        request.response.set_content_type(p.mimetype)
        return Stream(p.getimagechunks(), p.datasize)

    # generate a transformed image
    def image(self, request, p, size, preferred):
        if not self.coll.mayView(request, p):
            raise AccessError('You may not view this image')
        if p.collection != self.coll.dbobj:
            raise TraversalError('Image %d is not part of this collection' % p.id)
        
        if size is None:
            size = preferred_size(request)
        elif preferred:
            set_preferred_size(request, size)
        
        etag = '%s.%s.%s' % (p.hash, p.orientation, size)
        request.response.set_content_type(ImageTransform.transformed_type(p, size))
        request.response.set_header('ETag', etag)
        #request.response.set_header('Last-Modified', formatdate(p.modified_time))
        request.response.cache=2

        # See if they've already got it
        if etag == request.get_header('If-None-Match'):
            request.response.set_status(304)
            return ''
        
        file = ImageTransform.transform(p, size)
        
        if True or size == 'thumb':     # XXX streaming seems to cause a deadlock
            return ''.join(file)        # so we have a size
        else:
            return Stream(file)

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
            Redirector(returnurl)
        
        return 'rotate done, I guess'

    def _q_lookup(self, request, component):
        """ Look up an image by name.  The first part is the image
        number NNNN, followed by a size request (-orig is a special
        case to get the original image, but isn't really considered to
        be a size).  If the size request ends in '!' then that size is
        set as default.  The extension must be present, but is only
        checked for two states: .html (generate an HTML page to
        contain the image) and not .html (the image itself) """

        (picid, size, default, ext) = split_image_name(component)

        try:
            p = db.Picture.get(picid)
        except SQLObjectNotFound, x:
            raise TraversalError(str(x))

        if ext == '.html':
            return lambda request, self=self, p=p, size=size, default=default: \
                                       self.view(request=request, p=p,
                                                 size=size, default=default)

        if size == 'orig':
            return lambda request, self=self, p=p, size=size, default=default: \
                                       self.image_orig(request, p)
        else:
            return lambda request, self=self, p=p, size=size, default=default: \
                                       self.image(request, p, size, default)

    # view is a PTL function
    from image_page import view as view_ptl, view_rotate_link as view_rotate_link_ptl
    view = view_ptl
    view_rotate_link = view_rotate_link_ptl

    # Various URL generating functions
    def view_url(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''

        return '%s/%s/image/%d%s.html' % (imagestore.path(), self.dbcoll.name, p.id, size)

    def thumb_url(self, p):
        return '%s/%s/image/%d-thumb.jpg' % (imagestore.path(), self.dbcoll.name, p.id)

    def details_url(self, p):
        return '%s/%s/image/details/%d.html' % (imagestore.path(), self.dbcoll.name, p.id)

    def edit_url(self, p):
        return '%s/%s/image/edit/%d.html' % (imagestore.path(), self.dbcoll.name, p.id)

    def picture_url(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''
        return "%s/%s/image/%d%s.%s" % (imagestore.path(), self.dbcoll.name, p.id, size,
                                        ImageTransform.extmap[p.mimetype])

    def rotate_url(self, p, angle, frompage):
        angle = int(angle)
        return '%s/%s/image/rotate?id=%d&angle=%d&fromurl=%s' % \
               (imagestore.path(), self.dbcoll.name, p.id, angle, frompage)

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
        (tw,th) = ImageTransform.thumb_size(p.id)

        r = TemplateIO(html=True)

        r += H('<span class="thumb-img" style="width:%dpx; height=%dpx>">') % (tw, th)

        r += H('<img id="thumb:%(id)d" class="thumb" style="width:%(w)dpx; height:%(h)dpx;" alt="%(alt)s" %(extra)s src="%(ref)s">') % {
            'w': tw,
            'h': th,
            'alt': 'Thumbnail of %d' % p.id,
            'id': p.id,
            'extra': e,
            'ref': self.thumb_url(p) }

        if showvis:
            r += H('<img class="visibility" title="%(v)s" alt="%(v)s" src="%(p)s/static/%(v)s.png">') % {
                'v': p.visibility, 'p': imagestore.path()
                }

        r += H('</span>')

        return r.getvalue()

    def view_link(self, request, p, size=None, link=None, preferred=False, url=None, extra={}):
        if link is None:
            user = request.session.getuser()
            link = self.thumb_img(p=p, showvis=(user and p.ownerID == user.id))

        url = url or self.view_url(p=p, size=size, preferred=preferred)

        e = page.join_extra(extra)

        return H('<a id="pic%(id)d" %(extra)s href="%(url)s">%(link)s</a>' % {
            'id': p.id,
            'url': url,
            'link': link,
            'extra': e })

    def edit_newwin_link(self, request, p, extra=None):
        extra = extra or {}

        extra['target'] = str(p.id)

        return self.view_link(request, p, url=self.edit_url(p))
        
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
        return H('<a href="%s">%s</a>' % (self.details_url(p), link))

    def edit_link(self, p, link):
        return H('<a href="%s">%s</a>' % (self.edit_url(p), link))

    def set_prevnext(self, request, id, size=None, urlfn=None):
        (first, last) = request.session.get_result_ends()
        (prev,next) = request.session.get_results_neighbours(id)

        if urlfn is None:
            urlfn = lambda pic, size: self.view_url(pic, size)

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

