#!/usr/bin/env python
"""
pacman_compare.py

Compare packages in two files containing ``pacman -Q`` output. Ignores
versions.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/pacman_compare.py>

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2015-09-23 Jason Antman <jason@jasonantman.com>:
  - add option to include package description in output
2015-09-22 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import argparse
import subprocess
import re


class PacmanCompare:
    """compare packages in two ``pacman -Q`` outputs, ignoring versions"""

    desc_re = re.compile(r'^Description\s*: (.+)$')

    def read_packages(self, fpath):
        packages = []
        with open(fpath, 'r') as fh:
            for line in fh.readlines():
                if line.strip() == '':
                    continue
                packages.append(line.split(' ')[0])
        return sorted(packages)

    def get_package_desc(self, pkgname):
        """get the package description string"""
        try:
            p = subprocess.check_output(['pacman', '-Qi', pkgname])
        except subprocess.CalledProcessError:
            return '<not in local pacman database>'
        for line in p.split('\n'):
            m = self.desc_re.match(line)
            if m is None:
                continue
            return m.group(1)
        return '<unknown - could not parse pacman output>'

    def run(self, fileA, fileB, description=False):
        """ do stuff here """
        if not os.path.exists(fileA):
            raise SystemExit("ERROR: FILEA_PATH %s does not exist" % fileA)
        if not os.path.exists(fileB):
            raise SystemExit("ERROR: FILEA_PATH %s does not exist" % fileB)
        info = [
            {
                'packages': self.read_packages(fileA),
                'fname': os.path.basename(fileA),
                'only': [],
            },
            {
                'packages': self.read_packages(fileB),
                'fname': os.path.basename(fileB),
                'only': [],
            },
        ]
        if info[0]['packages'] == info[1]['packages']:
            print("Package lists identical (ignoring versions)")
            raise SystemExit(0)
        for pkname in info[0]['packages']:
                if pkname not in info[1]['packages']:
                    info[0]['only'].append(pkname)
        for pkname in info[1]['packages']:
                if pkname not in info[0]['packages']:
                    info[1]['only'].append(pkname)
        for idx in [0, 1]:
            print("%d packages only in %s (FILEA) of %d total" % (
                len(info[idx]['only']),
                info[idx]['fname'],
                len(info[idx]['packages']))
            )
            if len(info[idx]['only']) > 0:
                for x in info[idx]['only']:
                    if not description:
                        print(x)
                    else:
                        print("%s : %s" % (x, self.get_package_desc(x)))
                print("")

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('-D', '--description', dest='description', action='store_true',
                   default=False,
                   help='include package description in output')
    p.add_argument('FILEA_PATH', type=str)
    p.add_argument('FILEB_PATH', type=str)
    args = p.parse_args(argv)
    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    script = PacmanCompare()
    script.run(args.FILEA_PATH, args.FILEB_PATH, description=args.description)
