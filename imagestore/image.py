import re
from string import join
from quixote.errors import TraversalError
from quixote.html import htmltext
from sqlobject import SQLObjectNotFound
from ImageTransform import sizes, transform, transformed_size, thumb_size, extmap
from db import Picture
from pages import join_extra

from go_scgi import ImagestoreHandler
prefix = ImagestoreHandler.prefix

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

# class for /COLLECTION/image namespace (not an individual image)
class ImageUI:
    _q_exports = [ ]

    def __init__(self, coll):
        self.coll = coll

    # generate the original image
    def image_orig(self, request, p):
        request.response.set_content_type(p.mimetype)
        return p.getimage()             # XXX stream

    # generate a transformed image
    def image(self, request, p, size, preferred):
        if size is None:
            size = preferred_size(request)
        elif preferred:
            set_preferred_size(request, size)
        
        file = transform(p.id, size)
        ret = ''
        for d in file:
            ret += d

        request.response.set_content_type('image/jpeg')

        return ret

    def _q_lookup(self, request, component):
        """ Look up an image by name.  The first part is the image
        number NNNN, followed by a size request (-orig is a special
        case to get the original image, but isn't really considered to
        be a size).  If the size request ends in '!' then that size is
        set as default.  The extension must be present, but is only
        checked for two states: .html (generate an HTML page to
        contain the image) and not .html (the image itself) """
        
        regexp='^([0-9]+)(-(%s|orig)(!)?)?(.[a-z]+)$' % sizere()
        #print 'image looking up >%s< with %s' % (component, regexp)
        m = re.search(regexp, component)

        if m is None:
            raise TraversalError('Bad image name format: %s' % component)

        picid = int(m.group(1))

        try:
            p = Picture.get(picid)
            if p.collection != self.coll:
                raise TraversalError('Image %d is not part of this collection' % picid)
        except SQLObjectNotFound, x:
            raise TraversalError(str(x))

        size = m.group(3)
        default = m.group(4) is not None
        ext = m.group(5)

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
    from image_page import view as view_ptl
    view = view_ptl


    # Various URL generating functions
    def view_url(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''

        return '%s/%s/image/%d%s.html' % (prefix, self.coll.name, p.id, size)

    def thumb_url(self, p):
        return '%s/%s/image/%d-thumb.jpg' % (prefix, self.coll.name, p.id)

    def details_url(self, p):
        return '%s/%s/details/%d.html' % (prefix, self.coll.name, p.id)

    def picture_url(self, p, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''
        return "%s/%s/image/%d%s.%s" % (prefix, self.coll.name, p.id, size, extmap[p.mimetype])

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
        from image_page import view_margin
        
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
