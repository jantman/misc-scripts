#!/usr/bin/env python

"""
dot_find_cycles.py - uses Pydot and NetworkX to find cycles in a dot file directed graph.

Very helpful for Puppet stuff.

By Jason Antman <jason@jasonantman.com> 2012.

Free for all use, provided that you send any changes you make back to me, update the changelog, and keep this comment intact.

REQUIREMENTS:
Python
python-networkx - <http://networkx.lanl.gov/>
graphviz-python - <http://www.graphviz.org/>
pydot - <http://code.google.com/p/pydot/>
pydotplus - <http://pydotplus.readthedocs.io/>

To install requirements:

    pip install networkx graphviz pydot pydotplus

Last Test Requirement Versions:

decorator==4.0.10
graphviz==0.5.1
networkx==1.11
pydot==1.2.2
pydotplus==2.0.2
pyparsing==2.1.9

USAGE:
dot_find_cycles.py /path/to/file.dot

The canonical source of this script can always be found from:
<http://blog.jasonantman.com/2012/03/python-script-to-find-dependency-cycles-in-graphviz-dot-files/>

CHANGELOG:
2017-04-20 Frank Kusters <frank.kusters@sioux.eu>:
  - added support for stdin

2016-09-24 Jason Antman <jason@jasonantman.com>:
  - update docs to clarify the below

2016-09-24 jrk07 <https://github.com/jrk07>:
  - add pydotplus and fix read_dot import to work with modern networkx versions

2012-03-28 Jason Antman <jason@jasonantman.com>:
  - initial script creation
"""

import sys
from os import path, access, R_OK
import argparse
import networkx as nx
from networkx.drawing.nx_pydot import read_dot

def main():
    parser = argparse.ArgumentParser(description="Finds cycles in dot file graphs, such as those from Puppet. "
            "By Jason Antman <http://blog.jasonantman.com>")
    parser.add_argument('dotfile', metavar='DOTFILE', nargs='?', type=argparse.FileType('r'), default=sys.stdin,
            help="the dotfile to process. Uses standard input if argument is '-' or not present")
    args = parser.parse_args()

    # read in the specified file, create a networkx DiGraph
    G = nx.DiGraph(read_dot(args.dotfile))

    C = nx.simple_cycles(G)
    for i in C:
        print i

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass  # eat CTRL+C so it won't show an exception
