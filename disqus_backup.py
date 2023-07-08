#!/usr/bin/env python
"""
Simple script to backup Disqus comments/threads to
a specified JSON file.

To use this, you'll need to register an Application for the Disqus API,
and get its secret and public keys. Do so at http://disqus.com/api/applications/

Requirements:
disqus-python (the official API client)
anyjson
>  pip install disqus-python anyjson

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/disqus_backup.py>
"""

import json
import optparse
import sys
import os

from disqusapi import DisqusAPI, Paginator, APIError

def backup_disqus(short_name, key, secret, outfile, min_comments=5, verbose=False):
    """
    backup disqus threads and comments for a given forum shortname

    :param short_name: Disqus forum short name / ID
    :type short_name: string
    :param key: Disqus API public key
    :type key: string
    :param secret: Disqus API secret key
    :type secret: string
    :param outfile: path to the file to write JSON output to
    :type outfile: string
    :param min_comments: minimum number of posts to have, else error and exit
    :type min_comments: integer (default 5)
    :param verbose: whether to write verbose output
    :type verbose: boolean
    """
    result = {}
    disqus = DisqusAPI(secret, key)

    if verbose:
        print("Connected to Disqus API")
    try:
        details = disqus.forums.details(forum=short_name)
    except disqusapi.APIError:
        sys.stderr.write("ERROR: unable to find forum '%s'\n" % short_name)
        sys.exit(1)
    result['forum_details'] = details
    if verbose:
        print("Got forum details for '%s': %s" % (short_name, str(details)))

    try:
        threads = Paginator(disqus.forums.listThreads, forum=short_name)
    except APIError:
        sys.stderr.write("ERROR listing threads for forum '%s'\n" % short_name)
        sys.exit(1)
    thread_count = 0
    all_threads = []
    for t in threads:
        thread_count = thread_count + 1
        all_threads.append(t)
    if verbose:
        print("Found %d threads" % thread_count)

    result['threads'] = all_threads

    try:
        posts = Paginator(disqus.forums.listPosts, forum=short_name, include=['unapproved','approved'])
    except APIError:
        sys.stderr.write("ERROR listing posts for forum '%s'\n" % short_name)
        sys.exit(1)
    post_count = 0
    all_posts = []
    for p in posts:
        post_count = post_count + 1
        all_posts.append(p)
    if verbose:
        print("Found %d posts" % post_count)

    result['posts'] = all_posts


    with open(outfile, 'w') as fh:
        json.dump(result, fh)
    sys.stderr.write("Output written to %s\n" % outfile)
    return True

def parse_options(argv):
    """ parse command line options """
    parser = optparse.OptionParser()

    parser.add_option('-n', '--short-name', dest='short_name', action='store', type='string',
                      help='forum short name / ID')

    parser.add_option('-o', '--outfile', dest='outfile', action='store', type='string', default="disqus_backup.json",
                      help='output filename')

    parser.add_option('-m', '--minimum-comments', dest='min_comments', action='store', type='int', default=5,
                      help='error if less than this number of comments')

    parser.add_option('--secret', dest='secret', action='store', type='string',
                      help="Disqus API Secret Key - will try to read from DISQUS_SECRET env var if option not specified")

    parser.add_option('--key', dest='key', action='store', type='string',
                      help="Disqus API Public Key - will try to read from DISQUS_KEY env var if option not specified")

    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output')

    options, args = parser.parse_args(argv)

    if not options.short_name:
        sys.stderr.write("ERROR: you must specify forum short name (ID) with -n|--short-name\n")
        sys.exit(1)

    if not options.secret:
        try:
            options.sercret = os.environ['DISQUS_SECRET']
        except KeyError:
            sys.stderr.write("ERROR: Disqus API secret key must be passed with --secret, or defined in DISQUS_SECRET env variable.\n")
            sys.exit(1)

    if not options.key:
        try:
            options.key = os.environ['DISQUS_KEY']
        except KeyError:
            sys.stderr.write("ERROR: Disqus API Publc key must be passed with --key, or defined in DISQUS_KEY env variable.\n")
            sys.exit(1)

    return options

if __name__ == "__main__":
    opts = parse_options(sys.argv)
    backup_disqus(opts.short_name, opts.key, opts.secret, opts.outfile, min_comments=opts.min_comments, verbose=opts.verbose)
