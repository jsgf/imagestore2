#!/usr/bin/python

from quixote.server.scgi_server import run
from quixote.publish1 import Publisher
from quixote.config import Config
from quixote.session import SessionManager
import imagestore
from imagestore.session import ImagestoreSession, ImagestoreSessionMapping

import imagestore.db as db

config = Config()
config.read_file('imagestore/config.conf')

def create_my_publisher():
    db.db_connect()
    p = Publisher(imagestore,
                  config=config)
    session_manager=SessionManager(session_class=ImagestoreSession,
                                   session_mapping=ImagestoreSessionMapping())
    p.set_session_manager(session_manager)
    return p

if __name__ == '__main__':
    run(create_my_publisher, port=4000, script_name=imagestore.path())
