
from mx.DateTime import RelativeDateTime, DateTime, strptime, Error as DTError, oneDay, oneSecond
from quixote.errors import TraversalError, QueryError
from quixote.html import htmltext
from db import Picture
from sqlobject.sqlbuilder import AND, OR
from pages import pre, post, menupane, error, prefix
from calendar_page import _q_index_ptl, most_recent
from calendar import monthrange, monthcalendar

def yrange(start, stop, inc):
    ' A generic range supporting any type with comparison and += '
    v = start

    while v < stop:
        yield v
        v += inc

def pics_in_range(start, end=None, delta=None, filter=None):
    ' return a select result for pics from start - start+delta '
    if end is None:
        end = start + delta
        
    q = [ Picture.q.record_time >= start, Picture.q.record_time < end ]
    if filter is not None:
        q.append(filter)
    return Picture.select(AND(*q), orderBy=Picture.q.record_time)

def pics_grouped(interval, first=None, last=None, round=None):
    ''' return a list of (DateTime, count) tuples counting the number
    of images in a particular time interval'''

    debug = False

    if first is None:
        first = Picture.select(orderBy=Picture.q.record_time)[0].record_time
    if last is None:
        last = Picture.select(orderBy=Picture.q.record_time).reversed()[0].record_time

    if round is not None:
        first = first + round
        last = (last + interval - oneSecond) + round
        
    ret = []

    if debug:
        print 'first=%s last=%s interval=%s round=%s' % (first, last, interval, round)
    
    for t in yrange(first, last, interval):
        p = pics_in_range(t, delta=interval)
        if debug:
            print '  t=%s -> %d' % (t, p.count())
        if p.count() == 0:
            continue
        if round is not None:
            t += round
        ret.append((t, p.count()))

    return ret

class CalendarUI:
    _q_exports = [ 'year' ]
    
    intervals = { 'day':         RelativeDateTime(days=+1),
                  'week':        RelativeDateTime(weeks=+1),
                  'month':       RelativeDateTime(months=+1),
                  'year':        RelativeDateTime(years=+1),
                  }
    
    # Midnight on the Date
    zeroTime = RelativeDateTime(hour=0,minute=0,second=0)
    # A base for RelativeDateTime comparisons
    zeroDate = DateTime(0,1,1,0,0,0)

    # Just less than one day
    subDay = oneDay - oneSecond

    def __init__(self, collection, date=None, interval=None):
        self.collection = collection

        self.interval = interval
        self.date = date

        self.year = Year(self)
        
    # calendar will accept any combination of interval/date path
    # elements, though only the last of each is used
    def _q_lookup(self, request, component):
        #print 'Calendar: dealing with component: %s' % component
        
        if component in self.intervals.keys():
            self.interval = component
        else:
            try:
                self.date = strptime(component, '%Y-%m-%d')
            except DTError, x:
                raise TraversalError("Badly formatted date")

        return self

    _q_index = _q_index_ptl

    def menupane_extra(self):
        return ['Calendar',
                [('summary', self.calendar_url()),
                 'Recent...',
                 [('week', self.calendar_url('week')),
                  ('month', self.calendar_url('month')),
                  ('year', self.calendar_url('year'))]]]
    
    def calendar_url(self, interval=None, date=None):
        ret = '%s/%s/calendar/' % (prefix, self.collection.dbobj.name)
        if interval is not None:
            ret += interval + '/'
        if date is not None:
            ret += date.strftime('%Y-%m-%d') + '/'

        return htmltext(ret)
        
    def intervalList(self):
        i = self.intervals.items()
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
                raise QueryError('need date_end or date_inc')
            date_end = date_start+date_inc

        date_start += self.zeroTime     # round down to start of day
        date_end = (date_end + self.subDay) + self.zeroTime # round up to next day

        pics = pics_in_range(date_start, end=date_end, filter=filter)
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

    def yearview(self, year):
        """ Returns a list of months; each month is a list of weeks; each week is a list of days;
        each day is a tuple of (day, imagecount) """

        debug = False

        ret = []

        for m in range(1,12+1):
            days = monthrange(year, m)[1]
            start = DateTime(year, m, 1)
            end = start + RelativeDateTime(months=1)
            
            count = pics_in_range(start, delta=RelativeDateTime(months=1)).count()
            if debug:
                print '%d/%d count %d' % (year, m, count)
            
            if count == 0:
                if debug:
                    print "skipping %d/%d" % (year, m)
                continue

            month = Month(year, m)

            ret.append(month)

            for d in range(1, days+1):
                start = DateTime(year, m, d)
                end = start + oneDay

                count = pics_in_range(start, delta=oneDay).count()
                if count != 0:
                    month.markday(d, count)

        return ret
                                       
                
class Year:
    _q_exports = []

    import calendar_page
    formatyear = calendar_page.formatyear

    def __init__(self, cal):
        self.year = None
        self.calui = cal
        
    def _q_lookup(self, request, component):
        try:
            self.year = strptime(component, '%Y').year
        except DTError:
            try:
                self.year = strptime(component, '%Y-%m-%d').year
                request.redirect('../%d/' % self.year)
            except DTError:
                raise QueryError('Bad year format')
        return self

    def _q_index(self, request):
        if self.year is None:
            self.year = most_recent().record_time.year

        y = self.calui.yearview(self.year)

        return self.formatyear(request, y)
        
class Month:
    def __init__(self, year, month):
        self.year = year
        self.month = month
        self.days = monthrange(year, month)

        self.marked = {}

    def getname(self):
        return DateTime(self.year, self.month).strftime('%B')

    def markday(self, day, number):
        self.marked[day] = number

    def ismarked(self, day):
        return self.marked.get(day, 0)

    def getcalendar(self):
        return monthcalendar(self.year, self.month)
