
from mx.DateTime import RelativeDateTime, DateTime, strptime, Error as DTError
from quixote.errors import TraversalError, QueryError
from quixote.html import htmltext
from db import Picture
from pages import pre, post, menupane, error, prefix
from calendar_page import _q_index_ptl

    
class CalendarUI:
    _q_exports = []
    
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
    subDay = RelativeDateTime(hours=+23, minutes=+59, seconds=+59)

    def __init__(self, collection, date=None, interval=None):
        self.collection = collection

        self.interval = interval
        self.date = date
        
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
                 'last...',
                 [('Week', self.calendar_url('week')),
                  ('Month', self.calendar_url('month')),
                  ('Year', self.calendar_url('year'))]]]
    
        return [('Calendar summary', self.calendar_url()),
                'Recent photos',
                [('Week', self.calendar_url('week')),
                 ('Month', self.calendar_url('month')),
                 ('Year', self.calendar_url('year'))]]
    
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
