#!/usr/bin/python

import quixote.config
import quixote.session

from quixote.server.scgi_server import run
from quixote.publish1 import Publisher

import imagestore.session
import imagestore.config

config = quixote.config.Config()
config.read_file('imagestore/config.conf')

def create_my_publisher():
    imagestore.db.db_connect()
    p = Publisher(imagestore, config=config)
    session_manager=quixote.session.SessionManager(session_class=imagestore.session.ImagestoreSession,
                                                   session_mapping=imagestore.session.ImagestoreSessionMapping())
    p.set_session_manager(session_manager)
    return p

if __name__ == '__main__':
    run(create_my_publisher,
        port=imagestore.config.get('server', 'scgi_port'),
        script_name=imagestore.config.get('server', 'path'))
