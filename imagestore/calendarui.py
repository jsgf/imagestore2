
from mx.DateTime import RelativeDateTime, DateTime, strptime, Error as DTError, oneDay, oneSecond, Monday
from quixote.errors import TraversalError, QueryError
from quixote.html import htmltext
from db import Picture
from sqlobject.sqlbuilder import AND, OR
from pages import pre, post, menupane, error, prefix
from calendar_page import _q_index_ptl, most_recent
from calendar import monthrange, monthcalendar

class Interval:
    def __init__(self, name, step, round):
        self.name = name
        intervals[name] = self
        
        self.step = step
        self.round = round

    def roundup(self, time):
        return time + self.step - oneSecond + self.round

    def rounddown(self, time):
        return time + self.round

    def __str__(self):
        return 'Interval(%s)' % self.name

intervals = {}

int_day  =Interval('day', RelativeDateTime(days=+1),
               RelativeDateTime(hour=0, minute=0, second=0))
int_week =Interval('week', RelativeDateTime(days=+7),
               RelativeDateTime(weekday=(Monday,0)))
int_month=Interval('month', RelativeDateTime(months=+1),
               RelativeDateTime(day=1, hour=0, minute=0, second=0))
int_year =Interval('year', RelativeDateTime(years=+1),
               RelativeDateTime(month=1, day=1, hour=0, minute=0, second=0))

# A base for RelativeDateTime comparisons
zeroDate = DateTime(0,1,1,0,0,0)

sorted_intervals = intervals.values()
sorted_intervals.sort(lambda a,b: cmp(zeroDate + a.step, zeroDate + b.step))

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

def pics_grouped(group, first=None, last=None, round=False, filter=None):
    ''' return a list of (DateTime, select-result) tuples counting the number
    of images in a particular time interval '''

    debug = False

    if first is None:
        first = Picture.select(orderBy=Picture.q.record_time)[0].record_time
    if last is None:
        last = Picture.select(orderBy=Picture.q.record_time).reversed()[0].record_time

    if round:
        first = group.rounddown(first)
        last = group.roundup(last)
        
    ret = []

    if debug:
        print 'first=%s last=%s group=%s round=%s' % (first, last, group, round)
    
    for t in yrange(first, last, group.step):
        p = pics_in_range(t, delta=group.step, filter=filter)
        if debug:
            print '  t=%s -> %d' % (t, p.count())
        if p.count() == 0:
            continue
        if round:
            t = group.rounddown(t)
        ret.append((t, p))

    return ret

class CalendarUI:
    _q_exports = [ 'year' ]
    
    def __init__(self, collection, date=None, interval=None):
        self.collection = collection

        self.interval = interval
        self.date = date

        self.year = Year(self)
        
    # calendar will accept any combination of interval/date path
    # elements, though only the last of each is used
    def _q_lookup(self, request, component):
        #print 'Calendar: dealing with component: %s' % component
        
        if component in intervals.keys():
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
        
    def build_calendar(self, date_start, interval, filter=None):
        """ Returns a list of lists of images within a certain date
        range.  The outer list is a list of tuples (date, piclist)
        tuples, where piclist is a list of Pictures in record_time
        order.
        """

        date_end = interval.roundup(date_start+interval.step)
        date_start = interval.rounddown(date_start)

        pics = pics_grouped(int_day, date_start, date_end, round=True, filter=filter)

        days = [ (date, list(sel)) for date,sel in pics if sel.count() != 0 ]

        #print 'bulld_calendar(%s - %s) -> %s' % (date_start, date_end, days)

        return days

    def yearview(self, year):
        """ Returns a list of Months in a year, populated with info
        about pics in that month (only months with any pics are added
        to the list). """

        # Get pics grouped into months
        months = [ (Month(year, m.month), res) for (m, res) in pics_grouped(int_month,
                                                                            DateTime(year  ,1,1),
                                                                            DateTime(year+1,1,1),
                                                                            round=True)
                   if res.count() > 0 ]

        # Mark each day in the month
        for (m, sel) in months:
            for p in sel:
                m.markday(p.record_time.day, 1)

        # Just return a list of Months
        return [ m for (m,s) in months ]
                                       
                
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
        self.marked[day] = self.marked.get(day, 0) + number

    def ismarked(self, day):
        return self.marked.get(day, 0)

    def getcalendar(self):
        return monthcalendar(self.year, self.month)
