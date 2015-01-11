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
- Generate a new `.simc` file 

Requirements
-------------

* battlenet>=0.2.6

You can install these like:

`pip install battlenet>=0.2.6`

Configuration
--------------

`~/.nightly_simcraft/settings.py` is just Python code that will be imported by
this script. If it doesn't already exist when this script runs, the script
will exit telling you about an option to create an example config.

You'll need at least one `.simc` file to configure the run. That's outside the
scope of this script. I recommend using the SimulationCraft GUI to configure it
as you want, and then use the contents of the "Simulate" tab as the simc file
(place this in the same directory as your configuration file, and update
settings.py to point at it).

At every run, simc will be run against a copy of the specified simc file,
with your character's level and gear updated from the Battlenet API. No
other changes will be made to the file.

Copyright
----------

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The canonical, current version of this script will always be available at:
<https://github.com/jantman/misc-scripts/blob/master/nightly_simcraft.py>

Changelog
----------

2015-01-09 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import argparse
import logging
from textwrap import dedent

if sys.version_info[0] > 3 or ( sys.version_info[0] == 3 and sys.version_info[1] >= 3):
    import importlib.machinery
else:
    import imp

import battlenet

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


DEFAULT_CONFDIR = '~/.nightly_simcraft'


class NightlySimcraft:
    """ might as well use a class. It'll make things easier later. """

    SAMPLE_CONF = """
    # example nightly_simcraft.py configuration file
    # all file paths are relative to this file
    DEFAULT_SIMC = 'default.simc'
    CHARACTERS = [
      {
        'realm': 'realname',
        'character': 'character_name',
        'email': 'you@domain.com',
      },
      {
        'realm': 'realname',
        'character': 'character_name',
        'email': ['you@domain.com', 'someone@domain.com'],
        'simc': 'a_different.simc',
      },
    ]
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
        self.confdir = confdir
        self.read_config(confdir)
        self.logger.debug("connecting to BattleNet API")
        self.bnet = battlenet.Connection()
        self.logger.debug("connected")

    def read_config(self, confdir):
        """ read in config file """
        confpath = os.path.abspath(os.path.expanduser(os.path.join(confdir, 'settings.py')))
        self.logger.debug("Reading configuration from: {c}".format(c=confpath))
        if not os.path.exists(confpath):
            self.logger.error("ERROR - configuration file does not exist. Please run with --genconfig to generate an example one.")
            raise SystemExit(1)
        self.import_from_path(confpath)
        self.validate_config()
        self.logger.debug("Imported settings. {n} characters, DEFAULT_SIMC={d}".format(n=len(self.settings.CHARACTERS), d=self.settings.DEFAULT_SIMC))

    def validate_config(self):
        # validate config
        if not hasattr(self.settings, 'DEFAULT_SIMC'):
            self.logger.error("ERROR: Settings file must define DEFAULT_SIMC filename (string)")
            raise SystemExit(1)
        if type(self.settings.DEFAULT_SIMC) != type(''):
            self.logger.error("ERROR: Settings file must define DEFAULT_SIMC filename (string)")
            raise SystemExit(1)
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
        if 'character' not in char:
            self.logger.debug("'character' not in char dict")
            return False
        return True
            
    def run(self):
        """ do stuff here """
        for char in self.settings.CHARACTERS:
            cname = '{c}@{r}'.format(c=char['character'], r=char['realm'])
            self.logger.debug("Doing character: {c}".format(c=cname))
            if not validate_character(char):
                self.logger.warning("Character configuration not valid, skipping: {c}".format(c=char))
                continue
            bnet_info = self.get_battlenet(char['realm'], char['character'])
            if bnet_info is None:
                self.logger.warning("Character {c} not found; skipping.".format(c=cname))
                continue
            print("do something")
        """
        See:
        [SimulationCraft - How to Sim your Character - Guides - Wowhead](http://www.wowhead.com/guide=100/simulationcraft-how-to-sim-your-character)
        [How to Sim Your Toon: SimulationCraft for Dummies - Warlock - Wowhead Forums](http://www.wowhead.com/forums&topic=152437/how-to-sim-your-toon-simulationcraft-for-dummies)
        [StartersGuide - simulationcraft - A starters guide for Simulationcraft - World of Warcraft DPS Simulator - Google Project Hosting](https://code.google.com/p/simulationcraft/wiki/StartersGuide)
        [TextualConfigurationInterface - simulationcraft - TCI reference: basics. - World of Warcraft DPS Simulator - Google Project Hosting](https://code.google.com/p/simulationcraft/wiki/TextualConfigurationInterface)
        [Automation - simulationcraft - TCI reference: Automation Tool. - World of Warcraft DPS Simulator - Google Project Hosting](https://code.google.com/p/simulationcraft/wiki/Automation)
        [Examples - simulationcraft - Useful pieces of TCI - World of Warcraft DPS Simulator - Google Project Hosting](https://code.google.com/p/simulationcraft/wiki/Examples)
        [Options - simulationcraft - TCI reference: exhaustive list of settings. - World of Warcraft DPS Simulator - Google Project Hosting](https://code.google.com/p/simulationcraft/wiki/Options)
        [Output - simulationcraft - TCI reference: output - World of Warcraft DPS Simulator - Google Project Hosting](https://code.google.com/p/simulationcraft/wiki/Output)
        
        """

    def get_battlenet(self, realm, character):
        """ get a character's info from Battlenet API """
        try:
            char = self.bnet.get_character(battlenet.UNITED_STATES, realm, character)
        except battlenet.exceptions.CharacterNotFound:
            self.logger.error("ERROR - Character Not Found - realm='{r}' character='{c}'".format(r=realm, c=character))
        """
        >>> dir(chat)
        ['ALCHEMY', 'ALLIANCE', 'ALL_FIELDS', 'APPEARANCE', 'ARCHAEOLOGY', 'BLACKSMITHING', 'BLOOD_ELF', 'COMPANIONS', 'COOKING', 'DEATH_KNIGHT', 'DRAENEI', 'DRUID', 'DWARF', 'ENCHANTING', 'ENGINEERING', 'FEMALE', 'FIRST_AID', 'FISHING', 'GNOME', 'GOBLIN', 'GUILD', 'HERBALISM', 'HORDE', 'HUMAN', 'HUNTER', 'INSCRIPTION', 'ITEMS', 'JEWELCRATING', 'LEATHERWORKING', 'MAGE', 'MALE', 'MINING', 'MOUNTS', 'NIGHT_ELF', 'ORC', 'PALADIN', 'PETS', 'PRIEST', 'PROFESSIONS', 'QUESTS', 'REPUTATIONS', 'ROGUE', 'SHAMAN', 'STATS', 'Skinning', 'TAILORING', 'TALENTS', 'TAUREN', 'TITLES', 'TROLL', 'UNDEAD', 'WARLOCK', 'WARRIOR', 'WORGEN', '__class__', '__delattr__', '__dict__', '__doc__', '__eq__', '__format__', '__getattribute__', '__hash__', '__init__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__weakref__', '_data', '_delete_property_fields', '_fields', '_populate_data', '_refresh_if_not_present', 'achievement_points', 'appearance', 'class_', 'companions', 'connection', 'equipment', 'faction', 'gender', 'get_class_name', 'get_full_class_name', 'get_race_name', 'get_realm_name', 'get_spec_name', 'get_thumbnail_url', 'guild', 'last_modified', 'level', 'mounts', 'name', 'professions', 'race', 'realm', 'refresh', 'region', 'reputations', 'stats', 'talents', 'thumbnail', 'titles', 'to_json']
                >>> chat.titles
                [<Title: %s of the Iron Vanguard>]
                >>> chat.equipment
                <Equipment>
                >>> dir(chat.equipment)
                ['__class__', '__delattr__', '__dict__', '__doc__', '__eq__', '__format__', '__getattribute__', '__getitem__', '__hash__', '__init__', '__module__', '__ne__', '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__weakref__', '_character', '_data', 'average_item_level', 'average_item_level_equiped', 'back', 'chest', 'feet', 'finger1', 'finger2', 'hands', 'head', 'legs', 'main_hand', 'neck', 'off_hand', 'ranged', 'shirt', 'shoulder', 'tabard', 'to_json', 'trinket1', 'trinket2', 'waist', 'wrist']
                >>> chat.equipment.__dict__
                {'trinket2': <Item: Tormented Emblem of Flame>, 'trinket1': <Item: Sandman's Pouch>, 'back': <Item: Drape of Frozen Dreams>, 'feet': <Item: Windshaper Treads>, 'tabard': None, 'shirt': None, 'chest': <Item: Hexweave Robe of the Peerless>, 'legs': <Item: Lightbinder Leggings>, 'main_hand': <Item: Staff of Trials>, 'head': <Item: Crown of Power>, 'ranged': None, '_character': <Character: Jantman@Area 52>, 'wrist': <Item: Bracers of Arcane Mystery>, 'hands': <Item: Windshaper Gloves>, '_data': {u'shoulder': {u'stats': [{u'stat': 32, u'amount': 104}, {u'stat': 5, u'amount': 138}, {u'stat': 36, u'amount': 72}, {u'stat': 7, u'amount': 207}], u'name': u'Twin-Gaze Spaulders', u'tooltipParams': {}, u'armor': 71, u'itemLevel': 640, u'bonusLists': [], u'context': u'raid-finder', u'quality': 4, u'id': 115997, u'icon': u'inv_shoulder_cloth_draenorlfr_c_01'}, u'averageItemLevelEquipped': 623, u'averageItemLevel': 623, u'neck': {u'stats': [{u'stat': 59, u'amount': 41}, {u'stat': 49, u'amount': 46}, {u'stat': 5, u'amount': 66}, {u'stat': 7, u'amount': 99}], u'name': u'Skywatch Adherent Locket', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 592, u'bonusLists': [15], u'context': u'quest-reward', u'quality': 4, u'id': 114951, u'icon': u'inv_misc_necklace_6_0_024'}, u'trinket1': {u'stats': [{u'stat': 5, u'amount': 175}], u'name': u"Sandman's Pouch", u'tooltipParams': {}, u'armor': 0, u'itemLevel': 640, u'bonusLists': [525, 529], u'context': u'trade-skill', u'quality': 4, u'id': 112320, u'icon': u'inv_inscription_trinket_mage'}, u'trinket2': {u'stats': [{u'stat': 5, u'amount': 120}], u'name': u'Tormented Emblem of Flame', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 600, u'bonusLists': [], u'context': u'dungeon-normal', u'quality': 3, u'id': 114367, u'icon': u'inv_jewelry_talisman_11'}, u'finger2': {u'stats': [{u'stat': 32, u'amount': 66}, {u'stat': 5, u'amount': 94}, {u'stat': 36, u'amount': 57}, {u'stat': 7, u'amount': 141}], u'name': u'Diamondglow Circle', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109763, u'icon': u'inv_60dungeon_ring2d'}, u'finger1': {u'stats': [{u'stat': 40, u'amount': 54}, {u'stat': 49, u'amount': 77}, {u'stat': 5, u'amount': 103}, {u'stat': 7, u'amount': 155}], u'name': u'Solium Band of Wisdom', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 640, u'bonusLists': [], u'context': u'quest-reward', u'quality': 4, u'id': 118291, u'icon': u'inv_misc_6oring_purplelv1'}, u'head': {u'stats': [{u'stat': 51, u'amount': 63}, {u'stat': 32, u'amount': 139}, {u'stat': 5, u'amount': 184}, {u'stat': 36, u'amount': 93}, {u'stat': 7, u'amount': 275}], u'name': u'Crown of Power', u'tooltipParams': {}, u'armor': 77, u'itemLevel': 640, u'bonusLists': [], u'context': u'', u'quality': 4, u'id': 118942, u'icon': u'inv_crown_02'}, u'mainHand': {u'stats': [{u'stat': 40, u'amount': 81}, {u'stat': 5, u'amount': 139}, {u'stat': 36, u'amount': 99}, {u'stat': 7, u'amount': 208}, {u'stat': 45, u'amount': 795}], u'name': u'Staff of Trials', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 610, u'weaponInfo': {u'dps': 124.69697, u'damage': {u'max': 494, u'exactMin': 329.0, u'exactMax': 494.0, u'min': 329}, u'weaponSpeed': 3.3}, u'bonusLists': [], u'context': u'quest-reward', u'quality': 3, u'id': 119463, u'icon': u'inv_staff_2h_draenordungeon_c_05'}, u'back': {u'stats': [{u'stat': 49, u'amount': 57}, {u'stat': 32, u'amount': 66}, {u'stat': 5, u'amount': 94}, {u'stat': 7, u'amount': 141}], u'name': u'Drape of Frozen Dreams', u'tooltipParams': {}, u'armor': 44, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109926, u'icon': u'inv_cape_draenordungeon_c_02_plate'}, u'feet': {u'stats': [{u'stat': 32, u'amount': 70}, {u'stat': 5, u'amount': 97}, {u'stat': 36, u'amount': 57}, {u'stat': 7, u'amount': 146}], u'name': u'Windshaper Treads', u'tooltipParams': {}, u'armor': 51, u'itemLevel': 603, u'bonusLists': [171], u'context': u'quest-reward', u'quality': 3, u'id': 114684, u'icon': u'inv_cloth_draenorquest95_b_01boot'}, u'chest': {u'stats': [{u'stat': 49, u'amount': 131}, {u'stat': 32, u'amount': 107}, {u'stat': 5, u'amount': 184}, {u'stat': 7, u'amount': 275}], u'name': u'Hexweave Robe of the Peerless', u'tooltipParams': {}, u'armor': 94, u'itemLevel': 640, u'bonusLists': [50, 525, 538], u'context': u'trade-skill', u'quality': 4, u'id': 114813, u'icon': u'inv_cloth_draenorcrafted_d_01robe'}, u'wrist': {u'stats': [{u'stat': 32, u'amount': 63}, {u'stat': 5, u'amount': 94}, {u'stat': 36, u'amount': 63}, {u'stat': 7, u'amount': 141}], u'name': u'Bracers of Arcane Mystery', u'tooltipParams': {}, u'armor': 39, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109864, u'icon': u'inv_cloth_draenordungeon_c_01bracer'}, u'hands': {u'stats': [{u'stat': 32, u'amount': 53}, {u'stat': 40, u'amount': 63}, {u'stat': 5, u'amount': 89}, {u'stat': 7, u'amount': 133}], u'name': u'Windshaper Gloves', u'tooltipParams': {}, u'armor': 41, u'itemLevel': 593, u'bonusLists': [], u'context': u'quest-reward', u'quality': 2, u'id': 114689, u'icon': u'inv_cloth_draenorquest95_b_01glove'}, u'legs': {u'stats': [{u'stat': 49, u'amount': 101}, {u'stat': 32, u'amount': 118}, {u'stat': 5, u'amount': 167}, {u'stat': 7, u'amount': 251}], u'name': u'Lightbinder Leggings', u'tooltipParams': {}, u'armor': 77, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109807, u'icon': u'inv_cloth_draenordungeon_c_01pant'}, u'waist': {u'stats': [{u'stat': 49, u'amount': 101}, {u'stat': 40, u'amount': 76}, {u'stat': 5, u'amount': 138}, {u'stat': 7, u'amount': 207}], u'name': u'Hexweave Belt of the Harmonious', u'tooltipParams': {}, u'armor': 53, u'itemLevel': 640, u'bonusLists': [213, 525, 537], u'context': u'trade-skill', u'quality': 4, u'id': 114816, u'icon': u'inv_cloth_draenorcrafted_d_01belt'}}, 'waist': <Item: Hexweave Belt of the Harmonious>, 'shoulder': <Item: Twin-Gaze Spaulders>, 'neck': <Item: Skywatch Adherent Locket>, 'finger2': <Item: Diamondglow Circle>, 'average_item_level_equiped': 623, 'finger1': <Item: Solium Band of Wisdom>, 'average_item_level': 623, 'off_hand': None}
        """

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
