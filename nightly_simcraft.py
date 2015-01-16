#!/usr/bin/env python
"""
Python 2.7/3 wrapper script to do a nightly (cron'ed) run of
[SimulationCraft](http://simulationcraft.org/) when your gear
changes, and email you results. Configurable for any number of
characters, and any number of destination email addresses.

What It Does
-------------

For each character defined in the configuration file:

- uses [battlenet](https://pypi.python.org/pypi/battlenet/0.2.6) to check your
  character's gear, and cache it locally (under `~/.nightly_simcraft/`). If your
  gear has not changed since the last run, skip the character.
- Generate a new `.simc` file for the character, using current armory information
  and any options you specified.

Requirements
-------------

* battlenet>=0.2.6
* dictdiffer>=0.3.0

You can install these like:

`pip install battlenet>=0.2.6`

Configuration
--------------

`~/.nightly_simcraft/settings.py` is just Python code that will be imported by
this script. If it doesn't already exist when this script runs, the script
will exit telling you about an option to create an example config.

By default, this uses SimulationCraft's default settings for your character
(i.e. what you get when you do an Armory import, in either the command line
or GUI interfaces). If you need further customization.... TBD.

The simc file used for each character, as well as the final output, will be
cached on disk.

If simc isn't installed at /usr/bin/simc on your system, set the path in the
configuration file.

Copyright
----------

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The canonical, current version of this script will always be available at:
<https://github.com/jantman/misc-scripts/blob/master/nightly_simcraft.py>

Changelog
----------

2015-01-09 Jason Antman <jason@jasonantman.com> v0.0.1:
  - initial version of script
"""

import sys
import os
import argparse
import logging
import subprocess
import datetime
from textwrap import dedent
from copy import deepcopy
try:
    import cPickle as pickle
except ImportError:
    import pickle
import platform
import getpass
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

if sys.version_info[0] > 3 or ( sys.version_info[0] == 3 and sys.version_info[1] >= 3):
    import importlib.machinery
else:
    import imp

from dictdiffer import diff
import battlenet

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


DEFAULT_CONFDIR = '~/.nightly_simcraft'


class NightlySimcraft:
    """ might as well use a class. It'll make things easier later. """

    VERSION = '0.0.1'
    
    SAMPLE_CONF = """
    ###############################################################
    # example nightly_simcraft.py configuration file
    # all file paths are relative to this file
    ###############################################################
    # this is evaluated as ptrhon, so you can do whatever you want
    # as long as these variables end up being set
    ###############################################################
    SIMC_PATH = '/usr/bin/simc'
    CHARACTERS = [
      {
        'realm': 'realname',
        'name': 'character_name',
        'email': 'you@domain.com',
      },
      {
        'realm': 'realname',
        'name': 'character_name',
        'email': ['you@domain.com', 'someone@domain.com'],
      },
    ]
    # set these to strings to send email via GMail; otherwise
    # email will be sent via local SMTP.
    # It's highly recommended that you set an application-specific
    # password for this.
    GMAIL_USERNAME = None
    GMAIL_PASSWORD = None
    """
    
    def __init__(self, confdir=DEFAULT_CONFDIR, logger=None, dry_run=False, verbose=0):
        """ init method, run at class creation """
        # setup a logger; allow an existing one to be passed in to use
        self.logger = logger
        if logger is None:
            self.logger = logging.getLogger(self.__class__.__name__)
        if verbose > 1:
            self.logger.setLevel(logging.DEBUG)
        elif verbose > 0:
            self.logger.setLevel(logging.INFO)
        self.dry_run = dry_run
        self.confdir = os.path.abspath(os.path.expanduser(confdir))
        self.read_config(confdir)
        self.logger.debug("connecting to BattleNet API")
        self.bnet = battlenet.Connection()
        self.logger.debug("connected")
        self.logger.debug("loading character cache")
        self.character_cache = self.load_character_cache()

    def load_character_cache(self):
        pklpath = os.path.join(self.confdir, 'characters.pkl')
        if not os.path.exists(pklpath):
            return {}
        data = pickle.load(open(pklpath, 'rb'))
        return data

    def write_character_cache(self):
        pklpath = os.path.join(self.confdir, 'characters.pkl')
        with open(pklpath, 'wb') as fh:
            pickle.dump(self.character_cache, fh)

    def read_config(self, confdir):
        """ read in config file """
        confpath = os.path.abspath(os.path.expanduser(os.path.join(confdir, 'settings.py')))
        self.logger.debug("Reading configuration from: {c}".format(c=confpath))
        if not os.path.exists(confpath):
            self.logger.error("ERROR - configuration file does not exist. Please run with --genconfig to generate an example one.")
            raise SystemExit(1)
        self.import_from_path(confpath)
        self.validate_config()
        self.logger.debug("Imported settings for {n} characters".format(n=len(self.settings.CHARACTERS)))

    def validate_config(self):
        # validate config
        if not hasattr(self.settings, 'CHARACTERS'):
            self.logger.error("ERROR: Settings file must define CHARACTERS list")
            raise SystemExit(1)
        if type(self.settings.CHARACTERS) != type([]):
            self.logger.error("ERROR: Settings file must define CHARACTERS list")
            raise SystemExit(1)
        if len(self.settings.CHARACTERS) < 1:
            self.logger.error("ERROR: Settings file must define CHARACTERS list with at least one character")
            raise SystemExit(1)
        # end validate config
        
    def import_from_path(self, confpath):
        """ import a module from a given filesystem path """
        if sys.version_info[0] > 3 or ( sys.version_info[0] == 3 and sys.version_info[1] >= 3):
            # py3.3+
            self.logger.debug("importing {c} - py33+".format(c=confpath))
            loader = importlib.machinery.SourceFileLoader('settings', confpath)
            self.settings = loader.load_module()
        else:
            self.logger.debug("importing {c} - <py33".format(c=confpath))
            self.settings = imp.load_source('settings', confpath)
        self.logger.debug("imported settings module")

    @staticmethod
    def gen_config(confdir):
        dname = os.path.abspath(os.path.expanduser(confdir))
        confpath = os.path.join(dname, 'settings.py')
        if not os.path.exists(dname):
            os.mkdir(dname)
        conf = dedent(NightlySimcraft.SAMPLE_CONF)
        with open(confpath, 'w') as fh:
            fh.write(conf)

    def validate_character(self, char):
        if type(char) != type({}):
            self.logger.debug("Character is not a dict")
            return False
        if 'realm' not in char:
            self.logger.debug("'realm' not in char dict")
            return False
        if 'name' not in char:
            self.logger.debug("'name' not in char dict")
            return False
        return True
            
    def run(self):
        """ do stuff here """
        for char in self.settings.CHARACTERS:
            cname = self.make_character_name(char['name'], char['realm'])
            self.logger.debug("Doing character: {c}".format(c=cname))
            if not self.validate_character(char):
                self.logger.warning("Character configuration not valid, skipping: {c}".format(c=cname))
                continue
            bnet_info = self.get_battlenet(char['realm'], char['name'])
            if bnet_info is None:
                self.logger.warning("Character {c} not found on battlenet; skipping.".format(c=cname))
                continue
            changes = self.character_has_changes(cname, bnet_info)
            if changes is not None:
                self.do_character(cname, char, changes)
            else:
                self.logger.info("Character {c} has no changes, skipping.".format(c=cname))
        self.logger.info("Done with all characters.")

    def make_character_name(self, name, realm):
        realm = realm.replace(' ', '')
        return '{n}@{r}'.format(n=name, r=realm)

    def character_has_changes(self, c_name_realm, c_bnet):
        """
        Test if a chracter has changed since the last run.
        If it does not have changes, return None.
        If it does have changes, return a string human-readable representation
        of those changes.

        :param c_name_realm: name@realm character identifier
        :type c_name_realm: string
        :param c_bnet: BattleNet data for this character
        :type c_bnet: battlenet.things.Character
        :rtype: None or String
        """
        if c_name_realm not in self.character_cache:
            self.logger.debug("character not in cache: {c}".format(c=c_name_realm))
            return "Character not in cache (has not been seen before)."
        c_old = self.character_cache[c_name_realm]
        if c_old == c_bnet:
            self.logger.debug("character identical in cache and battlenet: {c}".format(c=c_name_realm))
            return None
        # else they're different
        self.logger.debug("character has differences between cache and battlenet: {c}".format(c=c_name_realm))
        return self.character_diff(c_old, c_bnet)

    def character_diff(self, old, new):
        """
        Diff two character dicts; return a human-readable representation

        :param old: old (cache) character dict
        :type old: dict
        :param new: new (battlenet) character dict
        :type new: dict
        :rtype: string
        """
        d = diff(old, new)
        s = ''
        for x in list(d):
            if x[0] == 'change':
                s += 'change {item} from {a} to {b}\n'.format(typ=x[0],
                                                            item=x[1],
                                                            a=x[2][0],
                                                            b=x[2][1])
            elif x[0] == 'remove':
                s += 'remove {a} {b}\n'.format(a=x[1], b=x[2])
            else:
                s += 'add {a} {b}\n'.format(a=x[1], b=x[2])
        s = s.strip()
        return s
    
    def do_character(self, c_name, c_settings, c_diff):
        """
        Do the actual simc run for this character

        :param c_name: character name in name@realm format
        :type c_name: string
        :param c_settings: the dict for this character from settings.py
        :type c_settings: dict
        :param c_diff: the textual diff of character changes that caused this run
        :type c_diff: string
        """
        if not os.path.exists(self.settings.SIMC_PATH):
            self.logger.error("ERROR: simc path {p} does not exist".format(p=self.settings.SIMC_PATH))
            return
        simc_file = os.path.join(self.confdir, '{c}.simc'.format(c=c_name))
        html_file = os.path.join(self.confdir, '{c}.html'.format(c=c_name))
        with open(simc_file, 'w') as fh:
            fh.write('"armory=us,{realm},{char}"\n'.format(realm=c_settings['realm'],
                                                           char=c_settings['name']))
            fh.write("calculate_scale_factors=1\n")
            fh.write("html={cn}.html".format(cn=c_name))
        os.chdir(self.confdir)
        self.logger.debug("Running: {p} {f}".format(p=self.settings.SIMC_PATH, f=simc_file))
        start = self.now()
        try:
            res = subprocess.check_output([self.settings.SIMC_PATH,
                                           simc_file],
                                          stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as er:
            self.logger.error("Error running simc!")
            self.logger.exception(er)
            return
        end = self.now()
        if not os.path.exists(html_file):
            self.logger.error("ERROR: simc finished but HTML file not found on disk.")
            return
        self.logger.debug("Ran simc, generated {h} in {d}".format(h=html_file, d=(end - start)))
        self.send_char_email(c_name,
                             c_settings,
                             c_diff,
                             html_file,
                             (end - start),
                             res)

    def send_char_email(self, c_name, c_settings, c_diff, html_path, duration, output):
        """
        Send emails about the simc run

        :param c_name: character name in name@realm format
        :type c_name: string
        :param c_settings: the dict for this character from settings.py
        :type c_settings: dict
        :param c_diff: the textual diff of character changes that caused this run
        :type c_diff: string
        :param html_path: path to the simc HTML output
        :type html_path: string
        :param duration: duration of simc run
        :type duration: datetime.timedelta
        :param output: output from simc command
        :type output: string
        """
        emails = c_settings['email']
        if type(emails) == type(""):
            emails = [emails]
        from_addr = getpass.getuser() + '@' + platform.node()
        subj = 'SimulationCraft output for {c}'.format(c=c_name)
        for dest_addr in emails:
            self.logger.info("Sending email for character {c} to {e}".format(c=c_name, e=dest_addr))
            if self.dry_run:
                self.logger.warning("DRY RUN - not actually sending email")
                continue
            msg = self.format_message(from_addr, dest_addr, subj, c_name, c_diff, html_path, duration, output)
            if hasattr(self.settings, 'GMAIL_USERNAME') and self.settings.GMAIL_USERNAME is not None:
                self.send_gmail(from_addr, dest_addr, msg.as_string())
            else:
                self.send_local(from_addr, dest_addr, msg.as_string())
        self.logger.debug("done sending emails for {cname}".format(cname=c_name))

    def format_message(self, from_addr, dest_addr, subj, c_name, c_diff, html_path, duration, output):
        body = 'SimulationCraft was run for {c} due to the following changes:\n'.format(c=c_name)
        body += '\n' + c_diff + '\n\n'
        body += 'The run was completed in {d} and the HTML report is attached.\n\n'.format(d=duration)
        body += 'SimulationCraft output: \n\n{o}\n\n'.format(o=output)
        footer = 'This run was done on {h} at {t} by nightly_simcraft.py v{v}'
        body += footer.format(h=platform.node(),
                              t=self.now(),
                              v=self.VERSION)
        msg = MIMEMultipart()
        msg['Subject'] = subj
        msg['From'] = from_addr
        msg['To'] = dest_addr
        msg.preamble = body
        with open(html_path, 'r') as fh:
            html = fh.read()
        html_att = MIMEText(html, 'html', 'utf-8')
        msg.attach(html_att)
        return msg
        
    def send_gmail(self, from_addr, dest, msg_s):
        """
        Send email using GMail
        """
        s = smtplib.SMTP('smtp.gmail.com:587')
        s.starttls()
        s.login(self.settings.GMAIL_USER, self.settings.GMAIL_PASSWORD)
        s.sendmail(from_addr, [dest], msg_s)
        s.quit()

    def send_local(self, from_addr, dest, msg_s):
        """
        Send email using local SMTP
        """
        s = smtplib.SMTP('localhost')
        s.sendmail(from_addr, [dest], msg_s)
        s.quit()

    def now(self):
        """
        Helper function to make unit tests easier - return datetime.now()
        """
        return datetime.datetime.now()
    
    def get_battlenet(self, realm, character):
        """ get a character's info from Battlenet API """
        try:
            char = self.bnet.get_character(battlenet.UNITED_STATES, realm, character)
        except battlenet.exceptions.CharacterNotFound:
            self.logger.error("ERROR - Character Not Found - realm='{r}' character='{c}'".format(r=realm, c=character))
            return None
        self.logger.debug("got character from battlenet; getting further information")
        # get all of the info we need
        char.appearance
        char.equipment
        char.level
        char.professions
        char.faction
        # these seem buggy
        try:
            char.stats
        except:
            pass
        try:
            char.talents
        except:
            pass
        # copy the dict
        d = deepcopy(char.__dict__['_data'])
        # remove stuff we don't want
        for i in ['connection', 'achievementPoints', 'lastModified', '_items', 'achievement_points']:
            if i in d:
                del d[i]
        for t in ['primary', 'secondary']:
            for i in d['professions'][t]:
                if 'recipes' in i:
                    del i['recipes']
        self.logger.debug("cleaned up character data")
        return d

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                   help="dry-run - don't send email, just say what would be sent")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-c', '--configdir', dest='confdir', action='store', type=str, default=DEFAULT_CONFDIR,
                   help='configuration directory (default: {c})'.format(c=DEFAULT_CONFDIR))
    p.add_argument('--genconfig', dest='genconfig', action='store_true', default=False,
                   help='generate a sample configuration file at configdir/settings.py')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.genconfig:
        NightlySimcraft.gen_config(args.confdir)
        print("Configuration file generated at: {c}".format(c=os.path.join(os.path.abspath(os.path.expanduser(args.confdir)), 'settings.py')))
        raise SystemExit()
    script = NightlySimcraft(dry_run=args.dry_run, verbose=args.verbose, confdir=args.confdir)
    script.run()
