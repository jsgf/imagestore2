import gc

from quixote.session import Session
from quixote.publish import SessionPublisher

from sqlobject import SQLObjectNotFound

from cPickle import load, dump
import os
from stat import ST_MTIME
from time import time

from db import User, conn

class ImagestorePublisher(SessionPublisher):
    def __init__(self, *args, **kwargs):
        SessionPublisher.__init__(self, *args, **kwargs)

        # (Optional step) Read a configuration file
        self.read_config("imagestore/config.conf")

        # Open the configured log files
        self.setup_logs()

class ImagestoreSession(Session):
    def __init__(self, request, id):
        Session.__init__(self, request, id)
        self.dirty = False
        
        self.user = None
        self.results = []
        self.breadcrumbs = []
        
        self.wantedit = False               # true if the user wants to edit things
        
    def start_request(self, request):
        Session.start_request(self, request)

    def finish_request(self, request):
        # clean up after request, to make sure
        # nothing is cached too long
        gc.collect()
        
    def has_info(self):
        return self.user is not None or \
               (self.results is not None and len(self.results) != 0) or \
               self.breadcrumbs or \
               Session.has_info(self)

    def is_dirty(self):
        r = (self.has_info() and self.dirty) or self._form_tokens
        self.dirty = False
        return r

    def setuser(self, user):
        if user != self.user:
            self.user = user
            self.dirty = True
            self.breadcrumbs = []

    def getuser(self):
        if self.user is None:
            return None

        try:
            #print 'self.user=%s' % self.user
            return User.get(self.user)
        except SQLObjectNotFound:
            self.user=None
            return None

    def set_query_results(self, pics):
        self.results = [ p.id for p in pics ]
        self.dirty = True

    def get_results_neighbours(self, cur):
        if self.results is None:
            return (None, None)
        if cur not in self.results:
            return (None, None)

        idx = self.results.index(cur)

        prev = None
        next = None
        if idx > 0:
            prev = self.results[idx-1]
        if idx < len(self.results)-1:
            next = self.results[idx+1]
        return (prev, next)

    def get_result_ends(self):
        if self.results is None:
            return (None,None)

        return (self.results[0], self.results[-1])
    
    def add_breadcrumb(self, title, url, desc):
        t = (str(title), str(url), desc and str(desc))
        try:
            idx = self.breadcrumbs.index(t)
        except ValueError:
            idx = len(self.breadcrumbs)

        newlist = self.breadcrumbs[:idx] + [ t ]
        newlist = newlist[-10:]

        if newlist != self.breadcrumbs:
            self.dirty = True
            self.breadcrumbs = newlist

    def del_breadcrumb(self):
        del self.breadcrumbs[-1]
        self.dirty = True

class DirMapping:
    """A mapping object that stores values as individual pickle
    files all in one directory.  You wouldn't want to use this in
    production unless you're using a filesystem optimized for
    handling large numbers of small files, like ReiserFS.  However,
    it's pretty easy to implement and understand, it doesn't require
    any external libraries, and it's really easy to browse the
    "database".
    """

    def __init__ (self, save_dir=None):
        self.set_save_dir(save_dir)
        self.cache = {}
        self.cache_time = {}

    def set_save_dir (self, save_dir):
        self.save_dir = save_dir
        if save_dir and not os.path.isdir(save_dir):
            os.mkdir(save_dir, 0700)
    
    def keys (self):
        return os.listdir(self.save_dir)

    def values (self):
        # This is pretty expensive!
        return [self[id] for id in self.keys()]

    def items (self):
        return [(id, self[id]) for id in self.keys()]

    def _gen_filename (self, session_id):
        return os.path.join(self.save_dir, session_id)

    def __getitem__ (self, session_id):

        filename = self._gen_filename(session_id)
        if (self.cache.has_key(session_id) and
            os.stat(filename)[ST_MTIME] <= self.cache_time[session_id]):
            return self.cache[session_id]

        if os.path.exists(filename):
            try:
                file = open(filename, "rb")
                try:
                    print "loading session from %r" % file
                    session = load(file)
                    self.cache[session_id] = session
                    self.cache_time[session_id] = time()
                    return session
                finally:
                    file.close()
            except IOError, err:
                raise KeyError(session_id,
                               "error reading session from %s: %s"
                               % (filename, err))
        else:
            raise KeyError(session_id,
                           "no such file %s" % filename)

    def get (self, session_id, default=None):
        try:
            return self[session_id]
        except KeyError:
            return default

    def has_key (self, session_id):
        return os.path.exists(self._gen_filename(session_id))

    def __setitem__ (self, session_id, session):
        filename = self._gen_filename(session.id)
        file = open(filename, "wb")
        print "saving session to %s" % file
        dump(session, file, 1)
        file.close()

        self.cache[session_id] = session
        self.cache_time[session_id] = time()

    def __delitem__ (self, session_id):
        filename = self._gen_filename(session_id)
        if os.path.exists(filename):
            os.remove(filename)
            if self.cache.has_key(session_id):
                del self.cache[session_id]
                del self.cache_time[session_id]
        else:
            raise KeyError(session_id, "no such file: %s" % filename)

class ImagestoreSessionMapping(DirMapping):
    def __init__(self):
        print 'making an ImagestoreSessionMapping'
        DirMapping.__init__(self, save_dir='./session/')
