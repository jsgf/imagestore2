#!/usr/bin/python

from scgi.quixote_handler import QuixoteHandler, main
from quixote.publish import SessionPublisher

class ImagestorePublisher(SessionPublisher):
    def __init__(self, *args, **kwargs):
        SessionPublisher.__init__(self, *args, **kwargs)

        # (Optional step) Read a configuration file
        self.read_config("imagestore/config.conf")

        # Open the configured log files
        self.setup_logs()

class ImagestoreHandler(QuixoteHandler):
    publisher_class = ImagestorePublisher
    root_namespace = "imagestore"
    prefix = "/imagestore"

if __name__ == '__main__':
    main(ImagestoreHandler)
