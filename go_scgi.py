#!/usr/bin/python

from scgi.quixote_handler import QuixoteHandler, main
from imagestore import publisher

class ImagestoreHandler(QuixoteHandler):
    publisher_class = publisher.ImagestorePublisher
    root_namespace = "imagestore"
    prefix = "/imagestore"

if __name__ == '__main__':
    main(ImagestoreHandler)
