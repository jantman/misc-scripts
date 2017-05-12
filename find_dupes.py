#!/usr/bin/env python
"""
CHANGELOG
---------

2017-05-12 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
from collections import defaultdict

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class DupeFinder(object):
    """ might as well use a class. It'll make things easier later. """

    def __init__(self, sums_file):
        """ init method, run at class creation """
        self.sums_file = sums_file

    def run(self):
        """ do stuff here """
        sums = self._read_sums()
        count = 0
        for md5sum, paths in sums.items():
            if len(paths) < 2:
                continue
            count += 1
            print('# %s' % md5sum)
            for p in paths:
                print(p)
            pass
        logger.info('Found %d duplicate files', count)

    def _read_sums(self):
        sums = defaultdict(list)
        count = 0
        logger.debug('Reading SUMS_FILE: %s', self.sums_file)
        with open(self.sums_file, 'r') as fh:
            for line in fh.readlines():
                line = line.strip()
                if line == '':
                    continue
                count += 1
                parts = line.split()
                sums[parts[0]].append(parts[1])
        logger.debug('Read %d file sums', count)
        return sums

def parse_args(argv):
    epil = "Generate SUMS_FILE using a command like 'md5sum /foo/* > sums' " \
           "or: '" \
           "find $(pwd) -type f | while read -r fname; do md5sum \"$fname\" " \
           ">> sums; done'"
    p = argparse.ArgumentParser(description='Find dupe files based on md5sum',
                                epilog=epil)
    p.add_argument('SUMS_FILE', action='store', type=str,
                   help="ms5sum output file - must be manually generated using"
                   " the 'md5sum' command")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    args = p.parse_args(argv)
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
    elif args.verbose == 1:
        set_log_info()

    script = DupeFinder(args.SUMS_FILE)
    script.run()
