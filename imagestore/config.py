# Imagestore application configuration

# These are the defaults; do not edit.  Put your changes in
# config_local.py

class server:
    path = '/imagestore'                # base pathname in server
    scgi_port = 4000                    # scgi port
    
class users:
    unpriv_newuser = True               # allow anyone to create accounts

    # Default permissions
    mayComment = True
    mayRate = False

class db:
    import os.path
    connection='sqlite:' + os.path.abspath('imagestore.db')

try:
    from config_local import *
except:
    pass
