# These are separated out from __init__.py to avoid recursuve imports

import imagestore.config

def base():
    return imagestore.config.server.path

def path():
    return base() +'/'

def static_path():
    return path() + 'static/'
