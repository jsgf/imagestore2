from sets import Set

from quixote.html import htmltext as H, TemplateIO
#from sqlobject.sqlbuilder import AND, OR, IN
from sqlobject import SQLObjectNotFound

from calendarui import int_day

from image import ImageUI
from pages import pre, post, menupane, prefix
from db import Picture, Keyword
from dbfilters import mayViewFilter

def listkeywords(base, kwlist, bigletter=False):
    kwlist.sort()

    r = TemplateIO(html=True)
    
    if not kwlist:
        return r

    if len(kwlist) > 10:
        divide = 'P'
    else:
        divide = 'SPAN'

    char = None

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

        sets = [ Set(k.pictures) for k in kw ]

        # Find intersection of all sets
        if sets:
            pics = reduce(lambda a, b: a & b, sets)
        else:
            pics = []

        # Filter for visibility
        pics = [ p for p in pics if self.col.mayView(request, p) ]

        # Sort by time
        pics.sort(lambda a,b: cmp(a.record_time, b.record_time))

        request.session.set_query_results([ p.id for p in pics ])

        r = TemplateIO(html=True)

        r += pre(request, 'Search for %s' % (' and '.join(self.kw)), 'kwsearch')

        # Useless keywords are common to all images in this search
        useless = Set([ k.word for k in pics[0].keywords ])
        for p in pics[1:]:
            useless &= Set([ k.word for k in p.keywords ])

        kwset = Set([ k.word for p in pics for k in p.keywords ])
        kwset -= useless
        kwset = list(kwset)
        kwset.sort()

        groups = group_by_time(pics, int_day)

        extra = self.search.menupane_extra()
        
        if len(groups) > 1:
            skiplist = [ ( H(int_day.num_fmt(day)), '#' + H(int_day.num_fmt(day)) )
                         for (day, dp) in groups ]
            if len(skiplist) > 15:
                factor = len(skiplist) / 15
                skiplist = [ s for (n, s) in zip(range(len(skiplist)), skiplist)
                             if n % factor == 0 ]
            extra.append([ 'Skip to:', skiplist ])

        r += menupane(request, extra)

        r += H('<h1>Search for %s: %d pictures</h1>\n') % (' and '.join(self.kw), len(pics))

        if kwset:
            r += H('<p><a href="#refine">(refine search)</a><br clear="both">\n')


        for (day, dp) in groups:
            r += H('<div class="day">\n')
            r += H('<h3 id="%s"><a href="%s">%s</a></h3>\n') % \
                 (int_day.num_fmt(day),
                  self.col.calendar.calendar_url(int_day, day),
                  int_day.num_fmt(day))

            for p in dp:
                r += '  ' + ImageUI(self.col).view_rotate_link(request, p) + '\n'
            r += H('</div>\n')

        if kwset:
            r += H('<div class="title-box kwlist" id="refine">\n')
            r += H('<h2>Refine search</h2>\n')

            r += listkeywords('%s/%s/search/kw/%s' % (prefix,
                                                      self.col.dbobj.name,
                                                      '/'.join(self.kw)),
                              kwset)
            r += H('</div>\n')

        if len(self.kw) > 1:
            r += H('<div class="title-box kwlist">\n')
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
            r += H('<div class="title-box kwlist">\n')
            r += H('<h2>Replace search</h2>\n')
            r += listkeywords('%s/%s/search/kw' % (prefix, self.col.dbobj.name),
                              kwset)
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

        r += pre('Search', 'search')
        r += menupane(request, self.menupane_extra())

        kw = Keyword.select(Keyword.q.collectionID == self.col.dbobj.id,
                            orderBy=Keyword.q.word)

        r += H('<div class="title-box kwlist">\n')
        r += H('<h2>%s keywords</h2>\n' % kw.count())

        r += listkeywords('kw', [ k.word for k in kw ], True)
        r += H('</div>\n')

        r += post();

        return r.getvalue()

    def menupane_extra(self):
        return [ 'Search',
                 [ ('by keyword', '%s/%s/search/' % (prefix, self.col.dbobj.name)) ] ]
