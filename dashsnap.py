#!/usr/bin/env python
"""
script to snapshot a graphite dashboard at specified intervals in
the past (i.e. the last 2,4,6 hours) or a single specified time range.

Snapshots all images on the dashboard as PNGs (1024x768 by default) as
well as the raw JSON data

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/dashsnap.py

CHANGELOG:

2014-03-16 jantman:
- initial script
"""

import requests
import anyjson
import time
import optparse
import sys
from datetime import datetime
import os

from pprint import pprint

def make_safe_filename(s):
    """
    return a safe file or directory name for a given string
    http://stackoverflow.com/a/7406369
    """
    keepcharacters = ('.','_','-')
    s = s.replace(' ', '_')
    return "".join(c for c in s if c.isalnum() or c in keepcharacters).rstrip()

def get_dashboard_graphs(graphite, dashboard, verbose=False):
    """
    Get the dicts representing all graphs on the specified dashboard.

    :rtype: list of dicts
    """
    dashboard_url = 'http://%s/dashboard/load/%s?_dc=%d' % (graphite, dashboard, int(time.time()))
    if verbose:
        print("Getting dashboard json: %s" % dashboard_url)
    r = requests.get(dashboard_url)
    if r.status_code != 200:
        print("ERROR: got status code %d" % r.status_code)
        return None
    graphs = r.json()
    graph_list = []
    for g in graphs['state']['graphs']:
        graph_list.append(g[1])
    return graph_list

def make_snapshots(graphite, outdir, graphs, from_datetime=None, to_datetime=None, intervals=None, verbose=False, height=768, width=1024, name=None):
    """
    Capture PNG and JSON snapshots of graphs

    EITHER from_datetime and to_datetime *or* intervals (list of from= strings)
    """
    from_until_pairs = []
    dirs = {}
    if from_datetime is not None and to_datetime is not None:
        from_until_pairs.append( (from_datetime.strftime("%H:%M_%Y%m%d"), to_datetime.strftime("%H:%M_%Y%m%d")) )
    else:
        for i in intervals:
            from_until_pairs.append( (i, 'now'))
    if verbose:
        print("starting %d snapshot sets..." % len(from_until_pairs))
    for (from_str, until_str) in from_until_pairs:
        t = make_safe_filename(from_str + "_to_" + until_str)
        dirname = os.path.join(outdir, t)
        os.mkdir(dirname)
        snapshot_graphs(graphite, dirname, graphs, from_str, until_str, height=height, width=width, verbose=verbose, name=name)
        dirs[t] = "%s to %s" % (from_str, until_str)
    if verbose:
        print("make_snapshots finished")
    write_snapshots_index(outdir, dirs, title=name, verbose=verbose)
    return True

def write_snapshots_index(outdir, dirs, title="", verbose=False):
    s = "<p>%s</p>\n<ul>" % title
    for d in dirs:
        s = s + "<li><a href=\"%s/index.html\">%s</a></li>" % (d, dirs[d])
    s = s + "</ul>"
    with open(os.path.join(outdir, 'index.html'), 'w') as fh:
        fh.write(format_html(title, s))
    return True

def snapshot_graphs(graphite, outdir, graphs, graph_from, graph_until, height=768, width=1024, verbose=False, name=None):
    """
    snapshot a dashboard with a given from and until time
    return a list of the filenames that were created
    """
    url = "http://%s/render" % graphite
    untitled_count = 0
    img_count = 0
    json_count = 0
    files = []
    for gdict in graphs:
        gdict['height'] = "%d" % height
        gdict['width'] = "%d" % width
        gdict['from'] = graph_from
        gdict['until'] = graph_until
        if 'title' in gdict:
            fname = make_safe_filename(gdict['title'])
        else:
            fname = "untitled_%d" % untitled_count
            untitled_count = untitled_count + 1
        img_path = os.path.join(outdir, fname + '.png')
        if verbose:
            print("getting image for %s" % fname)
        img = requests.get(url, params=gdict)
        if img.status_code != 200:
            print("ERROR: got status %d for %s" % (img.status_code, img.url))
        else:
            fh = open(img_path, 'wb')
            fh.write(img.content)
            fh.close()
            if verbose:
                print("\twrote image to %s" % img_path)
            img_count = img_count + 1
        json_path = os.path.join(outdir, fname + '.json')
        if verbose:
            print("getting JSON for %s" % fname)
        gdict['format'] = 'json'
        json_data = requests.get(url, params=gdict)
        print(json_data.url)
        if json_data.status_code != 200:
            print("ERROR: got status %d for %s" % (json_data.status_code, json_data.url))
        else:
            fh = open(json_path, 'wb')
            fh.write(json_data.content)
            fh.close()
            if verbose:
                print("\twrote JSON to %s" % json_path)
            json_count = json_count + 1
        files.append(fname)
    if verbose:
        print("saved %d graph images and %d raw JSON data files" % (img_count, json_count))
    write_image_index(outdir, files, orig_height=height, orig_width=width, title="%s from %s to %s" % (name, graph_from, graph_until), verbose=verbose)
    return True

def write_image_index(outdir, files, orig_height=768, orig_width=1024, title="", verbose=False):
    height = int(orig_height / 4)
    width = int(orig_width / 4)
    s = "<table border=\"1\">\n<tr>"
    for i, fname in enumerate(files):
        s = s + "<td>%s<br />\n" % fname
        s = s + "<a href=\"%s.png\">\n" % fname
        s = s + "<img src=\"%s.png\" height=\"%d\" width=\"%d\" />\n" % (fname, height, width)
        s = s + "</a><br /><a href=\"%s.json\">json</a></td>\n" % (fname)
        if (i + 1) % 4 == 0:
            s = s + "</tr>\n<tr>"
    s = s + "</tr></table>"
    with open(os.path.join(outdir, 'index.html'), 'w') as fh:
        fh.write(format_html(title, s))
    return True

def format_html(title, body):
    html_head = """
<html>
<head>
<title>%s</title>
</head>
<body>
"""
    html_foot = """
<p>created with <a href="https://github.com/jantman/misc-scripts/blob/master/dashsnap.py">https://github.com/jantman/misc-scripts/blob/master/dashsnap.py</a></p>
</body>
</html>
"""
    s = html_head % title
    s = s + body + html_foot
    return s

def parse_args(argv):
    """ parse command line options """
    parser = optparse.OptionParser()

    default_intervals = '-10minutes,-30minutes,-1hours,-2hours,-4hours,-6hours,-12hours,-24hours,-36hours'

    parser.add_option('-g', '--graphite', dest='graphite', action='store', type='string', default='graphite',
                      help='graphite web UI hostname')

    parser.add_option('-d', '--dashboard', dest='dashboard', action='store', type='string',
                      help='dashboard name to snapshot')

    parser.add_option('-i', '--intervals', dest='intervals', action='store', type='string', default=default_intervals,
                      help="list of graphite-style from intervals to snapshot (implicitly until=now)\nDefault: %s" % default_intervals)

    parser.add_option('-f', '--from', dest='from_str', action='store', type='string',
                      help='from time, [Y-m-d ]H:M:S')

    parser.add_option('-u', '--until', dest='to_str', action='store', type='string',
                      help='until time, [Y-m-d ]H:M:S')

    parser.add_option('-e', '--height', dest='height', action='store', type='int', default=768,
                      help='image height (default 768)')

    parser.add_option('-w', '--width', dest='width', action='store', type='int', default=1024,
                      help='image width (default 1024)')

    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output')

    options, args = parser.parse_args(argv)

    if not options.dashboard:
        raise SystemExit("ERROR: you must specify dashboard with -d|--dashboard")

    if (options.from_str and not options.to_str) or (options.to_str and not options.from_str):
        raise SystemExit("ERROR: -f|--from and -u|--until must be specified together")

    time_formats = ['%Y-%m-%d %H:%M:%S', '%H:%M:%S']
    options.from_date = None
    options.to_date = None
    if options.from_str:
        from_date = None
        for f in time_formats:
            try:
                from_date = datetime.strptime(options.from_str, f)
            except ValueError:
                pass
        if not from_date:
            raise SystemExit("Invalid date format: %s" % options.from_str)
        options.from_date = from_date
    if options.to_str:
        to_date = None
        for f in time_formats:
            try:
                to_date = datetime.strptime(options.to_str, f)
            except ValueError:
                pass
        if not to_date:
            raise SystemExit("Invalid date format: %s" % options.to_str)
        options.to_date = to_date

    if options.to_str and options.from_str:
        options.intervals = None
        today = datetime.now()
        if options.from_date.year == 1900:
            options.from_date = options.from_date.replace(today.year, today.month, today.day)
        if options.to_date.year == 1900:
            options.to_date = options.to_date.replace(today.year, today.month, today.day)
        if options.to_date <= options.from_date:
            raise SystemExit("ERROR: -f|--from must be less than -u|--until")

    if options.intervals:
        options.intervals = options.intervals.split(',')

    return options

if __name__ == "__main__":
    opts = parse_args(sys.argv)

    if opts.verbose:
        if opts.intervals:
            print("using intervals: %s" % opts.intervals)
        else:
            print("using explicit from and to dates: %s to %s" % (opts.from_date.strftime("%Y-%m-%d %H:%M:%S"), opts.to_date.strftime("%Y-%m-%d %H:%M:%S")))

    graphs = get_dashboard_graphs(opts.graphite, opts.dashboard, verbose=opts.verbose)
    if opts.verbose:
        print("Got %d graphs" % len(graphs))
    outdir = "%s-%s" % (opts.dashboard, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    print("writing output to: %s" % outdir)
    os.mkdir(outdir)
    make_snapshots(opts.graphite, outdir, graphs,
                   verbose=opts.verbose,
                   from_datetime=opts.from_date,
                   to_datetime=opts.to_date,
                   intervals=opts.intervals,
                   height=opts.height,
                   width=opts.width,
                   name=opts.dashboard )
