# Navigation controls

from quixote.html import htmltext as H, TemplateIO

import imagestore.pages as page

_def_link = {
    'first':    ('%(a)s%(a)s&nbsp;%%(link)s' % { 'a': page.arrow('left') }),
    'prev':     ('%(a)s&nbsp;%%(link)s' % { 'a': page.arrow('left') }),
    'next':     ('%%(link)s&nbsp;%(a)s' % { 'a': page.arrow('right') }),
    'last':     ('%%(link)s&nbsp;%(a)s%(a)s' % { 'a': page.arrow('right') }),
}

class _link:
    def __init__(self, rel, url, link, title):
        self.rel = rel
        self.url = url
        self.link = link
        self.title = title

    def render(self, depth=0):
        link = self.link

        title = self.title

        if link is None:
            link = H(_def_link[self.rel]) % { 'link': self.rel.capitalize() }

        title = title and (H('title="%s"') % title) or H('')

        return H('%s<a class="%s" %s href="%s">%s</a>\n') % ('  '*depth, self.rel,
                                                             title, self.url, link)

    def render_link(self, depth=0):
        return H('%s<link rel="%s" href="%s">\n') % ('  '*depth, self.rel, self.url)
    
class Nav:
    def __init__(self, request):
        self.request = request
        
        self.next = None
        self.prev = None
        self.first = None
        self.last = None

        self.options = []

    def set_first(self, url, link=None, title=None):
        assert self.first is None, 'resetting first?'
        self.first = _link('first', url, link, title)

    def set_last(self, url, link=None, title=None):
        assert self.last is None, 'resetting last?'
        self.last = _link('last', url, link, title)

    def set_next(self, url, link=None, title=None):
        assert self.next is None, 'resetting next?'
        self.next = _link('next', url, link, title)

    def set_prev(self, url, link=None, title=None):
        assert self.next is None, 'resetting prev?'
        self.prev = _link('prev', url, link, title)

    def add_option(self, url, link, title=None, selected=False, extra=None):
        self.options.append((url, link, title, selected, extra))
        
    def render_links(self, depth=0):
        r = TemplateIO(html=True)

        if self.first:
            r += self.first.render_link(depth)

        if self.prev:
            r += self.prev.render_link(depth)
        elif len(self.request.session.breadcrumbs) > 1:
            r += H('%s<link rel="prev" href="%s">\n') % ('  '*depth,
                                                         self.request.session.breadcrumbs[-2][1])
            
        if self.next:
            r += self.next.render_link(depth)

        if self.last:
            r += self.last.render_link(depth)

        return r.getvalue()

    def render_options(self, depth=0):
        r = TemplateIO(html=True)
            
        if self.options:
            pfx = '  '*depth
            r += H('%s<span class="options">\n') % pfx
            for url,link,title,selected,extra in self.options:
                t = title and (H('title="%s"') % title) or ''
                if extra is None:
                    extra = {}
                r += H('%(pfx)s  <a %(title)s class="%(sel)s" href="%(url)s" %(extra)s>%(link)s</a>\n') % {
                    'pfx': pfx,
                    'title': t,
                    'sel': selected and 'selected' or '',
                    'url': url,
                    'link': link,
                    'extra': page.join_extra(extra)
                    }
            r += H('%s</span>\n') % pfx
        return r.getvalue()

    def render(self, depth=0):
        p='  '*depth
        r = TemplateIO(html=True)

        r += H('%s<div id="nav">\n') % p

        if self.first:
            r += self.first.render(depth+1)

        if self.prev:
            r += self.prev.render(depth+1)

        if self.options:
            r += self.render_options(depth+1)
            
        if self.next:
            r += self.next.render(depth+1)

        if self.last:
            r += self.last.render(depth+1)

        r += H('%s</div>\n') % p

        return r.getvalue()
