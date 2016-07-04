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
2016-07-03 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import argparse
import logging
import subprocess
from ConfigParser import SafeConfigParser

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


class ToxIt(object):
    """re-run tox commands against an existing environment"""

    ignore_commands = [
        'python --version',
        'virtualenv --version',
        'pip --version',
        'pip freeze'
    ]

    def __init__(self):
        # in the future we should search for this, or have an arg for it
        self.toxinidir = os.path.abspath(os.getcwd())
        logger.debug('toxinidir: %s', self.toxinidir)
        fpath = os.path.join(self.toxinidir, 'tox.ini')
        logger.debug('tox path: %s', fpath)
        if not os.path.exists(fpath):
            raise Exception("ERROR: %s does not exist" % fpath)
        logger.debug('Parsing commands per env')
        self.commands_per_env = self.parse_toxini(fpath)
        logger.debug('Commands per env: %s', self.commands_per_env)

    def parse_toxini(self, toxini_path):
        """parse the tox ini, return dict of environments to list of commands"""
        cp = SafeConfigParser()
        logger.debug('Reading %s with SafeConfigParser', toxini_path)
        cp.read(toxini_path)
        sections = cp.sections()
        logger.debug('Config sections: %s', sections)
        if 'tox' not in sections:
            raise Exception('Error: tox.ini does not have a "tox" section')
        envs = cp.get('tox', 'envlist')
        envs = envs.split(',')
        logger.debug('tox envs: %s', envs)
        default_cmds = []
        env_cmds = {}
        for s in sections:
            if s == 'tox':
                continue
            raw_cmds = cp.get(s, 'commands').split("\n")
            cmds = []
            for c in raw_cmds:
                c = c.strip()
                if c == '':
                    continue
                if c in self.ignore_commands:
                    logger.debug('%s - skipping ignored command: %s', s, c)
                    continue
                if c.startswith('#'):
                    logger.debug('%s - skipping comment: %s', s, c)
                    continue
                cmds.append(c)
            logger.debug('%s commands: %s', s, cmds)
            if s == 'testenv':
                default_cmds = cmds
                continue
            if not s.startswith('toxenv:'):
                logger.info('Ignoring section: %s', s)
            s = s[7:]
            env_cmds[s] = cmds
        for e in envs:
            if e not in env_cmds:
                logger.debug('Setting default (testenv) commands for %s', e)
                env_cmds[e] = default_cmds
        return env_cmds


    def run_env(self, envname, cmd_list):
        """run a single env; return True (success) or False (failure)"""
        bindir = os.path.join(self.toxinidir, '.tox', envname, 'bin')
        if not os.path.exists(os.path.join(bindir, 'python')):
            logger.debug('No python binary in %s', bindir)
            logger.critical('Error: %s does not appear to have a '
                            'working virtualenv', envname)
            return False
        for c in cmd_list:
            cmd = self.fix_command(c, bindir)
            logger.info('Running command: %s', cmd)
            rcode = subprocess.call(cmd, shell=True)
            logger.info('Command exited %s', rcode)
            if rcode != 0:
                return False
        return True


    def fix_command(self, cmd, bindir):
        """transform a command to run outside tox"""
        """
        py.test -rxs -vv --durations=10 -m "acceptance" {posargs} rpymostat
        rm -Rf {toxinidir}/docs/build/html

        """
        cmd = cmd.format(
            posargs='',
            toxinidir=self.toxinidir
        )
        cmd = bindir + '/' + cmd
        return cmd


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
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('TOXENV', type=str, nargs='+', help='Tox environment name')
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = ToxIt()
    script.run(args.TOXENV)
