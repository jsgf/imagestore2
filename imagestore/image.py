import re
from string import join
from quixote.errors import TraversalError, AccessError
from quixote.html import htmltext
from sqlobject import SQLObjectNotFound
from ImageTransform import sizes, transform, transformed_size, thumb_size, extmap
from db import Picture
from pages import join_extra, prefix

def sizere():
    return '|'.join(sizes.keys())

# Save preferred size as a cookie rather than a user preference
# since it's most likely to depend on whichever machine/browser
# they're using.  (XXX Could also default from user preference)
def preferred_size(request, default='small'):
    ret = request.get_cookie('imagestore-preferred-size', default)
    if ret not in sizes.keys():
        ret = default
    return ret

def set_preferred_size(request, size):
    request.response.set_cookie('imagestore-preferred-size', size)


def query_neighbours(self, id):
    """If Picture.get(id) is in the results list of the last query,
    then find its neighbours and return them"""

    if not request.sessionMap.has_key('query-results'):
        return (None, None)
    qr = request.sessionMap['query-results']

    if id not in qr:
        return (None, None)

    idx=0
    # why don't lists have a find() method?
    for r in qr:
        if r == id:
            break
        idx += 1
    prev = None
    next = None
    if idx > 0:
        prev = qr[idx-1]
    if idx < len(qr)-1:
        next = qr[idx+1]
    return (prev, next)


# Split an image name into a (id, size, isPreferred, ext) tuple
def split_image_name(name):
    regexp='^([0-9]+)(-(%s|orig)(!)?)?(.[a-z]+)$' % sizere()
    #print 'image looking up >%s< with %s' % (name, regexp)
    m = re.search(regexp, name)

    if m is None:
        raise TraversalError('Bad image name format: %s' % name)

    return (int(m.group(1)), m.group(3), m.group(4) is not None, m.group(5))

class DetailsUI:
    _q_exports = []
    
    def __init__(self, image, coll):
        self.coll = coll
        self.image = image

    def _q_lookup(self, request, component):
        (id, size, pref, ext) = split_image_name(component)

        try:
            p = Picture.get(id)
        except SQLObjectNotFound, x:
            raise TraversalError(str(x))

        return lambda request, self=self, p=p: \
                                         self.details(request, p)

    from image_page import details as details_ptl
    details = details_ptl

# class for /COLLECTION/image namespace (not an individual image)
class ImageUI:
    _q_exports = [ 'details', 'rotate' ]

    def __init__(self, coll):
        self.coll = coll
        self.dbcoll = coll.dbobj

        self.details = DetailsUI(self, coll)

    # generate the original image
    def image_orig(self, request, p):
        if not self.coll.mayViewOrig(request, p):
            raise AccessError('You may not view this original image')
        request.response.set_content_type(p.mimetype)
        return p.getimage()             # XXX stream

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
        
        file = transform(p.id, size)
        ret = ''.join([ d for d in file])

        request.response.set_content_type('image/jpeg')

        return ret

    def rotate(self, request):
        try:
            id = int(request.get_form_var('id'))
            angle = int(request.get_form_var('angle'))
            returnurl = request.get_form_var('fromurl')

            p = Picture.get(id)

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
            request.redirect(returnurl)
        
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
            p = Picture.get(picid)
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

        return '%s/%s/image/%d%s.html' % (prefix, self.dbcoll.name, p.id, size)

    def thumb_url(self, p):
        return '%s/%s/image/%d-thumb.jpg' % (prefix, self.dbcoll.name, p.id)

    def details_url(self, p):
        return '%s/%s/image/details/%d.html' % (prefix, self.dbcoll.name, p.id)

    def picture_url(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''
        return "%s/%s/image/%d%s.%s" % (prefix, self.dbcoll.name, p.id, size, extmap[p.mimetype])

    def rotate_url(self, p, angle, frompage):
        angle = int(angle)
        return '%s/%s/image/rotate?id=%d&angle=%d&fromurl=%s' % \
               (prefix, self.dbcoll.name, p.id, angle, frompage)

    def picture_img(self, p, size, preferred=False, extra={}):
        e = join_extra(extra)

        (pw,ph) = transformed_size(p.id, size)

        return htmltext('<img class="picture" style="width:%(w)dpx; height:%(h)dpx;" alt="%(alt)s" %(extra)s src="%(ref)s">' % \
                        { 'w': pw,
                          'h': ph,
                          'alt': 'Picture %d' % p.id,
                          'extra': e,
                          'ref': self.picture_url(p, size, preferred) })

    def thumb_img(self, p, extra={}):
        e = join_extra(extra)
        (tw,th) = thumb_size(p.id)

        return htmltext('<img id="thumb:%(id)d" class="thumb" style="width:%(w)dpx; height:%(h)dpx;" alt="%(alt)s" %(extra)s src="%(ref)s">' % {
            'w': tw,
            'h': th,
            'alt': 'Thumbnail of %d' % p.id,
            'id': p.id,
            'extra': e,
            'ref': self.thumb_url(p) })

    def view_link(self, request, p, size=None, link=None, preferred=False, extra={}):
        if link is None:
            link = self.thumb_img(p=p)

        e = join_extra(extra)

        return htmltext('<a %(extra)s href="%(url)s">%(link)s</a>' % {
            'url': self.view_url(p=p, size=size, preferred=preferred),
            'link': link,
            'extra': e })

    def view_newwin_link(self, request, p, size=None, link=None, preferred=False, extra={}):
        from style import view_margin
        
        if size is None:
            size = preferred_size(request, None)
        extra['target'] = str(p.id)

        if size is not None:
            (tw,th) = transformed_size(p.id, size)
        else:
            (tw,th) = (640,480)

        extra['onClick'] = "newwin = window.open('', '%(id)d', 'width=%(w)d,height=%(h)d,resizable=1,scrollbars=0');" % {
            'id': p.id,
            'w': tw + (2*view_margin),
            'h': th + (2*view_margin),
            }
        return self.view_link(request, p=p, size=size, link=link, preferred=preferred, extra=extra)

    def details_link(self, p, link):
        return htmltext('<a href="%s">%s</a>' % (self.details_url(p), link))
