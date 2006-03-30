# Menu stuff

import copy

from quixote.html import TemplateIO, htmltext as H

def _p(d):
    return ' '*d

class MenuItem:
    def __init__(self, id=None, classes=None, extra=None):
        self.classes = classes and classes[:] or []
        self.classes.append('item')
        self.id = id
        
        self.extra = extra or {}

    def render(self, depth=0):
        pass

    def tags(self):
        import imagestore.pages

        c = ' '.join(self.classes)
        e = imagestore.pages.join_extra(self.extra)
        i=''
        if self.id:
            i = H('id="%s" ') % self.id
            
        return H('%sclass="%s"%s') % (i, c, e and ' '+e or '')

class SubMenu(MenuItem):
    def __init__(self, heading=None, items=None, id=None, classes=None, extra=None):
        MenuItem.__init__(self, id, classes, extra)

        self.classes.append('menu')

        if heading and not isinstance(heading, MenuItem):
            heading = Heading(heading)
        
        self.heading = heading

        self.items = items or []

    def render(self, depth=0):
        r = TemplateIO(html=True)

        if self.heading:
            if isinstance(self.heading, MenuItem):
                r += self.heading.render(depth)
            else:
                r += str(self.heading)

        self.renderitems(r, depth, self.tags())

        return r.getvalue()

    def renderitems(self, r, depth, tags):
        pfx=_p(depth)
        
        r += H('\n%s<ul%s>\n') % (pfx, tags and ' '+tags or '')

        depth += 1
        for i in self.items:
            r += H('%s<li>') % _p(depth)
            r += i.render(depth+1)
            r += H('\n')
            
        r += H('%s</ul>') % pfx

    def addItem(self, item):
        if isinstance(item, list):
            self += item
        else:
            self += [ item ]

    # Emulate a container
    def __len__(self):
        return len(self.items)

    def __getitem__(self, key):
        return self.items[key]

    def __iter__(self):
        return self.items.__iter__()

    def __add__(self, other):
        m = copy.copy(self)
        m.items = self.items[:]

        m += other

        return m

    def __iadd__(self, other):
        if isinstance(other, SubMenu):
            if other.heading:           # XXX imperfect - what to do?
                self.items += [ other.heading ]
            self.items += other.items
        elif isinstance(other, list):
            self.items += other
        else:
            raise TypeError('May only append lists and Menus to Menus')

        return self
    
class Menu(SubMenu):
    def __init__(self, items=None, id="top", classes=None, extra=None):
        SubMenu.__init__(self, items=items, id=id, classes=classes, extra=extra)

    def render(self, depth=0):
        r = TemplateIO(html=True)

        pfx=_p(depth)
        r += H('%s<div %s>') % (pfx, self.tags())
        self.renderitems(r, depth+1, None)
        r += H('\n%s</div>\n') % pfx

        return r.getvalue()
    
class Link(MenuItem):
    def __init__(self, link, url, classes=None, extra=None):
        MenuItem.__init__(self, classes=classes, extra=extra)

        self.classes.append('link')

        self.link = link
        self.url = url

    def render(self, depth=0):
        return H('<a %s href="%s">%s</a>') % (self.tags(), self.url, self.link)

class Heading(MenuItem):
    def __init__(self, head, classes=None, extra=None):
        MenuItem.__init__(self, classes=classes, extra=extra)

        self.classes.append('heading')
        
        self.head = head

    def render(self, depth=0):
        return H('<span %s>%s</span>') % (self.tags(), self.head)

class Separator(MenuItem):
    def __init__(self, classes=None, extra=None):
        MenuItem.__init__(self, classes=classes, extra=extra)

        self.classes.append('separator')

    def render(self, depth=0):
        return H('<hr %s />') % self.tags()
