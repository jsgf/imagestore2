import re
from string import join
from quixote.errors import TraversalError
from sqlobject import SQLObjectNotFound
from ImageTransform import sizes, transform
import db

def sizere():
    return '|'.join(sizes.keys())

# class for /CATALOGUE/image namespace (not an individual image)
class ImageUI:
    _q_exports = [ ]

    def __init__(self, cat):
        print 'ImageUI(%s)' % cat
        self.cat = cat


    # Save preferred size as a cookie rather than a user preference
    # since it's most likely to depend on whichever machine/browser
    # they're using.  (XXX Could also default from user preference)
    def preferred_size(self, request, default='small'):
        ret = request.get_cookie('imagestore-preferred-size', default)
        if ret not in sizes.keys():
            ret = default
        return ret

    def set_preferred_size(self, request, size):
        request.response.set_cookie('imagestore-preferred-size', size)



    def view(self, request, id, size, preferred):
        pass

    # generate the original image
    def image_orig(self, request, id):
        p = db.Picture.get(id)
        request.response.set_content_type(p.mimetype)
        return p.getimage()

    # generate a transformed image
    def image(self, request, id, size, preferred):
        if size is None:
            size = self.preferred_size(request)
        elif preferred:
            self.set_preferred_size(request, size)
        
        file = transform(id, size)
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
            p = db.Picture.get(picid)
            if p.catalogue != self.cat:
                raise TraversalError('Image %d is not part of this catalogue' % picid)
        except SQLObjectNotFound, x:
            raise TraversalError(str(x))

        size = m.group(3)
        default = m.group(4) is not None
        ext = m.group(5)

        if ext == '.html':
            return lambda request, self=self, id=id, size=size, default=default: \
                                       self.view(request, id, size, default)

        if size == 'orig':
            return lambda request, self=self, id=picid, size=size, default=default: \
                                       self.image_orig(request, id)
        else:
            return lambda request, self=self, id=picid, size=size, default=default: \
                                       self.image(request, id, size, default)
