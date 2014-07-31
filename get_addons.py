#!/usr/bin/env python
"""
Update my WoW addons on mac
"""

import sys
import os
import optparse
import logging
import requests
import re
import semantic_version
import contextlib
import tempfile
import shutil
import zipfile
import traceback
from lxml import etree
from io import BytesIO
import HTMLParser

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


class Addongetter:


    def __init__(self, dry_run=False, keep_temp=False):
        self.dry_run = dry_run
        self.addon_dir = self.find_addon_dir()
        self.backup_dir = self.backup_dir_path(self.addon_dir)
        if not os.path.exists(self.backup_dir):
            logger.info("creating addon backup directory: {b}".format(b=self.backup_dir))
            os.mkdir(self.backup_dir)
        self.keep_temp = keep_temp

    def find_addon_dir(self):
        """ find my addon directory """
        if sys.platform == 'darwin':
            return '/Volumes/disk0s7/WoW/World of Warcraft/Interface/AddOns'
        elif sys.platform == 'linux2':
            return os.path.expanduser('~/WoW/Interface/Addons')
        raise Exception("unable to find_addon_dir() on platform {p}".format(p=sys.platform))

    def backup_dir_path(self, addon_dir):
        """ get the backup directory path """
        p = os.path.abspath(os.path.join(addon_dir, '..', 'Addon_Backups'))
        return p

    def run(self):
        """ run it """
        failed = 0
        updated = 0
        total = 0

        res = self.do_elvui()
        if res is False:
            failed = 1
        elif res == 1:
            updated = 1
        total = 1

        for dirname in [ name for name in os.listdir(self.addon_dir) if os.path.isdir(os.path.join(self.addon_dir, name)) ]:
            if dirname.startswith('Blizzard_'):
                logger.debug("ignoring directory: {d}".format(d=dirname))
                continue
            res = self.update_addon(dirname)
            if res is False:
                failed += 1
            elif res == 1:
                updated += 1
            if res != 2:
                total += 1

        # other, generic addons
        logger.warning("Checked {t} modules; updated {u}; {f} failed".format(t=total, u=updated, f=failed))
        return True

    def update_addon(self, dirname):
        """
        given a dirname in addon_dir, update that addon
        returns: False on failure
                 True on nothing to do
                 2 on skipped
                 1 on updated
        """
        addon_name = self.addon_name_from_dirname(dirname)
        if addon_name is False:
            logger.debug("got addon_name for {d} as False, skipping".format(d=dirname))
            return 2
        logger.info("beginning update for {a} (directory {d})".format(a=addon_name, d=dirname))
        res = self.get_latest_from_curseforge(addon_name)
        if res is False:
            logger.warning("unable to find addon on curseforge: {a}".format(a=addon_name))
            return False
        latest, url = res
        logger.debug("addon {a} got latest version as {l} url {u}".format(a=addon_name, l=latest, u=url))
        return True

    def get_latest_from_curseforge(self, name):
        """
        given an addon name, attempt to get the latest version and its
        download URL from curseforge
        return a tuple of (semver, string url) or False on failure to determine version
        """
        pageurl = 'http://wow.curseforge.com/addons/{name}/files/'.format(name=name)
        logger.debug("getting curseforge addon files list: {url}".format(url=pageurl))
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:28.0) Gecko/20100101 Firefox/28.0'}
        r = requests.get(pageurl, stream=True, headers=headers)
        if r.status_code != 200:
            logger.debug("got status code {s} back for page {p}".format(s=r.status_code, p=pageurl))
            return False
        try:
            parser = etree.HTMLParser()
            root = etree.parse(BytesIO(r.content), parser)
            logger.debug("parsed with lxml etree")
        except Exception as e:
            #ex_type, ex, tb = sys.exc_info()
            #tb_str = ''.join(traceback.format_stack(tb))
            tb_str = traceback.format_exc()
            logger.warning("exception parsing curseforge page:\n{e}: {t}".format(e=e, t=tb_str))
            return False
        tables = root.xpath("//table[@class='listing']")
        if len(tables) < 1:
            logger.warning("found no matching tables on page")
            print(etree.tostring(root))
            return False
        for t in tables:
            print("table:\n{t}".format(t=t))
            print(etree.tostring(t))
        raise SystemExit("debugging")

    def addon_name_from_dirname(self, dirname):
        """ from the addon dir name, get the name of the addon """
        # if we need to explicitly skip anything, do it here
        if dirname.startswith('DataStore'):
            return False
        if dirname.startswith('Altoholic_'):
            return False
        n = dirname.lower()
        return n

    @contextlib.contextmanager
    def use_temp_directory(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        if not self.keep_temp:
            shutil.rmtree(temp_dir)

    def do_elvui(self):
        """ update elvui """
        newest = self.elvui_newest_version()
        if newest is None:
            return False
        logger.debug("got newest elvui version as: '{v}'".format(v=newest))
        current = self.elvui_current_version()
        if current is None:
            return False
        if current > newest:
            logger.error("got current elvui version as {c} greater than newest version {n}".format(c=current, n=newest))
            return False
        elif current == newest:
            logger.info("ElvUI version {c} is current/latest; nothing to update.".format(c=current))
            return True
        # else we need to update
        logger.info("ElvUI version is {c} but newest is {n}; updating...".format(c=current, n=newest))
        url = self.elvui_download_url(newest)
        logger.debug("got download url as: {url}".format(url=url))
        return self.update_elvui(url)

    def requests_get_binary(self, url, filename):
        """ use requests to download a binary file; returns True or False """
        chunk_size = 524288
        logger.debug("downloading binary {url} to {filename} with chunk size {c}".format(url=url, filename=filename, c=chunk_size))
        r = requests.get(url, stream=True)
        with open(filename, 'wb') as fd:
            for chunk in r.iter_content(chunk_size):
                fd.write(chunk)
        if not os.path.exists(filename):
            logger.error("downloaded file does not exist: {f}".format(f=filename))
            return False
        if os.stat(filename).st_size < 100:
            logger.error("downloaded file is less than 100b: {f}".format(f=filename))
            return False
        logger.debug("ok, successfully downloaded file")
        return True

    def update_elvui(self, zip_url):
        """ update ElvUI with the zip file from zip_url """
        with self.use_temp_directory() as temp_dir:
            zippath = os.path.join(temp_dir, 'elvui.zip')
            extracted = os.path.join(temp_dir, 'extracted')
            logger.info("downloading elvui zip to: {z}".format(z=zippath))
            res = self.requests_get_binary(zip_url, zippath)
            if not res:
                return False
            os.mkdir(extracted)
            logger.debug("opening zip file")
            with zipfile.ZipFile(zippath, 'r') as zfile:
                logger.debug("extracting zip file")
                zfile.extractall(extracted)
            logger.info("extracted elvui to {e}".format(e=extracted))
            dirs = [ name for name in os.listdir(extracted) if os.path.isdir(os.path.join(extracted, name)) ]
            for dirname in dirs:
                self.backup_and_install(extracted, dirname)
            logger.info("Updated ElvUI")
        return True

    def backup_and_install(self, src_dir, dirname):
        """
        install an addon directory, first backing up the old one if it exists
        @param the directory containing the dirname addon directory
        @param dirname the name of the addon directory (will be moved)
        """
        addonpath = os.path.join(self.addon_dir, dirname)
        newdir = os.path.join(src_dir, dirname)
        backupdir = os.path.join(self.backup_dir, dirname)
        if os.path.exists(backupdir):
            if self.dry_run:
                logger.warning("DRY RUN: would remove {d}".format(d=backupdir))
            else:
                logger.info("deleting old backup {d}".format(d=backupdir))
                shutil.rmtree(backupdir)
        if os.path.exists(addonpath):
            if self.dry_run:
                logger.warning("DRY RUN: would move {n} to {d}".format(n=addonpath, d=backupdir))
            else:
                logger.info("backing up {n} to {d}".format(n=addonpath, d=backupdir))
                shutil.move(addonpath, backupdir)
        if self.dry_run:
            logger.warning("DRY_RUN: would move {s} to {a}".format(s=newdir, a=addonpath))
        else:
            logger.info("moving {s} to {a}".format(s=newdir, a=addonpath))
            shutil.move(newdir, addonpath)
        return True

    def elvui_download_url(self, semver):
        """ make an elvui download URL for a semver version """
        vs = semver.__str__()
        url = 'http://www.tukui.org/downloads/elvui-{vs}.zip'.format(vs=vs)
        return url

    def elvui_current_version(self):
        """ find the currently installed elvui version """
        version_re = re.compile(r'^## Version: ([0-9\.]+)')
        tocpath = os.path.join(self.addon_dir, 'ElvUI', 'ElvUI.toc')
        if not os.path.exists(tocpath):
            logger.error("could not find elvui TOC at {p}".format(p=tocpath))
            return False
        with open(tocpath, 'r') as fh:
            for line in fh:
                m = version_re.match(line)
                if m:
                    ver = m.group(1)
                    logger.debug("found version as {m} from line: {l}".format(m=ver, l=line.strip()))
                    break
        if ver is None:
            logger.error("could not find current elvui version; please check code or install it")
            return False
        semver = semantic_version.Version(ver, partial=True)
        return semver

    def elvui_newest_version(self):
        """ find the newest elvui version """
        url = 'http://www.tukui.org/changelog.php?ui=elvui'
        version_re = re.compile(r'<u><b>Version ([0-9\.]+) ')
        logger.debug("getting {u} to check newest version".format(u=url))
        r = requests.get(url)
        if r.status_code != 200:
            logger.error("got status code {s} for url {u} - can't get ElvUi latest version number".format(s=r.status_code, u=url))
            return False
        ver = None
        for line in r.text.encode('utf-8').split("\n"):
            m = version_re.match(line)
            if m:
                ver = m.group(1)
                logger.debug("found version as {m} from line: {l}".format(m=ver, l=line.strip()))
                break
        if ver is None:
            logger.error("could not find latest elvui version; please check code")
            return False
        semver = semantic_version.Version(ver, partial=True)
        return semver


def parse_args(argv):
    """ parse arguments/options """
    p = optparse.OptionParser()

    p.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                      help='dry-run - dont actually send metrics')

    p.add_option('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')

    p.add_option('-k', '--keep-temp', dest='keep_temp', action='store_true', default=False,
                 help='keep temporary directories')

    options, args = p.parse_args(argv)

    return options


if __name__ == "__main__":
    opts = parse_args(sys.argv[1:])

    if opts.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif opts.verbose > 0:
        logger.setLevel(logging.INFO)

    klass = Addongetter(dry_run=opts.dry_run, keep_temp=opts.keep_temp)
    klass.run()
