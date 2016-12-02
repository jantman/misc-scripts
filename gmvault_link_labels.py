#!/usr/bin/env python
"""
gmvault_link_labels.py
======================

Script to iterate over ALL messages in a `GMVault <http://gmvault.org/>`_
backup DB directory and symlink them into per-label per-thread directories.

Links are of the form:

    <DEST_DIR>/<LABEL>/<THREAD_ID>/<MESSAGE_ID>

Note that labels may be reformatted; see _format_label().

This script relies on the GMVault DB_DIR layout present as of 1.9.1:

    DB_DIR/db/YYYY-MM/<gm_id>.(eml|meta)

License
-------

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2016-12-01 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import os
import sys
import argparse
import logging
import re
from anyjson import deserialize
from collections import defaultdict

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class GMVaultLabelLinker(object):
    """Create per-label per-thread symlink dirs for GMVault backup"""

    monthdir_re = re.compile('^\d{4}-\d{2}$')

    def __init__(self, db_dir, out_dir):
        """ init method, run at class creation """
        self.db_dir = db_dir
        self.db_path = os.path.join(self.db_dir, 'db')
        self.out_dir = out_dir
        logger.info('Initialize; DB_DIR=%s out_dir=%s', db_dir, out_dir)

    def run(self):
        """do everything"""
        logger.debug('Starting run.')
        meta_files = self.get_meta_list()
        labelmap = self.make_label_map(meta_files)
        if not os.path.exists(self.out_dir):
            os.mkdir(self.out_dir)
        count = 0
        for label in sorted(labelmap.keys()):
            label_str = self._format_label(label)
            logger.info('Creating symlinks for label "%s" - %d messages',
                        label_str, len(labelmap[label]))
            count += self.make_label_symlinks(label_str, labelmap[label])
        logger.info('Done; ensured %d symlinks', count)

    def _format_label(self, label):
        """
        Update a label string to be safe/correct for the filesystem.

        :param label: the original GMail label
        :type label: str
        :returns: the filesystem-safe label
        :rtype: str
        """
        s = label.replace('\\', '_')
        if s != label:
            logger.warning('Label "%s" changed to "%s" for filesystem safety',
                           label, s)
        return s

    def make_label_symlinks(self, label, msg_tups):
        """
        For a given label and list of message tuples, create symlinks for the
        messages in the label directory.

        :param label: label name
        :type label: str
        :param msg_tups: list of per-message 3-tuples (monthdir, thr_id, gm_id)
        :type msg_tups: list
        :returns: number of symlinks for this label
        :rtype: int
        """
        lbldir = os.path.join(self.out_dir, label)
        if not os.path.exists(lbldir):
            logger.debug('Creating: %s', lbldir)
            os.mkdir(lbldir)
        c = 0
        for msg in msg_tups:
            monthdir, thr_id, gm_id = msg
            dpath = os.path.join(lbldir, monthdir, str(thr_id))
            if not os.path.exists(dpath):
                logger.debug('Creating: %s', dpath)
                os.makedirs(dpath)
            src = os.path.join(self.db_path, monthdir, '%s.eml' % gm_id)
            link_name = os.path.join(dpath, '%s.eml' % gm_id)
            if not os.path.exists(link_name):
                logger.debug('Symlinking %s to %s', src, link_name)
                os.symlink(src, link_name)
            c += 1
        logger.info('%d symlinks for label %s', c, label)
        return c

    def make_label_map(self, meta_files):
        """
        Given a dict of ``self.db_path`` month-directory names to lists of
        metadata file names in those directories, read in each file,
        deserialize the JSON, and get the list of labels. Return a dict of each
        label to a list of per-message 4-tuples (per-month directory, thread_id,
        gm_id). NOTE this assumes that filenames are ``gm_id.(eml|meta)``.

        :param meta_files: Metadata file absolute paths (return value of
          :py:meth:`~.get_meta_list`)
        :type meta_files: dict
        :return: Mapping of labels to per-message 3-tuples (per-month directory,
          thread_id, gm_id)
        :rtype: dict
        """
        labels = defaultdict(list)
        logger.info('Reading metadata files')
        mfcount = 0
        for monthdir in sorted(meta_files.keys()):
            dpath = os.path.join(self.db_path, monthdir)
            for fname in sorted(meta_files[monthdir]):
                lbls, thr_id, gm_id = self.read_metadata(
                    os.path.join(dpath, fname)
                )
                mfcount += 1
                for l in lbls:
                    labels[l].append((
                        monthdir,
                        thr_id,
                        gm_id
                    ))
        logger.info('Done reading %d metadata files; %d distinct labels',
                    mfcount, len(labels))
        return labels

    def read_metadata(self, fpath):
        """
        Given the absolute path to a metadata file, read and deserialize it,
        then return a 3-tuple of (labels list, thread_id, msg_id)
        :param fpath: absolute path to metadata file to read
        :type fpath: str
        :return: 3-tuple: (labels list, thread_id, msg_id)
        :rtype: tuple
        """
        logger.debug('Reading metadata: %s', fpath)
        with open(fpath, 'r') as fh:
            raw = fh.read()
        d = deserialize(raw)
        return (
            d.get('labels', []),
            d.get('thread_ids', 'unknown_thread'),
            d.get('gm_id', d.get('msg_id'))
        )

    def get_meta_list(self):
        """
        Find all metadata files. Return a dict of YYYY-MM to a list of meta
        filenames in ``DB_DIR/db/YYYY-MM``.

        :return: Dict of YYYY-MM directory to list of metadata files
        :rtype: dict
        """
        metafiles = {}
        fcount = 0
        logger.info('Finding metadata files in %s', self.db_path)
        for dirname in sorted(os.listdir(self.db_path)):
            if not self.monthdir_re.match(dirname):
                continue
            dirpath = os.path.join(self.db_path, dirname)
            if not os.path.isdir(dirpath):
                continue
            metafiles[dirname] = []
            logger.debug('Recursing into %s', dirpath)
            for fname in sorted(os.listdir(dirpath)):
                if not os.path.isfile(os.path.join(dirpath, fname)):
                    continue
                if not fname.endswith('.meta'):
                    continue
                metafiles[dirname].append(fname)
            logger.debug('Found %d meta files in %s directory',
                         len(metafiles[dirname]), dirname)
            fcount += len(metafiles[dirname])
        logger.info('Done; found %d .meta files from %d months',
                    fcount, len(metafiles))
        return metafiles


def parse_args(argv):
    """
    parse arguments/options
    """
    desc = 'Script to iterate over ALL messages in a GMVault ' \
           '<http://gmvault.org/> backup DB directory and symlink them into ' \
           'per-label per-thread directories.'
    p = argparse.ArgumentParser(description=desc)
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-o', '--out-dir', dest='outdir', action='store', type=str,
                   help='Output directory; default is DB_DIR/Labels',
                   default=None)
    p.add_argument('DB_DIR', action='store', type=str,
                   help='GMVault DB_DIR (-d / --db-dir)')
    args = p.parse_args(argv)
    args.DB_DIR = os.path.abspath(args.DB_DIR)
    if not os.path.isdir(args.DB_DIR):
        raise RuntimeError("%s does not exist or is not a "
                           "directory" % args.DB_DIR)
    if args.outdir is None:
        args.outdir = os.path.join(args.DB_DIR, 'Labels')
    else:
        args.outdir = os.path.abspath(args.outdir)
    return args

def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()

    script = GMVaultLabelLinker(args.DB_DIR, args.outdir)
    script.run()
