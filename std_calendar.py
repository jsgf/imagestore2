# Hack to resolve the namespace conflict between imagestore.calendar
# and calendar, and the fact that there doesn't seem to be a way to to
# absolute package imports.

from calendar import *
