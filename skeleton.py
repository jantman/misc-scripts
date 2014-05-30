#!/usr/bin/env python
"""
Generic python2/3 command line script skeleton.

Implements most of the common stuff I put in one-off scripts
to make them actually not-so-shitty.
"""

import sys
import optparse
import logging

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


def main(dry_run=False):
    """ do something """
    if dry_run:
        logger.info("would have done x()")
    else:
        logger.debug("calling x()")
        x()
    return True


def parse_args(argv):
    """ parse arguments/options """
    p = optparse.OptionParser()

    p.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                      help='dry-run - dont actually send metrics')

    p.add_option('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')

    options, args = p.parse_args(argv)

    return options


if __name__ == "__main__":
    opts = parse_args(sys.argv[1:])

    if opts.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif opts.verbose > 0:
        logger.setLevel(logging.INFO)

    if opts:
        main(dry_run=opts.dry_run)
