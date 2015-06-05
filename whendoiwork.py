#!/usr/bin/env python
"""
whendoiwork

Script to find all git repositories in a list of local filesystem paths,
iterate over all commits in them (in the last N days), and build a histogram
of the day of week and hour of day of your commits (using information from your
git configuration).

####################################################################################

Requirements (and tested versions):
GitPython (1.0.1)
pytz
tzlocal (1.1.2)
matplotlib (1.4.2)
numpy (1.9.1)

####################################################################################

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

####################################################################################

CHANGELOG:
2015-06-04 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import os
import sys
import argparse
import logging
import subprocess
import datetime
import pytz
import tzlocal
from git import Repo
import matplotlib.pyplot as plt
import numpy as np


FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)


class GitWorkGraph:
    """ might as well use a class. It'll make things easier later. """

    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def __init__(self, repodirs=[], alt_repodirs=[], label='repos', alt_label='alt_repos', verbose=0):
        if verbose:
            logger.setLevel(logging.DEBUG)
        self.repodirs = repodirs
        self.alt_repodirs = alt_repodirs
        self.label = label
        self.alt_label = alt_label

    def run(self, author_name, num_days, tzname):
        """Run everything..."""
        # find git repositories
        logger.info("Only examining commits since {n} days ago".format(n=num_days))
        localtz = pytz.timezone(tzname)
        logger.info("Using local timezone '{l}' ({z})".format(z=localtz.zone, l=tzname))
        repos = []
        for d in self.repodirs:
            res = self.find_git_repos(d)
            logger.debug("Found {c} repos under {d}: {res}".format(c=len(res), d=d, res=res))
            repos.extend(res)
        alt_repos = []
        for d in self.alt_repodirs:
            res = self.find_git_repos(d)
            logger.debug("Found {c} alt-repos under {d}: {res}".format(c=len(res), d=d, res=res))
            alt_repos.extend(res)
        # find relevant commit data in each repo
        repo_data = self.do_repos(repos, author_name, num_days, localtz)
        alt_repo_data = self.do_repos(alt_repos, author_name, num_days, localtz)
        self.plot(repo_data, alt_repo_data, author_name, num_days, localtz)

    def do_repos(self, repolist, author_name, num_days, localtz):
        """
        return a dict of day of week (0=Monday, 6=Sunday) to dict
        of hour of day in UTC to number of commits/authors.
        """
        data = {}
        for x in range(7):
            data[x] = {y: 0 for y in range(24)}
        for repo in repolist:
            commit_dates = self.do_repo(repo, author_name, num_days)
            for dt_utc in commit_dates:
                dt_local = dt_utc.astimezone(localtz)
                data[dt_local.weekday()][dt_local.hour] += 1
        return data

    def do_repo(self, repo_path, author_name, num_days):
        """return a list of the datetimes of your commits in this repo"""
        repo = Repo(repo_path)
        if repo.bare:
            logger.debug("Skipping bare repository at {p}".format(p=repo_path))
            return None
        logger.debug("Checking commits in repository at {p}".format(p=repo_path))
        # GitPython repo.iter_commits() only works on current branch;
        # instead of iterating branches, this gets dangling commits too
        keep_commits = []
        seen_commits = []
        # we filter by author and date here in the `git log` command
        #################################################################################################################
        # @TODO ok, even this isn't getting us ALL the commits. In fact, on my current branch in my sample repo,
        # `git log -g` is showing 45 commits whereas `git log` shows 113...
        # https://groups.google.com/d/topic/git-python/U2uQIZv-iMA/discussion
        #################################################################################################################
        # dangling commits via reflog
        for sha in repo.git.log(walk_reflogs=True, author=author_name, pretty='%H', since='{n} days ago'.format(n=num_days)).split("\n"):
            if sha in seen_commits:
                continue
            c = repo.commit(sha)
            a_dt = datetime.datetime.fromtimestamp(c.authored_date, pytz.UTC)
            keep_commits.append(a_dt)
            seen_commits.append(sha)
        # all refs
        for sha in repo.git.log(all=True, pretty='%H').split("\n"):
            if sha in seen_commits:
                continue
            c = repo.commit(sha)
            a_dt = datetime.datetime.fromtimestamp(c.authored_date, pytz.UTC)
            keep_commits.append(a_dt)
            seen_commits.append(sha)
        # danging or orphaned
        for line in repo.git.fsck().split("\n"):
            parts = line.split(' ')
            if parts[-1] in seen_commits:
                continue
            if not repo.re_hexsha_only.match(parts[-1]):
                continue
            try:
                c = repo.commit(parts[-1])
                a_dt = datetime.datetime.fromtimestamp(c.authored_date, pytz.UTC)
                keep_commits.append(a_dt)
                seen_commits.append(sha)
                print("Checked fsck commit {s}".format(s=parts[-1]))
            except ValueError as ex:
                logger.debug(ex.message)
        logger.debug("Found {l} commits (with specified author name and since cutoff date) in repo.".format(l=len(keep_commits)))
        return keep_commits

    def find_git_repos(self, path):
        """find all direct subdirectories of path that are git repos"""
        repos = []
        for d in next(os.walk(path))[1]:
            p = os.path.join(path, d)
            if os.path.isdir(p) and os.path.isdir(os.path.join(p, '.git')):
                repos.append(p)
        return repos

    def make_plot_data(self, repo_data, alt_repo_data):
        """
        Take the two nested dicts of per-day, per-hour data and convert
        them to a numpy array for plotting.

        First we find the maximum number of commits per hour ever, c_max.

        Each array element is a float from -1 to 1, where 1 is c_max commits
        being done for repo_data repos, and -1 is c_max commits being done
        for alt_repo_data repos, and 0 is no commits.
        """
        # find the most commits per hour
        c_max = 0
        for t in [repo_data, alt_repo_data]:
            for day in t:
                for hour in t[day]:
                    if t[day][hour] > c_max:
                        c_max = t[day][hour]
        c_max = c_max * 1.0
        logger.debug("Max commits per hour: {c}".format(c=c_max))
        data = []
        for hour in range(24):
            d_list = []
            for day in range(7):
                r = repo_data[day][hour] * 1.0
                a = alt_repo_data[day][hour] * 1.0
                r_p = r / c_max
                a_p = a / c_max
                t = r_p - a_p
                d_list.append(t)
            data.append(d_list)
        return data

    def plot(self, repo_data, alt_repo_data, author_name, num_days, localtz):
        """
        Draw the plot
        see:
        * http://www.bertplot.com/visualization/?p=292
        """
        logger.info("Beginning to plot data")
        data = self.make_plot_data(repo_data, alt_repo_data)
        data = np.array(data)
        rows = [str(x) for x in range(24)]
        columns = self.day_names
        # plot the data
        fig,ax=plt.subplots()
        # this uses the "Reds" color map
        #ax.pcolor(data,cmap=plt.cm.Reds,edgecolors='k')
        heatmap = ax.pcolor(data,edgecolors='k', vmin=-1, vmax=1, cmap=plt.cm.bwr)
        # axis ticks
        ax.set_xticks(np.arange(0,7)+0.5)
        ax.set_yticks(np.arange(0,24)+0.5)

        # set sides of plot for ticks
        ax.xaxis.tick_bottom()
        ax.yaxis.tick_left()
        # set tick labels
        ax.set_xticklabels(columns,minor=False,fontsize=16)
        ax.set_yticklabels(rows,minor=False,fontsize=16)
        # legend
        cb = fig.colorbar(heatmap, ticks=[-1, 0, 1], spacing='uniform')
        cb.set_ticklabels([self.alt_label, 'None', self.label])

        # Here we use a text command instead of the title
        # to avoid collision between the x-axis tick labels
        # and the normal title position
        plt.text(0.5,1.08,'Commits by {a} - last {n} days'.format(a=author_name, n=num_days),
                          fontsize=22,
                          horizontalalignment='center',
                          transform=ax.transAxes
                          )

        # standard axis elements
        plt.ylabel('Hour of Day ({z})'.format(z=localtz.zone),fontsize=20)
        plt.xlabel('Day of Week',fontsize=20)
        # write file
        fname = 'plot.png'
        plt.savefig(fname)
        fpath = os.path.abspath(fname)
        logger.info("Plot saved to {f} <file://{a}>".format(f=fname, a=fpath))


def get_git_user_name():
    """
    GitPython still (1.0.1) seems to lack a nice way to get this
    """
    cmd = ['git', 'config', '--get', 'user.name']
    try:
        res = subprocess.check_output(cmd)
        return res.strip()
    except subprocess.CalledProcessError:
        logger.warning("Unable to execute {c}".format(c=' '.join(cmd)))
    return ''

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output. specify twice for debug-level output.')
    p.add_argument('-r', '--repodir', dest='repodirs', action='append',
                   help='directory to search for git repositories (non-recursive); '
                   'can be specified multiple times', default=[])
    p.add_argument('-a', '--alt-repodir', dest='alt_repodirs', action='append',
                   help='like -r/--repodir, but graph in alternate color', default=[])
    p.add_argument('--repolabel', action='store', help='repo label/legend', default='repos')
    p.add_argument('--alt-repolabel', action='store', help='alt repo label/legend', default='alt-repos')
    cn = get_git_user_name()
    p.add_argument('--author-name', action='store', type=str, default=cn,
                   help='author name to search for (argument to git log --author=); default: "{cn}"'.format(cn=cn))
    p.add_argument('-d', '--days', action='store', type=int, default=365,
                   help='number of days of history to search; default 365')
    p.add_argument('-t', '--timezone', action='store', type=str, default='UTC',
                   help='timezone to show commits in, as a string passed to pytz.timezone() (default: UTC)')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    script = GitWorkGraph(
        verbose=args.verbose,
        repodirs=args.repodirs,
        alt_repodirs=args.alt_repodirs,
        label=args.repolabel,
        alt_label=args.alt_repolabel,
    )
    script.run(args.author_name, args.days, args.timezone)
