#!/usr/bin/env python
"""
Python script to tell what branches differ between two git repos,
both by existence and head commit.
"""

import os
import sys

import git

def main():
    if len(sys.argv) < 2:
        print("USAGE: git_repo_diff.py path1 path2")
        sys.exit(2)

    repos = {sys.argv[1]: {}, sys.argv[2]: {}}
    for p in repos:
        if not os.path.exists(p) or not os.path.isdir(p):
            print("ERROR: %s is not a directory or does not exist." % p)
            sys.exit(1)
        d = os.path.join(p, '.git')
        if not os.path.exists(d) or not os.path.isdir(d):
            print("")
            sys.exit(1)
        o = git.Repo(p)
        if o.bare:
            print("ERROR: repo in %s is bare." % p)
            sys.exit(1)
        repos[p]['obj'] = o
        # find the branches and their commits
        origin = o.remotes.origin
        #origin.fetch()
        refs = {}
        for b in o.refs:
            foo = {}
            foo['hexsha'] = b.commit.hexsha
            foo['author'] = b.commit.author
            foo['date'] = b.commit.authored_date
            foo['message'] = b.commit.message
            refs[b] = foo

    # now compare them


if __name__ == "__main__":
    main()

def get_repo_commit_age(repo_path, verbose=False):
    """
    For a given git repository clone (absolute path on disk),
    returns the age in seconds of the newest commit to the
    current branch, or None if the directory doesn't appear to
    be a repository or checked out.
    """
    repo = git.Repo(repo_path)
    if repo.bare:
        if verbose:
            print("skipping bare repository '%s'" % repo_path)
        return None

    #d = repo.is_dirty()
    hc = repo.head.commit
    h_date = hc.authored_date
    if verbose:
        print("\trepo '%s' date '%d' commit '%s'" % (repo_path, h_date, hc))
    return int(time.time() - h_date)


"""
from git import *

        repo = Repo(path)
        if not allow_bare:
            if repo.bare:
                raise Exception("Specified path '%s' does not appear to be a git checkout, or is a bare repo." % path)

        if repo.is_dirty():
            raise Exception("Specified repository '%s' is dirty, cannot run tests." % path)

        self.logger.debug("Initialized git Repo at '%s'" % path)
        self.lint_options = lint_options
        self.repo = repo
        self.path = path
        self.temp_dir = temp_dir

        head_commit = self.repo.head.commit
        branch_diff = head_commit.diff(branchname)
        # 'a' files are our branch, 'b' files are the branch we're diffing against
        for d in branch_diff:
            if d.b_blob is None:
                # this is an added file
                if re.match("^modules-community/", d.a_blob_path):
                    continue
                if re.match(".*\.pp.*", d.a_blob.path):
                    manifests.append(d.a_blob.path)
                if re.match(".*\.erb.*", d.a_blob.path) or re.match(".*templates\/.*", d.a_blob.path):
                    templates.append(d.a_blob.path)
            elif d.a_blob is None:
                # this is a deleted file
                continue
            else:
                if re.match("^modules-community/", d.a_blob_path):
                    continue
                if re.match(".*\.pp.*", d.a_blob.path):
                    manifests.append(d.a_blob.path)
                if re.match(".*\.erb.*", d.a_blob.path) or re.match(".*templates\/.*", d.a_blob.path):
                    templates.append(d.a_blob.path)

"""
