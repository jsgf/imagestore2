use MaskTools, CookieAuthenticate

from db import *
from mx.DateTime import DateTime, RelativeDateTime, strptime, today
from string import join
import re

import ImageTransform
from ImageTransform import transformed_size, transform, data_from_Image, Image_from_data

def onError():
    # Get the error in a string
    import traceback, StringIO
    bodyFile=StringIO.StringIO()
    traceback.print_exc(file=bodyFile)
    errorBody=bodyFile.getvalue()
    bodyFile.close()
    # Set the body of the response
    response.body="<html><body><br><br><center>"
    response.body+="Sorry, an error occured<br>"
    response.body+="An email has been sent to the webmaster"
    response.body+="</center><pre>"
    response.body+=tools.escapeHtml(errorBody)
    response.body+="</pre></body></html>"

# Use this to map nice user-friendly URLs into the CherryPy namespace
# This is to get rid of visible foo?blah=blat&biff=foo type URL paths
# (though they'll still work)
def initNonStaticRequest():
    print '%s request.path: %s' % (request.method, request.path)
    
    # match /image/1234-size.jpg and map back to
    # /image/image?id=1234&size=<size> so that we can refer to images with
    # browser-friendly names
    m = re.search('^image/([0-9]+)(-(%s|orig)(!)?)?.[a-z]+$' % (join(ImageTransform.sizes.keys(), '|')),
                  request.path)
    if m is not None:
        #request.cacheKey=request.browserUrl
        #request.cacheExpire=time.time()+30*60 # 30 minutes
        if m.group(3) == 'orig':
            request.path='image/orig'
            request.paramMap = {'id': m.group(1)}
        else:
            request.path='image/image'
            request.paramMap = {'id': m.group(1),
                                'size': m.group(3)
                                }
            if m.group(4) is not None:
                request.paramMap['preferred'] = True
        return

    # match /image/view/1234-size!.html
    m = re.search('^image/view/([0-9]+)(-(%s|orig)(!)?)?\.html$' % (join(ImageTransform.sizes.keys(), '|')),
                  request.path)
    if m is not None:
        request.path='image/view'
        request.paramMap = {'id': m.group(1),
                            'size': m.group(3)
                            }
        if m.group(4) is not None:
            request.paramMap['preferred'] = True
        return
    
    # match /image/(edit|details)/1234.jpg
    m = re.search('^image/(edit|details)/([0-9]+)(\.[a-z]+)?', request.path)
    if m is not None:
        request.path='image/' + m.group(1)
        request.paramMap= { 'id': m.group(2) }
        return

    # match /calendar/(interval)/(date)
    m = re.search('^calendar/(%s)(/([0-9-]+))?$' % join(calendar.interval.keys(), '|'),
                  request.path)
    if m is not None:
        request.path='calendar'
        request.paramMap = {'date': m.group(3),
                            'interval': m.group(1) }
        return

def initNonStaticResponse():
    if response.headerMap['content-type'] == 'text/html':
        response.headerMap['content-type'] += '; charset=utf-8'
        
##
## Everything related to the display of images
##
CherryClass Image:
variable:
    # map types to extensions
    extmap = ImageTransform.extmap
    # map extensions to types
    typemap = ImageTransform.typemap
    # list of sizes
    sizes = ImageTransform.sizes.keys()

    # Margins of view window (must match the stylesheet)
    view_margin = 10


    # Cookie names
    ck_preferred_size = 'imagestore-preferred-size'
    
function:
    ##
    ## *_url functions generate a URL for a particular page type
    ##
    def view_url(self, id, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''
        return "%s/image/view/%d%s.html" % (root.base, id, size)

    def picture_url(self, id, size, preferred=False):
        if size is not None:
            size = '-'+size
            if preferred:
                size += '!'
        else:
            size = ''
        return "%s/image/%d%s.%s" % (root.base, id, size, self.extmap[Picture(id).mimetype])

    def thumb_url(self, id):
        return "%s/image/%d-thumb.jpg" % (root.base, id)

    def details_url(self, id):
        return '%s/image/details/%d.html' % (root.base, id)

    def edit_url(self, id):
        return '%s/image/edit/%d.html' % (root.base, id)


    ##
    ## Manage preference cookies
    ##
    def preferred_size(self, default='medium'):
        ret = default
        try:
            ret = request.simpleCookie[self.ck_preferred_size].value
            if ret not in self.sizes:
                ret = default            
        except KeyError, x:
            pass
        return ret

    def set_preferred_size(self, size):
        if size not in self.sizes:
            return
        response.simpleCookie[self.ck_preferred_size]=size
        response.simpleCookie[self.ck_preferred_size]['path']='/'
        response.simpleCookie[self.ck_preferred_size]['version']=1
            
    def sorted_sizes(self):
        s=ImageTransform.sizes.items()
        s.sort(lambda a,b: cmp(a[1][0]*a[1][1], b[1][0]*b[1][1]))
        return [ a for (a,b) in s ]

    ###
    ### The following functions build pieces of HTML for insertion in
    ### the output
    ###    
    def picture_img(self, id, size, preferred=False, extra={}):
        "Generate an <img> element for a picture"
        e = join([ '%s="%s"' % (k, tools.escapeHtml(extra[k])) for k in extra.keys() ], ' ')
        (pw,ph) = ImageTransform.transformed_size(id, size)
        
        return '<img class="picture" width=%(w)d height=%(h)d style="width:%(w)dpx height:%(h)dpx" alt="%(alt)s" %(extra)s src="%(ref)s">' % \
               { 'w': pw,
                 'h': ph,
                 'alt': 'Picture number %d' % id,
                 'extra': e,
                 'ref': self.picture_url(id, size, preferred) }
    

    def thumb_img(self, id, extra={}):
        "Generate an <img> element for a thumbnail"
        p = Picture(id)
        e = join([ '%s="%s"' % (k, tools.escapeHtml(extra[k])) for k in extra.keys() ], ' ')

        (tw,th) = ImageTransform.thumb_size(id)
        
        return '<img class="thumb" width=%(w)d height=%(h)d style="width: %(w)dpx height: %(h)dpx" alt="%(alt)s" %(extra)s src="%(ref)s">' % \
               { 'w': tw,
                 'h': th,
                 'alt': 'Thumbnail of picture %d' % id,
                 'extra': e,
                 'ref': self.thumb_url(id) }

    def picture_link(self, id, size, **extra):
        "Generate a link to a image, with the thumbnail as the link contents"
        return '<a href="%s">%s</a>' % (self.picture_url(id, size), self.thumb_img(id))

    def view_link(self, id, size=None, link=None, preferred=False, extra={}):
        """Generate a link to a full-sized image.  By default, the
        thumbnail is the link contents."""
        
        if size is None:
            size = self.preferred_size(None)
        
        if link is None:
            link = self.thumb_img(id)

        e = join([ '%s="%s"' % (k, tools.escapeHtml(extra[k])) for k in extra.keys() ], ' ')
            
        return "<a %(extra)s href=\"%(url)s\">%(link)s</a>" % {
            'url': self.view_url(id, size, preferred),
            'link': link,
            'extra': e,
            }

    def view_newwin_link(self, id, size=None, link=None, preferred=False, extra={}):
        "Generate a link to a full-sized image, which will open a new window."

        if size is None:
            size = self.preferred_size(None)
        
        extra['target']='%d' % id

        if size is not None:
            (tw,th) = ImageTransform.transformed_size(id, size)
        else:
            (tw,th) = (640,480)
            
        extra['onClick'] = "newwin = window.open('', '%(id)d', 'width=%(w)d,height=%(h)d,resizable=1,scrollbars=0');" % {
            'id': id,
            'w': tw + (2*self.view_margin),
            'h': th + (2*self.view_margin),
            }
        return self.view_link(id, size=size, link=link, preferred=preferred, extra=extra)

    def details_link(self, id, link):
        return '<a href="%s">%s</a>' % (self.details_url(id), link)
        
    def edit_link(self, id, link):
        return '<a href="%s">%s</a>' % (self.edit_url(id), link)
        
    def query_neighbours(self, id):
        """If Picture(id) is in the results list of the last query,
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

    def detail_string(self, id, orientfn=None):
        if orientfn is None:
            orientfn = lambda a: ''
            
        p = Picture(id)
        
        ret="""
        <table border=0>
        <tr>
                <td>Top:</td>
                <td align="center">
                        %(orient0)s
                </td>
                <td></td>
                <td rowspan=3>
                        <table border=0>
			<tr><td align=right><b>Create date</b></td><td>%(create_time)s</td></tr>
			<tr><td align=right><b>Exposure time</b></td><td>%(shutter)s</td></tr>
			<tr><td align=right><b>F-Number</b></td><td>%(fnumber)s</td></tr>
			<tr><td align=right><b>Program-mode</b></td><td>%(program)s</td></tr>
			<tr><td align=right><b>Exposure bias</b></td><td>%(exp_bias)s EV</td></tr>
			<tr><td align=right><b>Focal length</b></td><td>%(focal)d mm</td></tr>
			<tr><td align=right><b>Dimensions</b></td><td>%(width)dx%(height)d</td></tr>
                        </table>
                </td>
        </tr>
        <tr>
                <td>%(orient270)s</td>
                <td>%(thumb)s</td>
                <td>%(orient90)s</td>
        </tr>
        <tr>
                <td></td>
                <td align="center">%(orient180)s</td>
                <td>%(orient)d &deg;</td>
        </tr>
        </table>
        """ % {
                    'orient':           p.orientation,
                    'orient0':          orientfn(0),
                    'orient90':         orientfn(90),
                    'orient180':        orientfn(180),
                    'orient270':        orientfn(270),

                    'create_time':      p.record_time.strftime('%Y-%m-%d %H:%M'),
                    'shutter':          p.exposure_time,
                    'fnumber':          p.f_number,
                    'exp_bias':         p.exposure_bias,
                    'focal':            p.focal_length,
                    'width':            p.width,
                    'height':           p.height,
                    'program':          p.exposure_program,

                    'thumb':            self.view_link(id),
                    }
                
        return ret
        
view:
    def orig(self, id):
        "Generate the raw data for an image - this generates a series of streamed chunks"
        id = int(id)
        p = Picture(id)

        response.sendResponse = 0

        response.wfile.write(("HTTP/1.0 200\r\n"+
                              "Content-Type: %(type)s\r\n"+ 
                              "Content-Length: %(len)d\r\n"+
                              'Last-Modified: %(modtime)s GMT\r\n'
                              "\r\n") % { 'type': p.mimetype,
                                          'len': p.datasize,
                                          'modtime': p.modified_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
                                          })

        for c in p.getimagechunks():
            response.wfile.write(c)

        return ''

    def image(self, id, size=None, preferred=False):
        id=int(id)

        if size is None:
            size = self.preferred_size()
        elif preferred:
            self.set_preferred_size(size)
            
        ret = ''
        file = ImageTransform.transform(id, size)
        for d in file:
            ret += d

        p=Picture(id)
        response.headerMap["content-type"] = 'image/jpeg'
        response.headerMap['content-length'] = len(ret)
        response.headerMap['last-modified'] = p.modified_time.strftime('%a, %d %b %Y %H:%M:%S GMT')

        if request.method == 'HEAD':
            ret=''
        return ret

    def view(self, id=None, size=None, preferred=False):
        """Generate an HTML wrapper for an image being viewed"""
        id=int(id)

        (prev,next) = self.query_neighbours(id)
        
        if size is None:
            size = self.preferred_size()
        elif size == 'orig':
            return self.orig(id)
        elif preferred:
            self.set_preferred_size(size)
        
        (pw,ph) = ImageTransform.transformed_size(id, size)
        
        ret = ''
        ret += """
        <script language="JavaScript"><!--
                window.resizeTo(%(w)d, %(h)d)
        --></script>\n""" % { 'w': pw+(2*self.view_margin), 'h': ph+(2*self.view_margin) }
        
        p = Picture(id)

        ret += '<div class="nav">\n'
        if prev is not None:
            ret += self.view_link(prev, size, '&lt;&lt;&nbsp;Prev',
                                  extra={'title': 'Image %d' % prev,
                                         'class': 'prev'}) + '\n'

        ret += '<span class="size">\n'
        for s in self.sorted_sizes():
            if ImageTransform.sizes[s][0]*ImageTransform.sizes[s][1] < (640*480):
                continue
            sel=''
            if s == size:
                sel='selected'
            ret += self.view_link(id, s, s.capitalize(), preferred=True,
                                  extra={'title': '%dx%d' % ImageTransform.transformed_size(id, s),
                                         'class': sel}) + '\n'
        ret += self.view_link(id, 'orig', 'Original', extra={'title': 'For printing'}) + '\n'
        ret += '</span>\n'

        if next is not None:
            ret += self.view_link(next, size, 'Next&nbsp;&gt;&gt;',
                                  extra={'title': 'Image %d' % next,
                                         'class': 'next'}) + '\n'

        ret += '</div>\n'

        ret += self.details_link(id, self.picture_img(id, size, preferred)) + '\n'

        return root.pre('View image %d' % id, 'view') + ret + root.post()

    def edit(self, id):
        id = int(id)

        # XXX check for user permissions to edit
        p = Picture(id)
        def orientfn(a):
            checked=''
            if a == 0:
                checked=' checked'
            return '<input name="orient" type="radio" value="%d"%s>' % ((a + p.orientation)%360, checked)
        
        ret = '<form method="post">\n' + self.detail_string(id, orientfn) + '</form>'

        print 'exposure=%s' % p.exposure_time
        return root.pre('Edit image %d' % id) + ret + root.post()

    def details(self, id):
        id = int(id)

        return root.pre('Details for %d' % id) + self.detail_string(id) + root.post()

##
## Calendar/time-related display
##
CherryClass Calendar:
variable:
    # Midnight on the Date
    zeroTime = RelativeDateTime(hour=0,minute=0,second=0)
    # A base for RelativeDateTime comparisons
    zeroDate = DateTime(0,1,1,0,0,0)

    # Just less than one day
    subDay = RelativeDateTime(hours=+23, minutes=+59, seconds=+59)
    
    interval = { 'day':         RelativeDateTime(days=+1),
                 'week':        RelativeDateTime(weeks=+1),
                 'month':       RelativeDateTime(months=+1),
                 'year':        RelativeDateTime(years=+1),
                 }

function:
    ##
    ## *_url functions generate a URL for a particular page type
    ##
    def calendar_url(self, interval, date):
        return '%s/calendar/%s/%s' % (root.base, interval, date.strftime('%Y-%m-%d'))

    def intervalList(self):
        i=self.interval.items()
        i.sort(lambda a,b: cmp(self.zeroDate+a[1],self.zeroDate+b[1]))
        return i

    def build_calendar(self, date_start, date_end=None, date_inc=None, filter=None):

        """ Returns a list of lists of images within a certain date
        range.  The outer list is a list of tuples (date, piclist)
        tuples, where piclist is a list of Pictures in record_time
        order.
        """
        
        if date_end is None:
            if date_inc is None:
                raise 'need date_end or date_inc'
            date_end = date_start+date_inc

        date_start += self.zeroTime     # round down to start of day
        date_end = (date_end + self.subDay) + self.zeroTime # round up to next day

        q=(Picture.q.record_time >= date_start) & (Picture.q.record_time < date_end)
        if filter is not None:
            q = q & filter
        pics = Picture.select(q, orderBy='record_time')
        today=date_start
        days = []
        piclist = []
        
        for p in pics:
            pdate = p.record_time + self.zeroTime
            
            if today is None or pdate != today:
                #print "new day %s" % pdate
                if len(piclist) != 0 and today is not None:
                    days.append((today, piclist))
                piclist = []
                today = pdate
                
            piclist.append(p)
            
        if len(piclist) != 0 and today is not None:
            days.append((today, piclist))
        return days


    def time_summary(self, unit='week'):        
        pics = Picture.select(orderBy='record_time')
        if pics.count() == 0:
            return '(no images)'

        # Get the image record date, but set the time to 0
        date = pics[0].record_time + self.zeroTime
        next = date + interval[unit]

        entries = []
        while Picture.select(Picture.q.record_time >= date).count() > 0:
            pics = Picture.select((Picture.q.record_time >= date) &
                                  (Picture.q.record_time < next)).count()
            if pics > 0:
                entries.append((date, next, pics))
            date = next
            next = next + interval[unit]

        return entries

view:
    def index(self, date=None, interval='week'):
        path=request.path
        reltime = self.interval[interval]
        if date is None:
            # If no date provided, show images in the last interval
            date = today()-reltime
        else:
            date = strptime(date, '%Y-%m-%d')
        
        days = self.build_calendar(date, date_inc=reltime)
        ret=""
        if len(days) == 0:
            ret += "No images in specified range.<br>"

        prev = Picture.select(Picture.q.record_time < date, orderBy='-record_time')
        if prev.count() > 0:
            prev = prev[0].record_time + self.zeroTime
            ret += '<a href="%s">Prev</a>\n' % self.calendar_url(interval, prev-reltime+1)
            
        next = Picture.select(Picture.q.record_time >= (date+reltime), orderBy='record_time')
        if next.count() > 0:
            next = next[0].record_time + self.zeroTime
            ret += '<a href="%s">Next</a>\n' % self.calendar_url(interval, next)

        ret += "<br>"

	# Get a sorted list of available intervals
        for i,v in self.intervalList():
            sel=''
            if i == interval:
                sel='selected'
            ret += '<a class="%s" href="%s">%s</a>\n' % (sel, self.calendar_url(i, date), i)

        query_results=[]
        idx=0
        for d,pl in days:
            ret += '<div class="day">\n'
            ret += '<a class="day-link" href="%s">%s</a>\n' % (self.calendar_url('day', d), d.strftime('%Y-%m-%d'))
            for p in pl:
                query_results.append(p.id)
                ret += image.view_newwin_link(p.id) + '\n'
                idx+=1
            ret += '</div>\n'

        request.sessionMap['query-results'] = query_results
        return root.pre('Calendar', 'calendar') + ret + root.post()

    
CherryClass Root:
variable:
    # Base prepended to all URLs
    base = ''

function:
    def pre(self, title, bodyclass=None):
        if bodyclass is None:
            bodyclass = ''
        else:
            bodyclass = 'class="%s"' % bodyclass
            
        return """
        <!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
        <html>
        <head>
        <title>%(title)s</title>
        <link type="text/css" rel="stylesheet" href="/static/style.css">
        </head>
        <body %(class)s>
        """ % { 'title': title, 'class': bodyclass }

    def post(self):
        return """
        </body>
        </html>
        """
    
view:
    def index(self, page=1):
        page = int(page)
        
        s = Picture.select()
        pages = (s.count() + 19) / 20

        ret="<h1>Page %d/%d</h1>" % (page, pages)

        for p in range(1, pages+1):
            ret += '<a href="index?page=%(page)d">%(page)d</a>\n' % { 'page': p }
        ret += '<br>'

        col=0
        for i in s[(page-1)*20:page*20]:
            ret += image.view_newwin_link(i.id) + '\n'
            col += 1
            if col==5:
                col=0
                ret = ret+'<br>'
        ret = ret + '<br>'
        if page > 1:
            ret += '<a href="index?page=%d">Prev page</a>' % (page-1)
        if page < pages:
            ret += ' <a href="index?page=%d">Next page</a>' % (page+1)
        return self.pre('Summary') + ret + self.post()

    def summary_table(self, unit='week'):
        return maskTools.displayByColumn([ '%s - %s: %d' % (e[0].strftime('%Y-%m-%d'),
                                                            e[1].strftime('%Y-%m-%d'),
                                                            e[2])
                                           for e in self.time_summary(unit)],
                                         numberOfColumns=5)

    def login(self, referrer=None, user=None, password=None):
        return ''

    def logout(self, referrer=None):
        return ''

mask: 



# Local Variables:
# mode: python
# clean-up-trailing-only: t
# End:
