#!/usr/bin/env python
"""
Python 2.7/3 wrapper script to do a nightly (cron'ed) run of
[SimulationCraft](http://simulationcraft.org/) when your gear
changes, and email you results. Configurable for any number of
characters, and any number of destination email addresses.

What It Does
-------------

- uses [battlenet](https://pypi.python.org/pypi/battlenet/0.2.6) to check your
  character's gear, and cache it locally (under `~/.nightly_simcraft/`).
- if your gear has changed, run simc for your character and email the report
  to a specified address

Requirements
-------------

* battlenet>=0.2.6

You can install these like:

`pip install battlenet>=0.2.6`

Configuration
--------------

`~/.nightly_simcraft/settings.py` is just Python code that will be imported by
this script. An example follows:

#### BEGIN example ~/.nightly_simcraft/settings.py
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
  },
]
#### END example ~/.nightly_simcraft/settings.py

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
import argparse
import logging

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


class NightlySimcraft:
    """ might as well use a class. It'll make things easier later. """

    def __init__(self, logger=None, dry_run=False, verbose=0):
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

    def run(self):
        """ do stuff here """
        self.logger.info("info-level log message")
        self.logger.debug("debug-level log message")
        self.logger.error("error-level log message")
        print("run.")
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
        """
        [GCC 4.9.2] on linux2
        Type "help", "copyright", "credits" or "license" for more information.
        >>> from battlent import Connection
        Traceback (most recent call last):
              File "<stdin>", line 1, in <module>
              ImportError: No module named battlent
              >>> from battlnet import Connection
              Traceback (most recent call last):
              File "<stdin>", line 1, in <module>
              ImportError: No module named battlnet
              >>> from battlenet import Connection
              >>> conn = Connection()
              >>> chat = conn.get_character(battlenet.UNITED_STATES, 'Ares 52', 'Jantman')
              Traceback (most recent call last):
              File "<stdin>", line 1, in <module>
              NameError: name 'battlenet' is not defined
              >>> import battlenet
              >>> chat = conn.get_character(battlenet.UNITED_STATES, 'Ares 52', 'Jantman')
              Traceback (most recent call last):
              File "<stdin>", line 1, in <module>
                File "/home/jantman/venvs/foo/lib/python2.7/site-packages/battlenet/connection.py", line 125, in get_character
                    raise CharacterNotFound
                battlenet.exceptions.CharacterNotFound
                >>> chat = conn.get_character(battlenet.UNITED_STATES, 'Area 52', 'Jantman')
                >>> chat
                <Character: Jantman@Area 52>
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
                      help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    script = SimpleScript(dry_run=args.dry_run, verbose=args.verbose)
    script.run()
