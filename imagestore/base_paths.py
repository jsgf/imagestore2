# These are separated out from __init__.py to avoid recursuve imports

def base():
    return '/imagestore'

def path():
    return base() +'/'

def static_path():
    return path() + 'static/'
