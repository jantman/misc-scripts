#!/usr/bin/env python
"""
Script to take a list of [TomTom](http://wow.curseforge.com/addons/tomtom/)
WoW addon coordinates and output them in the optimal order.

In a more general sense, this script implements the Try-All-Tours exact
algorithm to solve the Traveling Salesman Problem (TSP), using TomTom
waypoint notation as coordinate input.

Requirements
-------------

This script requires Python 2.7+ (including 3.x) and the following packages,
which can be installed via ``pip``:

* matplotlib

Usage
------

Put your waypoints in a text file, one per line. Format should be anything designed
for TomTom, specifically:

The points will be ordered optimally and output to STDOUT. With the ``-o`` option,
they will be written to a file in addition to STDOUT.

The ``--start`` option specifies a point to start at.

Copyright
----------

The latest version of this script is available at:
<https://github.com/jantman/misc-scripts/blob/master/tomtom_tsp.py>

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me, and the author
and script source information is left intact.

The algorithm and implementation used here is mainly thanks to:
<http://nbviewer.ipython.org/url/norvig.com/ipython/TSPv3.ipynb>

CHANGELOG:
2015-01-25 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import matplotlib
import matplotlib.pyplot as plt
import random
import time
import itertools
import re

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


class TomTom_TSP:
    """ might as well use a class. It'll make things easier later. """

    def __init__(self, infile, outfile=None, start=None, verbose=0, plot=False):
        """ init method, run at class creation """
        line_re = re.compile(r'(/way)?[ ]?(\d+[\.]?\d*)[, ]+(\d+(.)?\d*)')
        self.logger = logging.getLogger(self.__class__.__name__)
        if verbose > 1:
            self.logger.setLevel(logging.DEBUG)
        elif verbose > 0:
            self.logger.setLevel(logging.INFO)
        self.outfile = outfile
        self.plot = plot
        # test start format
        if start is not None:
            m = line_re.match(start)
            if not m:
                self.logger.critical("ERROR: --start argument '{s}' is not in correct X,Y format.".format(s=start))
                raise SystemExit()
            self.start = complex(float(m.group(2)), float(m.group(3)))
            self.logger.debug("Setting start point to: {s}".format(s=self.start))
        with open(infile, 'r') as fh:
            lines = fh.readlines()
        self.waypoints = set()
        lineno = 0
        self.logger.debug("Parsing {i}".format(i=infile))
        for line in lines:
            lineno += 1
            line = line.strip()
            if line == '':
                continue
            m = line_re.match(line)
            if not m:
                self.logger.error("Invalid coordinate on line {n}: {l}".format(l=line, n=lineno))
                continue
            try:
                self.waypoints.add(complex(float(m.group(2)), float(m.group(3))))
            except Exception as ex:
                self.logger.error("ERROR parsing line {n}: {l}".format(l=line, n=lineno))
                self.logger.exception(ex)
                raise SystemExit()
        self.logger.info("Loaded {n} waypoints from {i}".format(n=len(self.waypoints), i=infile))

    def run(self):
        """ do stuff here """
        self.logger.info("info-level log message")
        self.logger.debug("Calculating exact TSP route...")
        tour = self.exact_TSP(self.waypoints)
        self.logger.debug("Done calculating route.")
        # OUTPUT HERE
        print(tour)
        print(self.total_distance(tour))
        # look at plotting

    def total_distance(self, tour):
        "The total distance between each pair of consecutive cities in the tour."
        return sum(self.distance(tour[i], tour[i-1]) for i in range(len(tour)))

    def distance(self, A, B):
        "The distance between two points."
        return abs(A - B)

    def exact_TSP(self, points):
        "Generate all possible tours of the cities and choose the shortest one."
        tours = self.alltours(points)
        self.logger.debug("Found {t} possible routes.".format(t=len(tours)))
        return self.shortest(tours)

    def shortest(self, tours):
        "Return the tour with the minimum total distance."
        return min(tours, key=total_distance)

    def alltours(self, points):
        "Return a list of tours, each a permutation of cities, but each one starting with the same city."
        self.logger.debug("Calculating all possible routes...")
        start = self.first(points)
        return [[start] + list(tour)
                for tour in itertools.permutations(points - {start})]

    def first(self, collection):
        "Start iterating over collection, and return the first element."
        for x in collection: return x


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='TomTom WoW addon TSP solver')
    p.add_argument('infile', metavar='INPUT_FILE', type=str,
                   help='Un-ordered waypoint input file')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-o', '--output', dest='outfile', action='store', type=str,
                   help='file to write output to, in addition to STDOUT')
    p.add_argument('-s', '--start', dest='startpoint', action='store', type=str,
                   help='Starting point in X,Y format')
    p.add_argument('-p', '--plot', dest='plot', action='store_true', default=False,
                   help='also output a plot image of the route')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    script = TomTom_TSP(args.infile, outfile=args.outfile, start=args.startpoint, verbose=args.verbose, plot=args.plot)
    script.run()
