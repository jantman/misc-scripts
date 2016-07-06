#!/usr/bin/env python
"""
toxit.py - script to parse a tox.ini file in cwd and run the test commands
for a specified environment against the already-existing virtualenv (i.e. just
re-run only the test commands).

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/toxit.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2016-07-05 Jason Antman <jason@jasonantman.com>:
  - gut the whole script and use tox's own parseconfig()
2016-07-05 Jason Antman <jason@jasonantman.com>:
  - bug fixes
2016-07-03 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import argparse
import logging
import subprocess
try:
    from tox.config import parseconfig
except ImportError:
    sys.stderr.write("ERROR: Could not import tox - is it installed?\n")
    raise SystemExit(1)

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)


class ToxIt(object):
    """re-run tox commands against an existing environment"""

    ignore_commands = [
        ['python', '--version'],
        ['virtualenv', '--version'],
        ['pip', '--version'],
        ['pip', 'freeze']
    ]

    def __init__(self):
        self.commands_per_env = self.parse_toxini()

    def parse_toxini(self):
        """parse the tox ini, return dict of environments to list of commands"""
        logger.debug('Calling tox.config.parseconfig()')
        config = parseconfig(args=[])
        logger.debug('Config parsed; envlist: %s', config.envlist)
        env_cmds = {}
        for envname in config.envlist:
            bindir = os.path.join(
                config.envconfigs[envname].envdir.strpath,
                'bin'
            )
            env_cmds[envname] = []
            for cmd in config.envconfigs[envname].commands:
                if cmd in self.ignore_commands:
                    logger.debug('%s - skipping ignored command: %s',
                                 envname, cmd)
                    continue
                cmd[0] = os.path.join(bindir, cmd[0])
                env_cmds[envname].append(cmd)
            logger.debug('env %s: %s', envname, env_cmds[envname])
        return env_cmds


    def run_env(self, envname, cmd_list):
        """run a single env; return True (success) or False (failure)"""
        for cmd in cmd_list:
            logger.info('Running command: %s', cmd)
            rcode = subprocess.call(cmd)
            logger.info('Command exited %s', rcode)
            if rcode != 0:
                return False
        return True


    def run(self, envlist):
        """run all selected envs"""
        failed = False
        for e in envlist:
            res = self.run_env(e, self.commands_per_env[e])
            if not res:
                failed = True
        if failed:
            print('Some commands failed.')
            raise SystemExit(1)
        print('All commands succeeded.')
        raise SystemExit(0)


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Re-run tox test commands for a '
                                'given environment against the '
                                'already-existing and installed virtualenv.')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False,
                   help='verbose output')
    p.add_argument('TOXENV', type=str, nargs='+', help='Tox environment name')
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    script = ToxIt()
    script.run(args.TOXENV)
