#!/usr/bin/env python3
#
# screen history saving script - saves your current windows and their titles,
# then appends this to ~/.screenrc and writes the result to ~/.screenrc.save
#
# This is intended to be run on a regular basis; I cron it every minute.
#
# WARNING - this expects only one screen session to be running as your user.
#
# Copyright 2014-2024 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Use this however you want; send changes back to me please.
#
# The canonical version of this script is available at:
#  <https://github.com/jantman/misc-scripts/blob/master/savescreen.py>
#
# CHANGELOG:
# 2014-07-24 Jason Antman <jason@jasonantman.com>
#   * first public version
#
# 2014-07-25 Jason Antman <jason@jasonantman.com>
#   * restored windows should go to their last PWD, set in ~/.bashrc
#     (see <http://blog.jasonantman.com/2014/07/session-save-and-restore-with-bash-and-gnu-screen/>)
#
# 2015-03-26 Jason Antman <jason@jasonantman.com>
#   * add lockfile to prevent runaway cron processes
#
# 2024-01-23 Jason Antman <jason@jasonantman.com>
#   * completely rewrite for modern Python (>= 3.9)
#   * remove ugly lockfile hackery
#   * set 30-second hard timeout
####################################################

import subprocess
import re
import os
from platform import node
from datetime import datetime
import sys
import logging
import argparse
import signal
import fcntl
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s %(levelname)s] %(message)s"
)
logger: logging.Logger = logging.getLogger()


class ScreenSaver:

    LOCKFILE_PATH: str = os.path.abspath(os.path.expanduser('~/.savescreen.lock'))

    def run(self, timeout: int = 30):
        if not os.path.exists(self.LOCKFILE_PATH):
            logger.info('Creating file: %s', self.LOCKFILE_PATH)
            Path(self.LOCKFILE_PATH).touch()
        def handler(*_):
            raise TimeoutError()
        # set the timeout handler
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout)
        try:
            ptr = os.open(self.LOCKFILE_PATH, os.O_WRONLY)
            try:
                fcntl.lockf(ptr, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._do_it()
                try:
                    os.close(ptr)
                except Exception:
                    pass
            except IOError:
                logger.error(
                    'Unable to acquire lock on %s; already running?',
                    self.LOCKFILE_PATH, exc_info=True
                )
        except TimeoutError:
            logger.error('Timeout at %d seconds', timeout)
        finally:
            signal.alarm(0)

    def _get_windows(self, timeout: int = 25) -> str:
        cmd = ['screen', '-Q', 'windows']
        logger.debug('Running: %s', ' '.join(cmd))
        p = subprocess.run(
            cmd,
            check=True, stdout=subprocess.PIPE, timeout=timeout, text=True
        )
        logger.debug(
            'Command exited %d with STDOUT: %s', p.returncode, p.stdout
        )
        return p.stdout

    def _windowstr_to_dict(self, windowstr: str) -> dict:
        """This is really crap code, but it's been working for a decade..."""
        windows = {}
        m = True
        windowre = re.compile(r'(\s?(\d+)[-\*]?\$\s+(\S+)\s*)')
        # loop over the window list, extract substrings matching a window specifier
        while m is not None:
            logger.debug("LOOP windowstr={w}=".format(w=windowstr))
            m = windowre.match(windowstr)
            if m is None:
                if len(windows) == 0:
                    logger.debug(
                        "no match and no windows yet; trimming windowstr and continuing")
                    windowstr = windowstr[1:]
                    m = True
                    continue
                else:
                    logger.debug(
                        "no match, breaking out of loop - windowstr: {w}".format(
                            w=windowstr))
                    break
            g = m.groups()
            windowstr = windowstr[len(g[0]):]
            logger.debug("found match: {a} = {b}".format(a=g[1], b=g[2]))
            windows[int(g[1])] = g[2]
        return windows

    def _do_it(self):
        windowstr: str = self._get_windows()
        windows: dict = self._windowstr_to_dict(windowstr)
        logger.debug('Windows: %s', windows)

        # read in screenrc
        logger.debug("Reading .screenrc")
        with open(os.path.expanduser('~/.screenrc'), 'r') as fh:
            screenrc = fh.read()

        # get rid of the first "local 0" line if it's there
        screenrc = screenrc.replace("screen -t local 0\n", "")

        logger.debug("Writing .screenrc.save")
        # write it out to the save location, with the windows added
        dirpath = os.path.expanduser('~/.screendirs')
        with open(os.path.expanduser('~/.screenrc.save'), 'w') as fh:
            fh.write(screenrc)
            fh.write("\n\n")
            dstr: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f"# .screenrc.save generated on {node()} at {dstr}\n")
            for n in range(0, max(windows.keys()) + 1):
                fh.write(
                    f'screen -t "{windows.get(n, "bash")}" {n} sh -c "cd $(readlink -fn {dirpath}/{n}); bash"\n'
                )
            fh.write("\n")


def parse_args(argv):
    p = argparse.ArgumentParser(description='Save screen session state to disk')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose output')
    p.add_argument('-t', '--timeout', dest='maxtime', action='store',
                   default=30, help='Maximum runtime seconds (default: 30)')
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


def set_log_level_format(lgr: logging.Logger, level: int, fmt: str):
    """Set logger level and format."""
    formatter = logging.Formatter(fmt=fmt)
    lgr.handlers[0].setFormatter(formatter)
    lgr.setLevel(level)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    # set logging level
    if args.verbose:
        set_log_debug(logger)
    else:
        set_log_info(logger)
    ScreenSaver().run(timeout=args.maxtime)
