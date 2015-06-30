#!/usr/bin/env python
"""
reconcile_github_with_local.py

Given a file containing a list of git repository paths (and optionally all
repositories on a specified GitHub Organization):
- clone all repos into a specified directory (if not already there)
- iterate over them and attempt to find repositories that have the same
  first commit
- for repositories with the same first commit, add one as a remote on the other,
  fetch, and attempt to determine if they're in sync, or if not, which one(s)
  have commits that aren't in the other

Mainly intended to reconcile GitHub repositories with an internal Git server, or
find old/unused repos.

Note that to use this script, you also need reconcile_git_repos.html.tmpl

Copyright / License
--------------------

The canonical version of this script lives at:
<https://github.com/jantman/misc-scripts/blob/master/reconcile_git_repos.py>

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that modifications are submitted back to me.

Requirements (tested versions):
-------------------------------

GitPython==1.0.1
gitdb==0.6.4
smmap==0.9.0
PyGithub==1.25.2
Jinja2==2.7.3
pytz==2015.4
tzlocal==1.2

Changelog
----------
2015-06-30 - initial version
"""

import sys
import os
import argparse
import logging
import git
import datetime
from collections import defaultdict
from itertools import combinations
import json
import pytz
import tzlocal
import time
from jinja2 import Environment, FileSystemLoader

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

from github import Github

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger()

# suppress logging from PyGithub
github_log = logging.getLogger("github")
github_log.setLevel(logging.WARNING)
github_log.propagate = True


def format_ts2str(ts):
    """jinja2 filter to convert integer timestamp to date string"""
    dt = datetime.datetime.fromtimestamp(ts)
    s = dt.strftime("%a %b %d, %Y %H:%M")
    return s


def format_repostats(repodict):
    """jinja2 filter to take one self.repos dict and format stats"""
    s = '{c} commits / {b} branches / {t} tags / newest commit: {n}'.format(
        c=repodict['num_commits'],
        b=repodict['num_branches'],
        t=repodict['num_tags'],
        n=format_ts2str(repodict['newest_timestamp']),
    )
    return s

class GitRepoReconciler(object):

    def __init__(self, repo_names, repo_prefix, clone_dir, github_orgname=None,
                 repo_html_prefix=None, skip=[], skip_tags=[]):
        """
        :param repo_names: list of repository names/paths to clone
        :type repo_names: list of strings
        :param repo_prefix: git url base to prefix to each element in repo_names
        :param clone_dir: local directory to clone repos into
        :type clone_dir: string
        :param github_orgname: name of GH organization to get repos for
        :type github_orgname: string
        :param repo_html_prefix: URL to prefix to repo names to get web view
        :type repo_html_prefix: string
        :param skip: list of repo names to skip
        :type skip: list of strings
        :param skip_tags: list of repo names to skip checking tags in
        :type skip_tags: list of strings
        """
        self.repo_names = repo_names
        self.github_orgname = github_orgname
        self.repo_prefix = repo_prefix
        self.repo_html_prefix = repo_html_prefix
        self.skip = skip
        logger.debug("Skipping repo names: {s}".format(s=self.skip))
        self.skip_tags = skip_tags
        logger.debug("Skipping tags in repo names: {s}".format(s=self.skip_tags))
        logger.debug("Got {l} repos to use".format(l=len(repos)))
        self.gh_repos = {}  # see get_github_org_repo_urls() and run()
        self.clone_dir = os.path.abspath(clone_dir)
        self.repos = {}  # see run() and repo_paths_to_urls()
        self.cache_path = os.path.join(os.path.abspath('.'), 'repocache.json')
        self.out_fname = 'reconcile_git_repos.html'
        if not os.path.exists('reconcile_git_repos.html.tmpl'):
            logger.critical("ERROR: Jinja2 template "
                            "'reconcile_git_repos.html.tmpl' not found in pwd")
            raise SystemExit(1)

    def run(self, fetch=True, cache=False):
        """run it."""
        if cache and os.path.exists(self.cache_path):
            logger.warning("Using repo information from cache")
            self.repos = self.read_cache(self.cache_path)
        else:
            self.get_repo_info(fetch=fetch)
            if cache:
                self.write_cache(self.cache_path, self.repos)
        logger.info("Attempting to find similar repos")
        similar = self.find_similar_repos()
        self.write_output(similar)

    def write_output(self, similar_repos):
        date = datetime.datetime.now(pytz.utc).astimezone(
            tzlocal.get_localzone()
        ).strftime('%Y-%m-%d %H:%M:%S%z %Z')
        logger.debug("Generating HTML from template")
        cutoff_ts = time.time() - (86400*365)
        env = Environment(
            loader = FileSystemLoader('.'),
            extensions=['jinja2.ext.loopcontrols'],
            trim_blocks=True,
        )
        env.filters['ts2str'] = format_ts2str
        env.filters['repostats'] = format_repostats
        template = env.get_template('reconcile_git_repos.html.tmpl')
        html = template.render(
            repos=self.repos,
            similar_repos=similar_repos,
            date=date,
            cutoff_ts=cutoff_ts,
            repo_sorted_timestamp=sorted(
                self.repos,
                key=lambda x: self.repos[x].get('newest_timestamp', 1)),
        )
        logger.warning("Writing HTML output to {f}".format(f=self.out_fname))
        with open(self.out_fname, 'w') as fh:
            fh.write(html)

    def read_cache(self, path):
        """read from cache"""
        with open(path, 'r') as fh:
            raw = fh.read()
        return json.loads(raw)

    def write_cache(self, path, data):
        """write to cache"""
        with open(path, 'w') as fh:
            fh.write(json.dumps(data))

    def get_repo_info(self, fetch=True):
        """get info about the repos; populate self.repos"""
        if self.github_orgname is not None:
            self.gh_repos = self.get_github_org_repos(self.github_orgname)
            logger.info("Found {l} GitHub repositories".format(
                l=len(self.gh_repos)))
        self.repos = self.repo_paths_to_urls(
            self.clone_dir,
            self.repo_names,
            self.gh_repos
        )
        logger.debug("Determined FS paths for {l} repos".format(l=len(repos)))
        logger.info("Cloning/fetching all repos")
        for path, repodict in self.repos.items():
            self.clone_or_fetch(path, repodict['url'], fetch=fetch)
            self.update_repo_info(path, repodict['name'])

    def find_similar_repos(self):
        """
        Find any repositories in self.repos that share the same
        oldest commit. For now, this is all we do for "similar"
        repo detection.

        Format of dicts in return list:
        {
        'repo_paths': [list of paths],
        'comparisons': [
            <return value from compare_repos()>
            ...
        ]
        }

        TODO: need to compare each pair of repos using combinations(reponames, 2);
        figure out number of different branches/tags in each, and difference in commits
        between the default branches of each

        :returns: list, where each element is a dict describing sets
        of self.repos keys (repository paths) that share the same oldest commit
        :rtype: list
        """
        commits = defaultdict(list)
        for path, rdict in self.repos.items():
            if 'oldest_commit' in rdict:
                commits[rdict['oldest_commit']].append(path)
        res = []
        for sha, pathlist in commits.items():
            if len(pathlist) < 2:
                continue
            logger.debug("Found repos with same oldest commit: {l}".format(
                l=pathlist))
            similar_dict = {
                'repo_paths': pathlist,
                'comparisons': [],
            }
            for pathA, pathB in combinations(pathlist, 2):
                similar_dict['comparisons'].append(
                    self.compare_repos(pathA, pathB)
                )
            res.append(similar_dict)
        return res

    def compare_repos(self, pathA, pathB):
        """
        Compare two repositories; return a dict with info about the comparison.

        pathA - path to A repo on disk
        pathB - path to B repo on disk
        branchA - count of branches in A but not B
        branchB - count of branches in B but not A
        branchDiff - count of branches that point to different commits in A/B
        tag(A|B|Diff) - "" for tags
        commitA - count of commits only in A
        commitB - count of commits only in B
        """
        A = self.get_repo_compare_info(pathA)
        B = self.get_repo_compare_info(pathB)
        res = {
            'pathA': pathA,
            'pathB': pathB,
            'branchA': 0,
            'branchB': 0,
            'branchDiff': 0,
            'tagA': 0,
            'tagB': 0,
            'tagDiff': 0,
            'commitA': 0,
            'commitB': 0,
            'Abranch': A['active_branch'],
            'Bbranch': B['active_branch'],
        }
        for _type in ['tag', 'branch']:
            for name, sha in A[_type].iteritems():
                if name not in B[_type]:
                    res[_type + 'A'] += 1
                elif B[_type][name] != A[_type][name]:
                    res[_type + 'Diff'] += 1
            for name, sha in B[_type].iteritems():
                if name not in A[_type]:
                    res[_type + 'B'] += 1
        for sha in A['commits']:
            if sha not in B['commits']:
                res['commitA'] += 1
        for sha in B['commits']:
            if sha not in A['commits']:
                res['commitB'] += 1
        return res

    def get_repo_compare_info(self, path):
        """
        Get information about a repo, to be used for compare_repos()

        branch: dict of name: sha for all branches
        tag: dict of name: sha for all tags
        active_branch: default branch name
        commits: list of commit SHAs in active_branch
        """
        res = {}
        self.clone_or_fetch(path, self.repos[path]['url'], fetch=True)
        repo = git.Repo(path, odbt=git.GitCmdObjectDB)
        res['branch'] = {b.name: b.commit.hexsha for b in repo.branches}
        res['tag'] = {t.name: t.commit.hexsha for t in repo.tags}
        if 'master' in res['branch']:
            logger.debug("Checking out master in {p}".format(p=path))
            repo.branches.master.checkout()
        elif 'trunk' in res['branch']:
            logger.debug("Checking out trunk in {p}".format(p=path))
            repo.branches.trunk.checkout()
        res['active_branch'] = repo.active_branch.name
        res['commits'] = [c.hexsha for c in repo.iter_commits()]
        return res

    def update_repo_info(self, path, name):
        """
        Given a key in self.repos, update its value dict with some
        information about the repo.
        """
        repo = git.Repo(path, odbt=git.GitCmdObjectDB)
        try:
            oldest, newest, num_commits = self.find_oldest_newest(path, repo, name)
            self.repos[path]['oldest_commit'] = oldest.hexsha
            self.repos[path]['newest_commit'] = newest.hexsha
            self.repos[path]['oldest_timestamp'] = oldest.committed_date
            self.repos[path]['newest_timestamp'] = newest.committed_date
            self.repos[path]['num_commits'] = num_commits
        except (ValueError, AttributeError):
            if len(os.listdir(os.path.join(
                    repo.git_dir, 'objects', 'pack'))) == 0:
                self.repos[path]['is_empty'] = True
                logger.warning("Empty repo at {p}".format(p=path))
                del repo  # open files
                return
            logger.critical("Error iterating commits in repo at {p}".format(
                p=path))
            del repo  # open files
            return
        self.repos[path]['num_branches'] = len(repo.branches)
        self.repos[path]['num_tags'] = len(repo.tags)
        del repo  # open files

    def find_oldest_newest(self, path, repo, name):
        """
        Find the oldest and newest commits in the repository.

        see:
        https://github.com/gitpython-developers/GitPython/issues/240#issuecomment-70705360

        :param repo: the git repository object
        :type repo: git.Repo
        :returns: 2-tuple of oldest commit, newest commit, number of commits
        :rtype: 2-tuple of git.objects.commit.Commit, number of commits
        """
        logger.debug("Finding oldest and newest commits in repo at {p}".format(
            p=path))
        oldest = None
        oldest_dt = datetime.datetime.max
        newest = None
        newest_dt = datetime.datetime.min
        commits = set()
        orig_head = repo.head.ref
        # see if we have any remote refs
        try:
            rmt_refs = repo.remotes.origin.refs
        except AssertionError:
            rmt_refs = []
        # create local branches for remote refs
        for ref in rmt_refs:
            logger.debug("New Head from remote: {n} ({c})".format(n=ref.name, c=ref.commit.hexsha))
            repo.create_head(ref.name, ref).set_tracking_branch(ref)
        seen = []
        # iterate all branches and tags
        refs = repo.branches + repo.tags
        if name in self.skip_tags:
            refs = repo.branches
        for ref in refs:
            if ref.commit.hexsha in seen:
                logger.debug("Skipping ref {n} with seen commit {c}".format(n=ref.name, c=ref.commit.hexsha))
                continue
            seen.append(ref.commit.hexsha)
            logger.debug("New Head: {n} ({c})".format(n=ref.name, c=ref.commit.hexsha))
            repo.git.checkout(ref.name)
            for commit in repo.iter_commits():
                commits.add(commit.hexsha)
                t = datetime.datetime.fromtimestamp(commit.committed_date)
                if t < oldest_dt:
                    oldest = commit
                    oldest_dt = t
                if t > newest_dt:
                    newest = commit
                    newest_dt = t
        if oldest is not None:
            logger.debug("Oldest: {od} {oc} ; Newest: {nd} {nc}; {c} commits".format(
                oc=oldest.hexsha,
                od=oldest_dt,
                nc=newest.hexsha,
                nd=newest_dt,
                c=len(commits)))
            orig_head.checkout()
        return (oldest, newest, len(commits))

    def clone_or_fetch(self, path, url, fetch=True):
        """
        Given a absolute path on the local filesystem and a repo url,
        clone the repo in that path if not present, or fetch if present.

        :param fetch: whether or not to fetch existing repos
        :type fetch: bool
        """
        try:
            repo = git.Repo(path, odbt=git.GitCmdObjectDB)
            logger.debug("Using git repo at {p}".format(p=path))
        except git.exc.NoSuchPathError:
            logger.debug("Cloning {u} into {p}".format(u=url, p=path))
            repo = git.Repo.clone_from(url, path, odbt=git.GitCmdObjectDB)
        assert not repo.bare
        assert not repo.is_dirty()
        assert len(repo.remotes) == 1
        if fetch:
            logger.debug("Fetching origin in {p}".format(p=path))
            repo.remotes.origin.fetch()
            logger.debug("Repo up to date: {p}".format(p=path))
        del repo  # open files

    def repo_paths_to_urls(self, clone_dir, repos, gh_repos):
        """
        Return a dict of unique repository names to their URLs
        """
        paths = {}
        for repo in repos:
            repo = self.repo_prefix + repo
            # parse URL
            name = os.path.basename(urlparse.urlparse(repo).path)
            if name in self.skip:
                logger.warning("Skipping repo: {n}".format(n=name))
                continue
            if name in paths:
                logger.critical("Already have a repo named {n}; ignoring "
                                "{u}".format(n=name, u=repo))
            path = os.path.join(clone_dir, name)
            paths[path] = {
                'url': repo,
                'name': name,
                'is_github': False,
                'is_empty': False,
            }
            if self.repo_html_prefix is None:
                paths[path]['html_url'] = None
            else:
                paths[path]['html_url'] = self.repo_html_prefix + name
        for name, repo in gh_repos.items():
            if name in self.skip:
                logger.warning("Skipping GitHub repo: {n}".format(n=name))
                continue
            path = os.path.join(clone_dir, name)
            paths[path] = {
                'url': repo.ssh_url,
                'name': name,
                'is_github': True,
                'html_url': repo.html_url,
                'is_empty': False,
            }
        return paths

    def get_github_org_repos(self, orgname):
        """return a dict of repo names to github.Repository.Repository objects"""
        GH_TOKEN = os.environ.get('GITHUB_TOKEN', None)
        if GH_TOKEN is None:
            logger.critical("ERROR - you must export your GitHub API token as "
                            "the 'GITHUB_TOKEN' environment variable.")
            raise SystemExit(1)
        logger.debug("Authenticating to GitHub API")
        g = Github(login_or_token=GH_TOKEN)

        logger.debug("Getting repositories for organization {o}".format(
            o=orgname))
        res = {}
        for repo in g.get_organization(orgname).get_repos():
            res[repo.name] = repo
            f = " fork of %s/%s" % (
                repo.parent.owner.name, repo.parent.name) if repo.fork else ''
            p = 'private' if repo.private else 'public'
            fc = "; %d forks" % (repo.forks_count) if (
                repo.forks_count > 0) else ''
            logger.debug("Found GitHub Repo: %s (%s%s%s) %s" % (
                repo.name, p, f, fc, repo.html_url))
        return res

def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('repos', type=str, action='store',
                        help='file containing git repository names, one per line')
    parser.add_argument('repo_prefix', type=str, action='store',
                        help='git URL base to prefix to each entry in the repos'
                        ' file')
    parser.add_argument('-u', '--url-prefix', action='store', type=str,
                        dest='repo_html_prefix',
                        help='URL to prefix to repo names to get web view')
    parser.add_argument('-g', '--github-org', action='store', type=str,
                        dest='orgname',
                        help='also clone all repositories from this GitHub org')
    parser.add_argument('-d', '--clone-dir', action='store', type=str,
                        dest='clone_dir', default='.',
                        help='directory to clone repos into')
    parser.add_argument('-F', '--no-fetch', action='store_true', default=False,
                        dest='no_fetch',
                        help='do not fetch existing repos')
    parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                        default=0,
                        help='verbose output. specify twice for debug-level '
                        'output.')
    parser.add_argument('-C', '--cache', dest='cache', action='store_true',
                        default=False,
                        help='cache repository information at ./repocache.json;'
                        ' use this cache if present, otherwise write it')
    parser.add_argument('-s', '--skip', dest='skip', action='append', type=str,
                        default=[],
                        help='repository names to skip')
    parser.add_argument('--skip-tags', dest='skip_tags', action='append',
                        type=str, default=[],
                        help='repository names to not check tags in')
    args = parser.parse_args(argv)
    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    with open(args.repos, 'r') as fh:
        repos = [l.strip() for l in fh.readlines()]
    r = GitRepoReconciler(repos, args.repo_prefix, args.clone_dir,
                          github_orgname=args.orgname,
                          repo_html_prefix=args.repo_html_prefix,
                          skip=args.skip, skip_tags=args.skip_tags)
    r.run(fetch=(not args.no_fetch), cache=args.cache)
