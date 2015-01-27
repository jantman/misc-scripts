#!/usr/bin/env python
"""
Script to take a list of [TomTom](http://wow.curseforge.com/addons/tomtom/)
WoW addon coordinates and output them in the optimal order.

This script uses Philippe Guglielmetti's [Goulib](https://pypi.python.org/pypi/Goulib/1.8.3)
implementation of the hill-climbing algorithm for solving the TSP.

Requirements
-------------

This script requires Python 2.7+ (including 3.x) and the following packages,
which can be installed via ``pip``:

* ``matplotlib`` (for plotting)
* ``Goulib``

Usage
------

Put your waypoints in a text file, one per line. Format should be anything designed
for TomTom, specifically anything matching:

    '(/way)?[ ]?(\d+[\.]?\d*)[, ]+(\d+(.)?\d*)'

The points will be ordered optimally and output to STDOUT. With the ``-o`` option,
they will be written to a file in addition to STDOUT. ``--macro`` will break output
into macro-length sections.

ToDo
-----

- Start route at a given point?
- Plot on zone map?

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
2015-01-26 Jason Antman <jason@jasonantman.com>:
* fix minor bug on line 170

2015-01-25 Jason Antman <jason@jasonantman.com>:
* initial version of script
"""

import sys
import argparse
import logging
import matplotlib.pyplot as plt
import itertools
import re
from math import hypot
from Goulib import optim

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


class TomTomTSP:
    """ might as well use a class. It'll make things easier later. """

    def __init__(self, infile, outfile=None, verbose=0, plot=False, numiter=10000, macro=False):
        """ init method, run at class creation """
        line_re = re.compile(r'(/way)?[ ]?(\d+[\.]?\d*)[, ]+(\d+(.)?\d*)')
        self.logger = logging.getLogger(self.__class__.__name__)
        if verbose > 1:
            self.logger.setLevel(logging.DEBUG)
        elif verbose > 0:
            self.logger.setLevel(logging.INFO)
        self.outfile = outfile
        self.plot = plot
        self.macro = macro
        self.numiter = numiter
        self.infile = infile
        # read in the file
        with open(infile, 'r') as fh:
            lines = fh.readlines()
        # parse waypoints - both list and set
        self.waypoints = set()
        self.original_order = []
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
                c = (float(m.group(2)), float(m.group(3)))
                self.waypoints.add(c)
                if c not in self.original_order:
                    self.original_order.append(c)
            except Exception as ex:
                self.logger.error("ERROR parsing line {n}: {l}".format(l=line, n=lineno))
                self.logger.exception(ex)
                raise SystemExit()
        self.logger.info("Loaded {n} waypoints from {i}".format(n=len(self.waypoints), i=infile))
        self.logger.debug("List length={l} set length={s}".format(l=len(self.original_order), s=len(self.waypoints)))

    def run(self):
        """ do stuff here """
        self.logger.info("info-level log message")
        self.logger.debug("Calculating TSP route...")
        tour = self.optim_wrapper()
        self.logger.debug("Done calculating route.")
        if self.macro:
            out = self.tour_macro(tour)
        else:
            out = self.output_tour(tour)
        print(out)
        if self.outfile is not None:
            with open(self.outfile, 'w') as fh:
                fh.write(out)
            self.logger.info("Output written to: {o}".format(o=out))
        if self.plot:
            plt.subplot(211)
            plt.title("Original")
            self.plot_tour(self.original_order)
            plt.subplot(212)
            plt.title("Optimal Order")
            self.plot_tour(tour)
            self.logger.info("Plots written to: {i}.png".format(i=self.infile))
            plt.savefig('{i}.png'.format(i=self.infile), bbox_inches='tight')

    def optim_wrapper(self):
        """ wrap Goulib.optim.tsp and return result """
        self.logger.debug("Running Goulib.optim.tsp with {n} iterations".format(n=self.numiter))
        r = optim.tsp(self.original_order,
                      self.distance,
                      max_iterations=10000,
                      close=False)
        # returns tuple; 2 is list of input indexes
        res = []
        # generate a list of points
        for idx in r[2]:
            res.append(self.original_order[idx])
        return res

    def plot_tour(self, tour):
        "Apply a TSP algorithm to cities, and plot the resulting tour."
        # Plot the tour as blue lines between blue circles, and the starting city as a red square.
        self.plotline(list(tour) + [tour[0]])
        self.plotline([tour[0]], 'rs')

    def plotline(self, points, style='bo-'):
        "Plot a list of points (complex numbers) in the 2-D plane."
        X, Y = self.XY(points)
        plt.plot(X, Y, style)

    def XY(self, points):
        "Given a list of points, return two lists: X coordinates, and Y coordinates."
        return [p[0] for p in points], [p[1] for p in points]

    def output_tour(self, tour):
        """ return TomTom-style string """
        s = ''
        for i in tour:
            s += self.format_point(i) + "\n"
        return s

    def format_point(self, p):
        return '/way {x}, {y}'.format(x=p[0], y=p[1])

    def tour_macro(self, tour):
        """ return TomTom-style macro-safe string """
        s = ''
        tmp_s = ''
        count = 0
        for i in tour:
            tmp = self.format_point(i) + "\n"
            if len(tmp_s) + len(tmp) > 255:
                count += 1
                s += "# macro {c}\n{t}".format(c=count, t=tmp_s)
                tmp_s = ''
            tmp_s += tmp
        if tmp_s != '':
            if s == '':
                s = tmp_s
            else:
                count += 1
                s += "# macro {c}\n{t}".format(c=count, t=tmp_s)
        return s

    def distance(self, A, B):
        "The distance between two points."
        return abs(hypot(B[0]-A[0], B[1]-A[1]))


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
    p.add_argument('-p', '--plot', dest='plot', action='store_true', default=False,
                   help='also output a plot image of the route')
    p.add_argument('-n', '--num-iterations', dest='numiter', action='store', type=int, default=10000,
                   help='number of iterations - more iterations yields a more accurate result')
    p.add_argument('-m', '--macro', action='store_true', default=False,
                   help='split output into chunks < 255 characters each')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    script = TomTomTSP(args.infile,
                       outfile=args.outfile,
                       verbose=args.verbose,
                       plot=args.plot,
                       numiter=args.numiter,
                       macro=args.macro)
    script.run()
