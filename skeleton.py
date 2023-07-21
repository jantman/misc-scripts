#!/usr/bin/env python
"""
Skeleton of a simple Python CLI script

Source
------

https://github.com/jantman/misc-scripts/blob/master/skeleton.py

Dependencies
------------

Python 3+

"""

import sys
import argparse
import logging

FORMAT: str = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger: logging.Logger = logging.getLogger()


class SimpleScript:

    def __init__(self):
        pass

    def run(self):
        print("run.")


def parse_args(argv):
    p = argparse.ArgumentParser(description='Python script skeleton')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose output')
    args = p.parse_args(argv)
    return args


def set_log_info(l: logging.Logger):
    """set logger level to INFO"""
    set_log_level_format(
        l,
        logging.INFO,
        '%(asctime)s %(levelname)s:%(name)s:%(message)s'
    )


def set_log_debug(l: logging.Logger):
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        l,
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(lgr: logging.Logger, level: int, format: str):
    """Set logger level and format."""
    formatter = logging.Formatter(fmt=format)
    lgr.handlers[0].setFormatter(formatter)
    lgr.setLevel(level)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose:
        set_log_debug(logger)
    else:
        set_log_info(logger)

    SimpleScript().run()
