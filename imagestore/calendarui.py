
import calendar

import mx.DateTime as mxdt

from quixote.errors import TraversalError, QueryError
from quixote.html import htmltext

from sqlobject.sqlbuilder import AND

import imagestore
import imagestore.db as db
import imagestore.calendar_page as calendar_page
import imagestore.dbfilters as dbfilter
import imagestore.menu as menu

def to_mxDateTime(dt):
    if type(dt) == mxdt.DateTime:
        return dt
    return mxdt.DateTime(dt.year, dt.month, dt.day,
                         dt.hour, dt.minute, dt.second)

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

def most_recent(filter):
    " Return DateTime of most recent picture, or today "
    try:
        return db.Picture.select(filter,
                                 orderBy=db.Picture.q.record_time).reversed()[0].record_time
    except IndexError:
        return mxdt.gmt()


class Interval:
    def __init__(self, name, step, round):
        self.name = name
        intervals[name] = self
        
        self.step = step
        self.round = round

    def roundup(self, time):
        time = to_mxDateTime(time)
        return time + self.step - mxdt.oneSecond + self.round

    def rounddown(self, time):
        time = to_mxDateTime(time)
        return time + self.round

    def __str__(self):
        return 'Interval(%s)' % self.name

    def num_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('%F')

class DayInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'day', mxdt.RelativeDateTime(days=+1),
                          mxdt.RelativeDateTime(hour=0, minute=0, second=0))

    def long_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('%%A, %%B %s, %%Y' % ordinal(time.day))


class WeekInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'week', mxdt.RelativeDateTime(days=+7),
                          mxdt.RelativeDateTime(weekday=(mxdt.Monday,0)))

    def long_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('Week of %%B %s, %%Y' % ordinal(time.day))

class MonthInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'month', mxdt.RelativeDateTime(months=+1),
                          mxdt.RelativeDateTime(day=1, hour=0, minute=0, second=0))

    def num_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('%Y-%m')

    def long_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('%B, %Y')

class YearInterval(Interval):
    def __init__(self):
        Interval.__init__(self, 'year', mxdt.RelativeDateTime(years=+1),
                          mxdt.RelativeDateTime(month=1, day=1, hour=0, minute=0, second=0))

    def num_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('%Y')

    def long_fmt(self, time):
        time = to_mxDateTime(time)
        return time.strftime('%Y')

intervals = {}

int_day  =DayInterval()
int_week =WeekInterval()
int_month=MonthInterval()
int_year =YearInterval()

# A base for RelativeDateTime comparisons
zeroDate = mxdt.DateTime(0,1,1,0,0,0)

sorted_intervals = intervals.values()
sorted_intervals.sort(lambda a,b: cmp(zeroDate + a.step, zeroDate + b.step))

def parse(s):
    " Try parsing several different forms of date "
    try:
        return mxdt.strptime(s, '%Y-%m-%d')
    except mxdt.Error, x:
        pass
    try:
        return mxdt.strptime(s, '%Y-%m')
    except mxdt.Error, x:
        pass
    return mxdt.strptime(s, '%Y')


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
        
    q = [ db.Picture.q.record_time >= start, db.Picture.q.record_time < end ]
    if filter is not None:
        q.append(filter)
    return db.Picture.select(AND(*q), orderBy=db.Picture.q.record_time).distinct()

def pics_grouped(group, first=None, last=None, filter=None):
    ''' return a list of (DateTime, select-result) tuples counting the number
    of images in a particular time interval '''

    debug = False

    try:
        if first is None:
            first = db.Picture.select(filter, orderBy=db.Picture.q.record_time)[0].record_time
        if last is None:
            last = db.Picture.select(filter, orderBy=db.Picture.q.record_time).reversed()[0].record_time
    except IndexError:
        # If there are no pictures, then return an empty list
        return []

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
            except mxdt.Error, x:
                raise TraversalError("Badly formatted date")

        return self

    _q_index = calendar_page._q_index_ptl

    def menupane_extra(self):
        return menu.SubMenu(heading='Calendar',
                            items=[ menu.Link(link='summary', url=self.path()),
                                    menu.SubMenu(heading='Recent...',
                                                 items=[menu.Link('week', self.path(int_week)),
                                                        menu.Link('month', self.path(int_month)),
                                                        menu.Link('year', self.path(int_year))])])
    
    def path(self, interval=None, date=None):
        ret = self.collection.path() + 'calendar/'
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

        pics = pics_grouped(int_day, date_start, date_end, filter=filter)

        days = [ (date, sel) for date,sel in pics if sel.count() != 0 ]

        #print 'bulld_calendar(%s - %s) -> %s' % (date_start, date_end, days)

        return days

    def yearview(self, request, year):
        """ Returns a list of Months in a year, populated with info
        about pics in that month (only months with any pics are added
        to the list). """

        # Get pics grouped into months
        filter = dbfilter.mayViewFilter(self.collection.dbobj, request.session.getuser())
        months = [ (Month(year, m.month), res) for (m, res) in pics_grouped(int_month,
                                                                            mxdt.DateTime(year  ,1,1),
                                                                            mxdt.DateTime(year+1,1,1),
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
        except mxdt.Error:
            raise QueryError('Bad year format')
        return self

    def _q_index(self, request):
        if self.year is None:
            filter = dbfilter.mayViewFilter(self.calui.collection.dbobj,
                                            request.session.getuser())
            self.year = most_recent(filter).year

        y = self.calui.yearview(request, self.year)

        return self.formatyear(request, y)
        
class Month:
    def __init__(self, year, month):
        self.year = year
        self.month = month
        self.days = calendar.monthrange(year, month)

        self.marked = {}
        self.total = 0

    def getname(self):
        return mxdt.DateTime(self.year, self.month).strftime('%B')

    def markday(self, day, number):
        self.total += number
        self.marked[day] = self.marked.get(day, 0) + number

    def ismarked(self, day):
        return self.marked.get(day, 0)

    def getcalendar(self):
        return calendar.monthcalendar(self.year, self.month)
