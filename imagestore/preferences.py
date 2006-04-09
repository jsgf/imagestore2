
import urllib
import json

import quixote

import imagestore.ImageTransform as ImageTransform

class PreferenceError(Exception):
    pass

class Property(object):
    __slots__ = ['default', 'validset']
    
    def __init__(self, default, validset):
        self.default = default
        self.validset = validset
        
    def valid(self, v):
        return v in self.validset

    def encode(self, v):
        print 'encoding "%s"' % v
        v = self.tocookie(v)
        v = json.write(v)
        v = urllib.quote(v)
        return v

    def decode(self, v):
        if v is None:
            return None
        v = urllib.unquote(v)
        v = json.read(v)
        v = self.fromcookie(v)
        return v
    
    def fromcookie(self, v):
        return v

    def tocookie(self, v):
        return v

class BoolProperty(Property):
    __slots__ = []
    
    def __init__(self, default):
        Property.__init__(self, default, (True, False))

class SizeProperty(Property):
    __slots__ = []

    def __init__(self, default):
        Property.__init__(self, default, ImageTransform.sizes.keys())

    def tocookie(self, v):
        return [ v, ImageTransform.sizes[v]]

    def fromcookie(self, v):
        return v[0]
    
def _propname(pref):
    return '_pref_%s' % pref

class Preferences(object):
    @staticmethod
    def _cookiename(pref):
        return 'IS-pref-%s' % pref

    __properties__ = {
        # property: (default-value, validator) tuples
        'view_new_window':      BoolProperty(True),
        'resize_view':          BoolProperty(False),
        'image_size':           SizeProperty('medium'),

        'want_edit':            BoolProperty(True),
        }

    __slots__ = [ 'parent' ] + \
                [ _propname(k) for k in __properties__.keys() ] + \
                __properties__.keys()

    def __init__(self, parent):
        self.parent = parent
        
    def _set_pref(self, pref, value):
        prop = self.__properties__[pref]

        if not prop.valid(value):
            raise PreferenceError('bad value')
        
        setattr(self, _propname(pref), value)
        response = quixote.get_response()
        response.set_cookie(self._cookiename(pref), prop.encode(value), path=self.parent.path())

    def _del_pref(self, pref):
        delattr(self, _propname(pref))
        response = quixote.get_response()
        response.expire_cookie(self._cookiename(pref), path=self.parent.path())

    def _get_pref(self, pref):
        prop = self.__properties__[pref]

        ret = getattr(self, _propname(pref), None)
        if ret is None:
            request = quixote.get_request()
            ret = prop.decode(request.get_cookie(self._cookiename(pref)))
            if ret is None:
                ret = prop.default
                self._set_pref(pref, ret)

        return ret

    def set_client(self, pref, val):
        """ Return some javascript to set the preference on the client side. """
        prop = self.__properties__[pref]
        assert prop.valid(val)
        return """document.cookie='%s=%s;path=%s'""" % (self._cookiename(pref),
                                                        prop.encode(val),
                                                        self.parent.path())

import imagestore
p = Preferences(imagestore)

# Set a property for each preference
for k in Preferences.__properties__.keys():
    def pget(self, k=k):
        return self._get_pref(k)
    def pset(self, value, k=k):
        self._set_pref(k, value)
    def pdel(self, k=k):
        self._del_pref(k)

    setattr(Preferences, k, property(fget=pget, fset=pset,
                                     fdel=pdel, doc='%s preference' % k))
