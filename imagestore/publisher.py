from quixote.publish import SessionPublisher
from quixote.session import SessionManager
from session import ImagestoreSession, ImagestoreSessionMapping

from db import db_connect

class ImagestorePublisher(SessionPublisher):
    def __init__(self, *args, **kwargs):
        print 'starting up publisher'
        db_connect()
        
        sessionmap = ImagestoreSessionMapping()
        
        session = SessionManager(session_class=ImagestoreSession,
                                 session_mapping=sessionmap)
        
        SessionPublisher.__init__(self, session_mgr=session, *args, **kwargs)

        # (Optional step) Read a configuration file
        self.read_config("imagestore/config.conf")

        # Open the configured log files
        self.setup_logs()

