#!/usr/bin/env python
"""
Script using boto and inotify to continually sync a directory to S3, and
generate an index.html for it.

##### This file is managed by privatepuppet::motion ######
"""

import os
import sys
import argparse
import logging
import datetime
from boto.s3.connection import S3Connection
from boto.s3.key import Key
import pyinotify
from filechunkio import FileChunkIO
import math

FORMAT = "[%(asctime)s][%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)

WATCH_MASK = pyinotify.IN_CLOSE_WRITE
WATCH_TIMEOUT = 1000 # milliseconds

class S3IndexSync:
    """Sync a directory to S3, generating index.html for it"""

    def run(self, bucket_name, path, prefix=''):
        """run the sync"""
        self.prefix = prefix
        logger.debug("connecting to S3")
        self.conn = S3Connection()
        logger.info("Connected to S3")
        logger.debug("Getting S3 bucket %s", bucket_name)
        self.bucket = self.conn.get_bucket(bucket_name)
        logger.debug("Got bucket")
        self.bucket_endpoint = self.bucket.get_website_endpoint()
        logger.debug("Bucket endpoint: %s", self.bucket_endpoint)
        self.uploaded = self.get_current_keys()
        logger.debug("Found %s uploaded files", len(self.uploaded))
        self.initial_sync(path)
        self.sync_loop(path)

    def initial_sync(self, path):
        """synchronize all existing files"""
        sync_files = []
        logger.info("Beginning initial file sync")
        for fname in os.listdir(path):
            k = os.path.join(self.prefix, fname)
            if k in self.uploaded:
                continue
            fpath = os.path.join(path, fname)
            if not os.path.isfile(fpath):
                continue
            self.upload_file(fpath, k, make_index=False)
        self.make_index_html()

    def sync_loop(self, path):
        """inotify-based file watcher"""
        logger.info("Setting up inotify with watch on %s (timeout %s)", path,
                    WATCH_TIMEOUT)
        self.wm = pyinotify.WatchManager()
        self.wm.add_watch(path, WATCH_MASK, rec=True)
        self.notifier = pyinotify.Notifier(self.wm, self.handle_inotify,
                                           timeout=WATCH_TIMEOUT)
        logger.info("Processing events")
        self.notifier.process_events()
        logger.info("Starting inotify loop")
        while True:
            try:
                if self.notifier.check_events():
                    self.notifier.read_events()
                    self.notifier.process_events()
            except KeyboardInterrupt as ex:
                raise ex
            except:
                logger.exception("exception encountered while polling inotify")

    def handle_inotify(self, event):
        """handle the inotify event"""
        if event.dir:
            logger.debug("Skipping directory event")
        logger.info("Got event for %s", event.pathname)
        k = os.path.join(self.prefix, os.path.basename(event.pathname))
        self.upload_file(event.pathname, k)

    def upload_file(self, fpath, key_path, make_index=True):
        """upload file at fpath to bucket at key_path"""
        fsize = os.stat(fpath).st_size
        if fsize >= 15728640:  # 15 MB
            self.upload_large_file(fpath, key_path, fsize)
            return
        start = datetime.datetime.now()
        logger.info("Uploading %s to %s", fpath, key_path)
        k = Key(self.bucket)
        k.key = key_path
        k.set_contents_from_filename(fpath)
        logger.info("Upload complete in %s", (datetime.datetime.now() - start))
        if key_path not in self.uploaded and make_index is True:
            self.make_index_html()
        self.uploaded.add(key_path)

    def upload_large_file(self, fpath, key_path, fsize):
        """
        upload a large file in multiple parts
        from: <http://boto.readthedocs.org/en/latest/s3_tut.html#storing-data>
        """
        logger.info("Doing multipart upload of %s to %s", fpath, key_path)
        start = datetime.datetime.now()
        mp = self.bucket.initiate_multipart_upload(key_path)
        chunk_size = 15728640
        chunk_count = int(math.ceil(fsize / float(chunk_size)))
        logger.debug("Will upload %sb file as %s chunks, %sb each",
                     fsize, chunk_count, chunk_size)

        # Send the file parts, using FileChunkIO to create a file-like object
        # that points to a certain byte range within the original file. We
        # set bytes to never exceed the original file size.
        for i in range(chunk_count):
            logger.debug("Uploading chunk %s", i)
            offset = chunk_size * i
            f_bytes = min(chunk_size, fsize - offset)
            with FileChunkIO(fpath, 'r', offset=offset, bytes=f_bytes) as fp:
                mp.upload_part_from_file(fp, part_num=i + 1)
            logger.debug("Uploaded %s bytes", offset)
        # Finish the upload
        logger.debug("Done uploading chunks")
        mp.complete_upload()
        logger.info("Upload complete in %s", (datetime.datetime.now() - start))
        self.uploaded.add(key_path)

    def upload_index(self, content):
        """upload the index.html"""
        key_path = os.path.join(self.prefix, 'index.html')
        start = datetime.datetime.now()
        logger.info("Uploading index.html")
        k = Key(self.bucket)
        k.key = key_path
        k.content_type = 'text/html'
        k.set_contents_from_string(content)
        logger.info("Upload complete in %s", (datetime.datetime.now() - start))

    def make_index_html(self):
        """generate and upload a new index.html"""
        url = 'http://%s/%s' % (self.bucket_endpoint, self.prefix)
        html = "<html><head><title>%s</title></head>\n" % url
        html += "<body><h2>%s</h2><ul>\n" % url
        for fpath in sorted(self.uploaded):
            furl = 'http://%s/%s' % (self.bucket_endpoint, fpath)
            html += "<li><a href=\"%s\">%s</a></li>\n" % (furl, fpath)
        html += "</ul></body></html>\n"
        self.upload_index(html)

    def get_current_keys(self):
        """return a list of the current keys (strings) in the bucket"""
        keys = set()
        if self.prefix != '':
            l = self.bucket.list(prefix=self.prefix)
        else:
            l = self.bucket.list()
        for k in l:
            keys.add(k.name)
        return keys


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='motion capture handler')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-p', '--prefix', dest='prefix', action='store',
                   type=str, help='prefix to prepend to files in S3',
                   default='')
    p.add_argument('-R', '--recursive', dest='recursive', action='store_true',
                   help='recursively check files; otherwise, just upload files'
                   ' directly in the specified path', default=False)
    p.add_argument('BUCKET_NAME', action='store', type=str,
                   help='s3 bucket name')
    p.add_argument('PATH', action='store', type=str, help='path to sync')
    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    if args.recursive:
        raise NotImplementedError("recursive upload not implemented")
    cls = S3IndexSync()
    cls.run(args.BUCKET_NAME, args.PATH, prefix=args.prefix)
