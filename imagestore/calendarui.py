
from mx.DateTime import RelativeDateTime, DateTime, strptime, Error as DTError, oneDay, oneSecond, Monday
from quixote.errors import TraversalError, QueryError
from quixote.html import htmltext
from sqlobject.sqlbuilder import AND, OR

from db import Picture
from dbfilters import mayViewFilter
from pages import pre, post, menupane, error, prefix
from calendar_page import _q_index_ptl, most_recent
from calendar import monthrange, monthcalendar
from menu import SubMenu, Heading, Link

def kw_summary(pics):
    count = {}
    for p in pics:
        for k in p.keywords:
            count[k.word] = count.get(k.word, 0) + 1
    tot = count.items()
    tot.sort(lambda a,b: cmp(b[1],a[1]))
    return [ t[0] for t in tot ]

def ordinal(n):
    o='th'
    if n == 1:
        o = 'st'
    elif n == 2:
        o = 'nd'
    elif n == 3:
        o = 'rd'

    return '%d%s' % (n,o)

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

    def num_fmt(self, time):
        return time.strftime('%F')

class DayInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'day', RelativeDateTime(days=+1),
                          RelativeDateTime(hour=0, minute=0, second=0))

    def long_fmt(self, time):
        return time.strftime('%%A, %%B %s, %%Y' % ordinal(time.day))


class WeekInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'week', RelativeDateTime(days=+7),
                          RelativeDateTime(weekday=(Monday,0)))

    def long_fmt(self, time):
        return time.strftime('Week of %%B %s, %%Y' % ordinal(time.day))

class MonthInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'month', RelativeDateTime(months=+1),
                          RelativeDateTime(day=1, hour=0, minute=0, second=0))

    def num_fmt(self, time):
        return time.strftime('%Y-%m')

    def long_fmt(self, time):
        return time.strftime('%B, %Y')

class YearInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'year', RelativeDateTime(years=+1),
                          RelativeDateTime(month=1, day=1, hour=0, minute=0, second=0))

    def num_fmt(self, time):
        return time.strftime('%Y')

    def long_fmt(self, time):
        return time.strftime('%Y')

intervals = {}

int_day  =DayInterval()
int_week =WeekInterval()
int_month=MonthInterval()
int_year =YearInterval()

# A base for RelativeDateTime comparisons
zeroDate = DateTime(0,1,1,0,0,0)

sorted_intervals = intervals.values()
sorted_intervals.sort(lambda a,b: cmp(zeroDate + a.step, zeroDate + b.step))

def parse(s):
    " Try parsing several different forms of date "
    try:
        return strptime(s, '%Y-%m-%d')
    except DTError, x:
        pass
    try:
        return strptime(s, '%Y-%m')
    except DTError, x:
        pass
    return strptime(s, '%Y')


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
    return Picture.select(AND(*q), orderBy=Picture.q.record_time).distinct()

def pics_grouped(group, first=None, last=None, round=False, filter=None):
    ''' return a list of (DateTime, select-result) tuples counting the number
    of images in a particular time interval '''

    debug = False

    try:
        if first is None:
            first = Picture.select(filter, orderBy=Picture.q.record_time)[0].record_time
        if last is None:
            last = Picture.select(filter, orderBy=Picture.q.record_time).reversed()[0].record_time
    except IndexError:
        # If there are no pictures, then return an empty list
        return []
    
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
    
    def __init__(self, collection, date=None, interval=int_week):
        self.collection = collection

        self.interval = interval
        self.date = date

        self.year = Year(self)
        
    # calendar will accept any combination of interval/date path
    # elements, though only the last of each is used
    def _q_lookup(self, request, component):
        #print 'Calendar: dealing with component: %s' % component

        if component in intervals.keys():
            self.interval = intervals[component]
        else:
            try:
                self.date = parse(component)
            except DTError, x:
                raise TraversalError("Badly formatted date")

        return self

    _q_index = _q_index_ptl

    def menupane_extra(self):
        return SubMenu(heading='Calendar',
                       items=[ Link(link='summary', url=self.calendar_url()),
                               SubMenu(heading='Recent...',
                                       items=[Link('week', self.calendar_url(int_week)),
                                              Link('month', self.calendar_url(int_month)),
                                              Link('year', self.calendar_url(int_year))])])
    
    def calendar_url(self, interval=None, date=None):
        ret = '%s/%s/calendar/' % (prefix, self.collection.dbobj.name)
        if interval is not None:
            if isinstance(interval, str):
                interval = intervals[interval]
            ret += interval.name + '/'
        if date is not None:
            if interval is not None:
                ret += interval.num_fmt(date)
            else:
                ret += date.strftime('%Y-%m-%d')
            ret += '/'

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

        days = [ (date, sel) for date,sel in pics if sel.count() != 0 ]

        #print 'bulld_calendar(%s - %s) -> %s' % (date_start, date_end, days)

        return days

    def yearview(self, request, year):
        """ Returns a list of Months in a year, populated with info
        about pics in that month (only months with any pics are added
        to the list). """

        # Get pics grouped into months
        filter = mayViewFilter(self.collection.dbobj, request.session.getuser())
        months = [ (Month(year, m.month), res) for (m, res) in pics_grouped(int_month,
                                                                            DateTime(year  ,1,1),
                                                                            DateTime(year+1,1,1),
                                                                            round=True,
                                                                            filter=filter)
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
            self.year = parse(component).year
        except DTError:
            raise QueryError('Bad year format')
        return self

    def _q_index(self, request):
        if self.year is None:
            self.year = most_recent().year

        y = self.calui.yearview(request, self.year)

        return self.formatyear(request, y)
        
class Month:
    def __init__(self, year, month):
        self.year = year
        self.month = month
        self.days = monthrange(year, month)

        self.marked = {}
        self.total = 0

    def getname(self):
        return DateTime(self.year, self.month).strftime('%B')

    def markday(self, day, number):
        self.total += number
        self.marked[day] = self.marked.get(day, 0) + number

    def ismarked(self, day):
        return self.marked.get(day, 0)

    def getcalendar(self):
        return monthcalendar(self.year, self.month)
