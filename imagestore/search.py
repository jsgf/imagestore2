from sets import Set

from quixote.html import htmltext as H, TemplateIO
#from sqlobject.sqlbuilder import AND, OR, IN
from sqlobject import SQLObjectNotFound

from calendarui import int_day

from image import ImageUI
from pages import pre, post, menupane, prefix, plural, join_extra
from db import Picture, Keyword
from dbfilters import mayViewFilter
from calendar_page import picsbyday
from menu import SubMenu, Heading, Link, Separator

def commonKeywords(pics):
    " Returns a set of keywords which are common to all pics "
    if len(pics) == 0:
        return Set()

    ret = Set(pics[0].keywords)

    for p in pics[1:]:
        ret &= Set(p.keywords)

    return ret

def listkeywords(base, kwlist, bigletter=False):
    kwlist.sort()

    r = TemplateIO(html=True)
    
    if not kwlist:
        return r

    if len(kwlist) > 10:
        divide = 'p'
    else:
        divide = 'span'

    char = None

    kwlist.sort()

    for k in kwlist:
        if k[0] != char:
            if char:
                r += H('</%s>\n' % divide) 
            r += H('<%s class="emphasize %s">\n' % (divide, bigletter and 'bigletter' or ''))
            char = k[0]
        r += H('  <a class="kw" href="%s/%s/">%s</a>\n') % (base, k, k)
    if char:
        r += H('</%s>\n' % divide) 

    return r

def group_by_time(pics, unit):
    curtime = None
    curlist = []

    ret = []

    for p in pics:
        time = unit.rounddown(p.record_time)
        if curtime != time:
            if curtime and curlist:
                ret.append((curtime, curlist))
            curtime = time
            curlist = []
        curlist.append(p)

    if curtime and curlist:
        ret.append((curtime, curlist))

    return ret

class KWSearchUI:
    _q_exports = []
    
    def __init__(self, search, collection):
        self.col = collection
        self.search = search
        
        self.kw = []

    def _q_lookup(self, request, element):
        element = element.strip()
        self.kw.append(element)
        return self
    
    def _q_index(self, request):
        # Map keyword strings into Keywords; if any keyword is
        # unknown, then by definition we can't find any images tagged
        # with it
        try:
            kw = [ Keyword.byWord(k) for k in self.kw ]
        except SQLObjectNotFound:
            kw = []

        # List of Sets of pictures for each keyword
        picsets = [ Set(k.pictures) for k in kw ]

        # Find intersection of all sets
        if picsets:
            pics = reduce(lambda a, b: a & b, picsets)
        else:
            pics = []

        # Filter for visibility
        pics = [ p for p in pics if (not p.isPending() and self.col.mayView(request, p)) ]

        # Sort by time
        pics.sort(lambda a,b: cmp(a.record_time, b.record_time))

        request.session.set_query_results(pics)

        r = TemplateIO(html=True)

        # Useless keywords are the ones common to all images in this search
        useless = Set([ k.word for k in commonKeywords(pics) ])

        # Union of all keywords used
        kwset = Set([ k.word for p in pics for k in p.keywords ])

        # The refining set of keywords are the ones which will further
        # restrict the search results
        refining = kwset-useless
        
        #print 'useless=%s, kwset=' % useless
        
        groups = group_by_time(pics, int_day)

        extra = []

        if refining:
            extra += [ Link('refine search', '#refine') ]
        if kwset:
            extra += [ Link('new search', '#replace') ]
        
        if len(groups) > 1:
            skiplist = [ Link(int_day.num_fmt(day), '#' + int_day.num_fmt(day))
                         for (day, dp) in groups ]
            if len(skiplist) > 15:
                factor = len(skiplist) / 15
                skiplist = [ s for (n, s) in zip(range(len(skiplist)), skiplist)
                             if n % factor == 0 ]
            extra += [ SubMenu(heading='Skip to:', items=skiplist) ]

        if len(self.kw) > 1:
            searchstr = ' and '.join([ ', '.join(self.kw[:-1]), self.kw[-1] ])
        elif len(self.kw) == 1:
            searchstr = self.kw[0]
        else:
            searchstr = '(nothing)'
            
        r += pre(request, 'Search for %s: %s' % (searchstr, plural(len(pics), 'picture')),
                 'kwsearch', brieftitle=searchstr)

        r += menupane(request, extra)

        r += H('<h1>Search for %s: %s</h1>\n') % (searchstr, plural(len(pics), 'picture'))

        r += picsbyday(request, groups, self.col)

        if refining:
            # Refine by ANDing more keywords in
            r += H('<div class="title-box kwlist" id="refine">\n')
            r += H('<h2>Refine search</h2>\n')

            r += listkeywords('%s/%s/search/kw/%s' % (prefix,
                                                      self.col.dbobj.name,
                                                      '/'.join(self.kw)),
                              list(refining))
            r += H('</div>\n')

        if len(self.kw) > 1:
            r += H('<div id="expand" class="title-box kwlist">\n')
            r += H('<h2>Expand search (remove keyword)</h2>\n')

            for k in self.kw:
                cur = Set(self.kw)
                cur.remove(k)
                cur = list(cur)
                cur.sort()
                r += H('<a class="kw" href="%s/%s/search/kw/%s/">%s</a>\n') % \
                     (prefix, self.col.dbobj.name, '/'.join(cur), k)
            r += H('</div>\n')

        if kwset:
            r += H('<div id="replace" class="title-box kwlist">\n')
            r += H('<h2>New search</h2>\n')

            r += listkeywords('%s/%s/search/kw' % (prefix, self.col.dbobj.name),
                              list(kwset))
            r += H('</div>\n')

        r += post()

        return r.getvalue()
    
class SearchUI:
    _q_exports = [ 'kw' ]
    
    def __init__(self, collection):
        self.col = collection

        self.kw = KWSearchUI(self, collection)
        
    def _q_index(self, request):
        r = TemplateIO(html=True)

        kw = Keyword.select(Keyword.q.collectionID == self.col.dbobj.id,
                            orderBy=Keyword.q.word)

        r += pre(request, 'Keyword search', 'search', brieftitle='keywords')
        r += menupane(request)

        r += H('<div class="title-box kwlist">\n')
        r += H('<h2>%s</h2>\n') % plural(kw.count(), 'keyword')

        # XXX filter only keywords with (visible) pictures associated with them
        # (and perhaps weight by use)
        r += listkeywords('kw', [ k.word for k in kw ], True)
        r += H('</div>\n')

        r += post();

        return r.getvalue()

    def menupane_extra(self):
        return [ Separator(),
                 SubMenu(heading='Search',
                         items=[Link('by keyword', '%s/%s/search/' % (prefix, self.col.dbobj.name))]) ]

    def search_kw_url(self, kw, d=None):
        return H('%s/%s/search/kw/%s/%s') % (prefix, self.col.dbobj.name, kw,
                                             d and '#' + int_day.num_fmt(d) or '')

    def search_kw_link(self, kw, d=None, extra=None):
        if extra:
            extra = join_extra(extra)

        return H('<a %s href="%s">%s</a>') % (extra or '',
                                              self.search_kw_url(kw, d), kw)
