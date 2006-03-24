# These are separated out from __init__.py to avoid recursuve imports

def base():
    import imagestore.config as config
    return config.get('server', 'path')

def path():
    return base() +'/'

def static_path():
    return path() + 'static/'
