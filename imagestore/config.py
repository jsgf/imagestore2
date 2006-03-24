# Imagestore application configuration

# These are the defaults; do not edit.  Put your changes in
# imagestore.conf

import ConfigParser
import os.path

_defaults = {
    'server': {
        'path': '/imagestore',          # base pathname in server
        'scgi_port': 4000               # scgi port
    },
    'db': {
    'connection': os.path.abspath('imagestore.db')
    },
    'auth': {
    'schemes': 'digest',                # allowable schemes (digest, basic)
    'realm': 'Imagestore',
    'cookie_life': 'unlimited',          # ( 'unlimited' | 'session' | <seconds> )
    'nonce_life': 'unlimited',           # ( 'unlimited' | <seconds> )
    },
    'users': {
    'unpriv_newuser': 'True',            # allow anyone to create accounts
    'mayComment': 'True',
    'mayRate': 'True',
    }
}
    
_config = ConfigParser.SafeConfigParser()

_config.read('imagestore.conf')

def get(section, name):
    try:
        return _config.get(section, name)
    except ConfigParser.Error:
        return _defaults[section][name]
