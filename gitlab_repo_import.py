#!/usr/bin/env python
"""
gitlab_repo_import.py
=====================

Helper to import an existing bare git repo into GitLab.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/gitlab_repo_import.py>

Usage
-----

1. Export your GitLab Private API token as GITLAB_TOKEN, or you will be prompted
   for it interactively.
2. Run the script:

    gitlab_repo_import.py [options] repo_path [repo_path ...]

Requirements
-------------

python-gitlab (tested with 0.9.2; `pip install python-gitlab`)

Written for python2.7

Copyright and License
----------------------

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

Changelog
----------

2015-07-21 Jason Antman <jason@jasonantman.com>:
  - add remove_on_fail option to remove destination directory if copy fails
  - add ignore_broken_links option to ignore broken symlinks when copying repo
  - wrap repo copy operation in try/except

2015-07-16 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import re
import os
import subprocess
import json
import shutil
import pwd

import gitlab

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)

# suppress requests internal logging
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True

# mapping of our CLI arguments to gitlab.Project attribute names
BOOLEAN_SETTING_NAMES = {
    'issues': 'issues_enabled',
    'merge_requests': 'merge_requests_enabled',
    'wiki': 'wiki_enabled',
    'snippets': 'snippets_enabled',
}

# per https://github.com/gitlabhq/gitlabhq/blob/master/doc/api/projects.md
VISIBILITY_LEVELS = {
    'private': 0,
    'internal': 10,
    'public': 20,
}

def ignore_broken_links_callback(dirname, items):
    skip = []
    for item in items:
        path = os.path.join(dirname, item)
        if not os.path.exists(path):
            logger.warning("Skipping broken link: %s", path)
            skip.append(item)
    return skip


class GitLabRepoImport:
    """Helper to import an existing bare git repo into GitLab."""

    git_user = 'git'

    def __init__(self, url, apikey, gitlab_ctl_path, repos_dir=None,
                 remove_on_fail=False, ignore_broken_links=False):
        """connect to GitLab"""
        self.remove_on_fail = remove_on_fail
        self.ignore_broken_links = ignore_broken_links
        logger.debug("Connecting to GitLab")
        self.conn = gitlab.Gitlab(url, apikey)
        self.conn.auth()
        logger.info("Connected to GitLab as %s",
                    self.conn.user.username)
        if repos_dir is not None:
            self.repos_dir = repos_dir
        else:
            self.repos_dir = self._get_repo_dir(gitlab_ctl_path)

    def run(self, group_name, repo_paths, project_settings, migrate_hooks):
        """
        main entry point

        For information on project_settings, see update_project_settings()
        """
        logger.info("Importing repos under group '%s'", group_name)
        create_path = os.path.join(self.repos_dir, group_name)
        if not os.path.exists(create_path):
            logger.error("Error: group does not yet exist (path %s does not "
                         "exist", create_path)
            raise SystemExit(1)
        failed = 0
        succeeded = 0
        for repo in repo_paths:
            if not os.path.exists(repo):
                logger.error("Error: repo path does not exist: %s", repo)
                continue
            if self.do_repo(
                    create_path, repo, group_name, project_settings,
                    migrate_hooks
            ):
                succeeded += 1
            else:
                failed += 1
        logger.info("Done with all repos; imported %d, %d failed.",
                    succeeded, failed)
        if failed > 0:
            raise SystemExit(1)

    def do_repo(self, create_path, repo_path, group_name, project_settings,
                migrate_hooks):
        """import one repo"""
        repo_name = os.path.basename(repo_path)
        if not repo_name.endswith('.git'):
            project_name = repo_name
            repo_name += '.git'
        else:
            project_name = re.sub('\.git$', '', repo_name)
        dest_path = os.path.join(create_path, repo_name)
        if os.path.exists(dest_path):
            logger.error("Error: path already exists: %s", dest_path)
            return False
        logger.info("Copying %s to %s", repo_path, dest_path)
        try:
            ignore_cb = None
            if self.ignore_broken_links:
                ignore_cb = ignore_broken_links_callback
            shutil.copytree(repo_path, dest_path, ignore=ignore_cb)
            logger.debug("Done copying")
            tmp = pwd.getpwnam(self.git_user)
            git_uid = tmp.pw_uid
            git_gid = tmp.pw_gid
            logger.info("Recursively setting ownership on %s to %d:%d",
                        dest_path, git_uid, git_gid)
            # from http://stackoverflow.com/a/2853934/211734
            os.chown(dest_path, git_uid, git_gid)
            for root, dirs, files in os.walk(dest_path):
                for momo in dirs:
                    os.chown(os.path.join(root, momo), git_uid, git_gid)
                for momo in files:
                    os.chown(os.path.join(root, momo), git_uid, git_gid)
            logger.debug("Done chown'ing")
            if migrate_hooks:
                hook_dir = os.path.join(dest_path, 'hooks')
                new_dir = os.path.join(dest_path, 'custom_hooks')
                if os.path.exists(hook_dir):
                    logger.info("Migrating hooks - moving %s to %s",
                                hook_dir,
                                new_dir)
                    shutil.move(hook_dir, new_dir)
                    logger.debug("Done migrating hooks")
        except Exception as ex:
            logger.exception("Exception when copying repo")
            if self.remove_on_fail and os.path.exists(dest_path):
                logger.warning("Removing %s", dest_path)
                shutil.rmtree(dest_path)
            return
        if not self.import_repo():
            return False
        proj = self.get_gitlab_project(group_name, project_name)
        if proj is None:
            logger.error("Error: import command exited successfully, but could "
                         "not find project %s/%s via API.",
                         group_name,
                         project_name)
            return False
        commits = proj.Commit()
        if len(commits) < 1:
            logger.warning("Warning: project %s created, but has no commits.",
                           proj.path_with_namespace)
        else:
            logger.info("Created project with at least %d commits", len(commits))
        self.update_project_settings(project_settings, proj)
        return True

    def get_gitlab_project(self, namespace, project_name):
        """get the Project object for the specified project, or None if not found"""
        for p in self.conn.Project():
            if p.name == project_name and p.namespace.name == namespace:
                return p
        return None

    def import_repo(self):
        """do the actual GitLab import"""
        cmd = [
            'gitlab-rake',
            '-v',
            'gitlab:import:repos',
            'RAILS_ENV=production'
        ]
        try:
            logger.info("Running: %s", ' '.join(cmd))
            res = subprocess.check_output(cmd)
        except subprocess.CalledProcessError as ex:
            logger.error("Import failed (exit %d):\n%s", ex.returncode, ex.output)
            return False
        logger.debug("Imported repo:\n%s", res)
        return True

    def update_project_settings(self, project_settings, project):
        """
        Update the settings on a project.

        project_settings is a dict of settings to update on the created project;
        keys: 'visibility', 'issues', 'merge_requests', 'wiki', 'snippets'
        values:
          - if key is missing or value is None, do nothing
          - if 'visibility' is one of private|internal|public, set visibility
              to that level
          - if the other keys are True or False, enable or disable that feature
        """
        logger.info("Updating project settings on %s", project.path_with_namespace)
        changes = False
        for setting, value in project_settings.items():
            if setting == 'visibility':
                current = getattr(project, 'visibility_level')
                value = VISIBILITY_LEVELS[value]
                if current == value:
                    logger.debug("visibility already at desired value: %s", value)
                    continue
                logger.debug("Setting visibility_level to %s (current=%s)",
                             value,
                             current)
                setattr(project, 'visibility_level', value)
                changes = True
            elif setting in BOOLEAN_SETTING_NAMES and value is not None:
                attr_name = BOOLEAN_SETTING_NAMES[setting]
                current = getattr(project, attr_name)
                if current == value:
                    logger.debug("%s already at desired value: %s", setting, value)
                    continue
                logger.debug("Setting %s to %s (current=%s)", setting, value,
                             current)
                setattr(project, attr_name, value)
                changes = True
        if not changes:
            logger.info("No changes to project settings.")
            return
        logger.debug("Saving project")
        try:
            res = project.save()
        except Exception as ex:
            logger.exception("Saving project failed: ", ex)
            return
        logger.info("Settings updated for project %s", project.path_with_namespace)

    def _get_repo_dir(self, gitlab_ctl_path):
        """use gitlab-ctl to get the absolute path to git gitlab_shell repo dir"""
        cmd = [gitlab_ctl_path, 'show-config']
        logger.info("Running %s to get gitlab configuration", ' '.join(cmd))
        res = subprocess.check_output(cmd)
        logger.debug("gitlab-ctl done")
        try:
            conf = json.loads(res)
        except:
            logger.error("Unable to read JSON output from %s", ' '.join(cmd))
            raise SystemExit(1)
        try:
            path = conf['gitlab']['gitlab-rails']['gitlab_shell_repos_path']
            logger.info("Found repos path from config as: %s", path)
        except KeyError:
            path = '/var/opt/gitlab/git-data/repositories'
            logger.warning("Could not find gitlab_shell_repos_path in config, "
                           "using default of: %s", path)
        return path


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(description='Helper to import an existing bare '
                                'git repo into GitLab.')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False,
                   help='verbose output')
    DEFAULT_URL = 'http://127.0.0.1'
    p.add_argument('-u', '--gitlab_url', action='store', dest='gitlab_url',
                   default=DEFAULT_URL,
                   help='URL to GitLab instance (default: %s)' % DEFAULT_URL)
    p.add_argument('-g', '--group', action='store', dest='group',
                   required=True,
                   help='Group name to import projects under')
    p.add_argument('--gitlab-ctl', action='store', dest='gitlab_ctl',
                   default='/bin/gitlab-ctl',
                   help='specify path to gitlab-ctl other than /bin/gitlab-ctl')
    p.add_argument('--repos-dir', action='store', dest='repos_dir', default=None,
                   help="path to gitlab_shell's repositories directory, in "
                   "gitlab configuration as gitlab_shell_repos_path; if not "
                   "specified, will be queried using 'gitlab-ctl show-config'")
    p.add_argument('--no-migrate-hooks', action='store_false',
                   dest='migrate_hooks', default=True,
                   help="if specified, do not automatically rename the source "
                   "repo's 'hooks' directory to 'custom_hooks' before import")
    p.add_argument('--remove-on-fail', action='store_true', default=False,
                   dest='remove_on_fail',
                   help="remove destination directory if copy or import fails")
    p.add_argument('--ignore-broken-links', action='store_true', default=False,
                   dest='ignore_broken_links',
                   help='ignore any broken links in source repo when copying to'
                   ' GitLab destination')

    # project settings
    p.add_argument('--visibility', action='store', dest='visibility',
                   default=None,
                   choices=['private', 'internal', 'public'],
                   help='Set visibility of new projects to this value (private|'
                   'internal|public); default is to leave as-is')
    for name in BOOLEAN_SETTING_NAMES:
        g = p.add_mutually_exclusive_group()
        g.add_argument('--enable-%s' % name, action='store_true',
                       dest=name,
                       help='enable %s for project, regardless of GitLab '
                       'default' % name)
        g.add_argument('--disable-%s' % name, action='store_true',
                       dest='no_%s' % name,
                       help='disable %s for project, regardless of GitLab '
                       'default' % name)

    # paths
    p.add_argument('repo_path', action='store', type=str, nargs='+',
                   help='Local filesystem path to repo to import; may be '
                   'specified multiple times.')


    args = p.parse_args(argv)

    # project_settings
    args.settings = {}
    args.settings['visibility'] = args.visibility
    for name in BOOLEAN_SETTING_NAMES:
        if hasattr(args, name) and getattr(args, name) is True:
            args.settings[name] = True
        elif hasattr(args, 'no_%s' % name) and getattr(args, 'no_%s' % name) is True:
            args.settings[name] = False
        else:
            args.settings[name] = None

    return args

def get_api_key():
    if 'GITLAB_TOKEN' in os.environ:
        return os.environ['GITLAB_TOKEN']
    return raw_input("Enter your GitLab Private API token: ")

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    syncer = GitLabRepoImport(
        args.gitlab_url,
        get_api_key(),
        args.gitlab_ctl,
        repos_dir=args.repos_dir,
        remove_on_fail=args.remove_on_fail,
        ignore_broken_links=args.ignore_broken_links,
    )
    syncer.run(args.group, args.repo_path, args.settings, args.migrate_hooks)
