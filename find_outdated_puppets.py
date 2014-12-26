#!/usr/bin/env python2
"""
Script to look at a Puppet Dashboard unhidden-nodes.csv and extract the latest report time for each node.
Optionally, list nodes with runtime BEFORE a string.

ABANDONED - no longer used or maintained.

"""
import csv
from datetime import datetime
import optparse
import os
from dateutil import parser as dateutil_parser
import sys
import pytz

# for column output formatting, max len of a node name
NODE_NAME_MAXLEN = 40

def read_node_csv(fname):
    """
    Read in the nodes CSV and return a hash of node name to latest line for each node.
    """

    # our final hash of nodename => row
    nodes = {}

    # read in the CSV file
    f = open(fname, 'rb')
    cr = csv.reader(f, delimiter=',')

    # iterate the rows. first row is headers.
    rownum = 0
    time_col = 0
    for row in cr:
        # Save header row.
        if rownum == 0:
            header = row
            colnum = 0
            for col in row:
                if row[colnum] == "time":
                    time_col = colnum
                colnum += 1
        else:
            date_str = row[time_col]
            # sometimes the date is missing. in that case, it should be OLD...
            if date_str == '':
                date_str = '1970-01-01 01:00 UTC'
            try:
                date_dt = dateutil_parser.parse(date_str)
            except:
                print "Error converting time string '%s' for node '%s'" % (date_str, row[0])
                date_dt = datetime(1970, 1, 1)
            temp = {}
            colnum = 0
            for col in row:
                temp[header[colnum]] = col
                colnum += 1
            temp['date'] = date_dt
            if row[0] not in nodes:
                nodes[row[0]] = temp
            if date_dt > nodes[row[0]]['date']:
                nodes[row[0]] = temp
        rownum += 1
    f.close()
    return nodes

if __name__ == '__main__':
    # if the program is executed directly parse the command line options
    # and read the text to paste from stdin

    parser = optparse.OptionParser()
    parser.add_option('-f', '--file', dest='fname', default='unhidden-nodes.csv',
                      help='path to unhidden-nodes.csv file (default unhidden-nodes.csv)')

    parser.add_option('-b', '--before', dest='before_str', default='',
                       help='show only nodes last reported before this date string (optional)')

    parser.add_option('-c', '--csv', dest='csv', default=False, action='store_true',
                      help='output as CSV rather than columns (optional)')

    options, args = parser.parse_args()

    if options.before_str:
        try:
            before_dt = pytz.UTC.localize(dateutil_parser.parse(options.before_str))
        except:
            print "Error converting time string '%s' to datetime - failing." % options.before_str
            sys.exit(2)

    if not os.path.exists(options.fname):
        print "ERROR: Unable to open file %s" % options.fname

    # parse CSV and get back a dict
    nodes = read_node_csv(options.fname)

    # get a list of key/value pairs
    node_dates = {}
    for node in nodes:
        node_dates[node] = nodes[node]['date']

    # sort by date
    nodes_sorted = sorted(node_dates.iteritems(), key=lambda (k,v): (v,k), reverse=True)

    # format string for column output
    fmt_str = "{:%ds}{:^16s}{:>20s}" % NODE_NAME_MAXLEN

    # output
    for node, date in nodes_sorted:
        if options.before_str and date >= before_dt:
            continue
        if options.csv:
            print "{:s},{:s},{:s}".format(node, date.strftime("%Y-%m-%d %H:%M"), nodes[node]['status'])
        else:
            print fmt_str.format(node, date.strftime("%Y-%m-%d %H:%M"), nodes[node]['status'])
