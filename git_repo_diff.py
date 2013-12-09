#!/usr/bin/env python
"""
Python script to tell what branches differ between two git repos,
both by existence and head commit.

Reqires GitPython>=0.3.2.RC1
"""

import os
import sys

import git

def main():
    if len(sys.argv) < 2:
        print("USAGE: git_repo_diff.py path1 path2")
        sys.exit(2)

    repos = {sys.argv[1]: {'other': sys.argv[2]}, sys.argv[2]: {'other': sys.argv[1]}}
    for p in repos:
        if not os.path.exists(p) or not os.path.isdir(p):
            print("ERROR: %s is not a directory or does not exist." % p)
            sys.exit(1)
        d = os.path.join(p, '.git')
        if not os.path.exists(d) or not os.path.isdir(d):
            print("ERROR: %s does not appear to be a git clone" % p)
            sys.exit(1)
        o = git.Repo(p)
        if o.bare:
            print("ERROR: repo in %s is bare." % p)
            sys.exit(1)
        repos[p]['obj'] = o
        # find the branches and their commits
        origin = o.remotes.origin
        origin.fetch()
        refs = {}
        for b in origin.refs:
            foo = {}
            foo['hexsha'] = b.commit.hexsha
            foo['author'] = b.commit.author
            foo['date'] = b.commit.authored_date
            foo['message'] = b.commit.message
            refs[b] = foo
        repos[p]['refs'] = refs

    # now compare them
    reported = []
    for p in repos:
        other = repos[p]['other']
        for ref in repos[p]['refs']:
            if ref not in repos[other]['refs']:
                print("ref %s in %s but not %s" % (ref, p, other))
            else:
                if repos[p]['refs'][ref]['hexsha'] != repos[other]['refs'][ref]['hexsha']:
                    if ref in reported:
                        continue
                    print("ref %s differs between repos:" % ref)
                    print("\t%s: sha=%s author=%s date=%s" % (p, repos[p]['refs'][ref]['hexsha'],
                                                              repos[p]['refs'][ref]['author'],
                                                              repos[p]['refs'][ref]['date']))
                    print("\t%s: sha=%s author=%s date=%s" % (other, repos[other]['refs'][ref]['hexsha'],
                                                              repos[other]['refs'][ref]['author'],
                                                              repos[other]['refs'][ref]['date']))
                    reported.append(ref)

if __name__ == "__main__":
    main()
