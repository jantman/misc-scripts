#!/usr/bin/env python
 # -*- coding: utf-8 -*-
"""
Tests for nightly_simcraft.py from:
<https://github.com/jantman/misc-scripts/blob/master/nightly_simcraft.py>

Requirements
=============

* pytest
* mock
* pytest-cov
* pep8, pytest-pep8

Usage
======

To just run the tests (with verbose output):

    py.test -vv test_skeleton.py

To also run PEP8 style checking:

    py.test -vv --pep8 test_skeleton.py skeleton.py

To also print a coverage report (requires `pytest-cov`):

    py.test -vv --pep8 --cov-report term-missing --cov=skeleton test_skeleton.py skeleton.py

To generate a nicely-readable HTML coverage report, use ``--cov-report html``.

Information
============

The latest version of this script is available at:
<https://github.com/jantman/misc-scripts/blob/master/test_nightly_simcraft.py>

Copyright 2015 Jason Antman <jason@jasonantman.com>
  <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2015-01-10 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import pytest
import logging
from mock import MagicMock, call, patch, Mock, mock_open
from contextlib import nested
import sys
import datetime
from copy import deepcopy
import subprocess
from freezegun import freeze_time

import battlenet
import nightly_simcraft


class Container:
    pass


def test_default_confdir():
    assert nightly_simcraft.DEFAULT_CONFDIR == '~/.nightly_simcraft'

def test_parse_argv():
    """ test parse_argv() """
    argv = ['-d', '-vv', '-c' 'foobar', '--genconfig']
    args = nightly_simcraft.parse_args(argv)
    assert args.dry_run is True
    assert args.verbose == 2
    assert args.confdir == 'foobar'
    assert args.genconfig is True


class Test_NightlySimcraft:

    @pytest.fixture
    def mock_ns(self):
        """ a mocked NightlySimcraft object """
        bn = MagicMock(spec_set=battlenet.Connection)
        conn = MagicMock(spec_set=battlenet.Connection)
        bn.return_value = conn
        rc = Mock()
        lc = Mock()
        mocklog = MagicMock(spec_set=logging.Logger)
        def mock_ap_se(p):
            return p
        def mock_eu_se(p):
            return p.replace('~/', '/home/user/')
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc),
                patch('nightly_simcraft.NightlySimcraft.load_character_cache', lc),
                patch('nightly_simcraft.os.path.expanduser'),
                patch('nightly_simcraft.os.path.abspath'),
        ) as (bnp, rcp, lcc, mock_eu, mock_ap):
            mock_ap.side_effect = mock_ap_se
            mock_eu.side_effect = mock_eu_se
            s = nightly_simcraft.NightlySimcraft(verbose=2, logger=mocklog)
        return (bn, rc, mocklog, s, conn, lcc)

    @pytest.fixture
    def mock_bnet_character(self, bnet_data):
        char = battlenet.things.Character(battlenet.UNITED_STATES,
                                          realm='Area 52',
                                          name='jantman',
                                          data=bnet_data)
        return char

    def test_init_default(self):
        """ test SimpleScript.init() """
        bn = MagicMock(spec_set=battlenet.Connection)
        rc = Mock()
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc)
        ):
            s = nightly_simcraft.NightlySimcraft(dry_run=False,
                                                 verbose=0,
                                                 confdir='~/.nightly_simcraft'
                                             )
        assert bn.mock_calls == [call()]
        assert rc.call_args_list == [call('~/.nightly_simcraft')]
        assert s.dry_run is False
        assert type(s.logger) == logging.Logger
        assert s.logger.level == logging.NOTSET

    def test_init_logger(self):
        """ test SimpleScript.init() with specified logger """
        m = MagicMock(spec_set=logging.Logger)
        bn = MagicMock(spec_set=battlenet.Connection)
        rc = Mock()
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc)
        ):
            s = nightly_simcraft.NightlySimcraft(logger=m)
        assert s.logger == m

    def test_init_dry_run(self):
        """ test SimpleScript.init() with dry_run=True """
        bn = MagicMock(spec_set=battlenet.Connection)
        rc = Mock()
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc)
        ):
            s = nightly_simcraft.NightlySimcraft(dry_run=True)
        assert s.dry_run is True

    def test_init_verbose(self):
        """ test SimpleScript.init() with verbose=1 """
        bn = MagicMock(spec_set=battlenet.Connection)
        rc = Mock()
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc)
        ):
            s = nightly_simcraft.NightlySimcraft(verbose=1)
        assert s.logger.level == logging.INFO

    def test_init_debug(self):
        """ test SimpleScript.init() with verbose=2 """
        bn = MagicMock(spec_set=battlenet.Connection)
        rc = Mock()
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc)
        ):
            s = nightly_simcraft.NightlySimcraft(verbose=2)
        assert s.logger.level == logging.DEBUG

    def test_read_config_missing(self, mock_ns):
        """ test read_config() when settings file is missing """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.NightlySimcraft.import_from_path'),
                patch('nightly_simcraft.NightlySimcraft.validate_config'),
        ) as (mock_path_exists, mock_import, mock_validate):
            mock_path_exists.return_value = False
            with pytest.raises(SystemExit) as excinfo:
                s.read_config('/foo')
            assert excinfo.value.code == 1
        assert call('Reading configuration from: /foo/settings.py') in mocklog.debug.call_args_list
        assert mock_import.call_count == 0
        assert mock_path_exists.call_count == 1
        assert mocklog.error.call_args_list == [call("ERROR - configuration file does not exist. Please run with --genconfig to generate an example one.")]

    def test_read_config(self, mock_ns):
        """ test read_config() working correctly """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        mock_settings = Container()
        setattr(mock_settings, 'CHARACTERS', [])
        setattr(mock_settings, 'DEFAULT_SIMC', 'foo')
        setattr(s, 'settings', mock_settings)
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.NightlySimcraft.import_from_path'),
                patch('nightly_simcraft.NightlySimcraft.validate_config'),
        ) as (mock_path_exists, mock_import, mock_validate):
            mock_path_exists.return_value = True
            s.read_config('/foo')
        assert call('Reading configuration from: /foo/settings.py') in mocklog.debug.call_args_list
        assert mock_import.call_args_list == [call('/foo/settings.py')]
        assert mock_path_exists.call_count == 1
        assert mock_validate.call_args_list == [call()]
        
    def test_genconfig(self):
        """ test gen_config() """
        cd = '/foo'
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', create=True)
        ) as (mock_pe, mock_open):
            mock_open.return_value = MagicMock(spec=file)
            mock_pe.return_value = True
            nightly_simcraft.NightlySimcraft.gen_config(cd)
        file_handle = mock_open.return_value.__enter__.return_value
        assert mock_open.call_args_list == [call('/foo/settings.py', 'w')]
        assert file_handle.write.call_count == 1

    def test_genconfig_nodir(self):
        """ test gen_config() with config directory missing """
        cd = '/foo'
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.os.mkdir'),
                patch('nightly_simcraft.open', create=True)
        ) as (mock_pe, mock_mkdir, mock_open):
            mock_open.return_value = MagicMock(spec=file)
            mock_pe.return_value = False
            nightly_simcraft.NightlySimcraft.gen_config(cd)
        file_handle = mock_open.return_value.__enter__.return_value
        assert mock_open.call_args_list == [call('/foo/settings.py', 'w')]
        assert file_handle.write.call_count == 1
        assert mock_mkdir.call_args_list == [call('/foo')]

    def test_validate_config_no_characters(self, mock_ns):
        """ test validate_config() with no characters """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        mock_settings = Container()
        setattr(mock_settings, 'DEFAULT_SIMC', 'foo')
        setattr(s, 'settings', mock_settings)
        with pytest.raises(SystemExit) as excinfo:
            res = s.validate_config()
        assert excinfo.value.code == 1
        assert mocklog.error.call_args_list == [call("ERROR: Settings file must define CHARACTERS list")]

    def test_validate_config_characters_not_list(self, mock_ns):
        """ test validate_config() if CHARACTERS is not a list """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        mock_settings = Container()
        setattr(mock_settings, 'DEFAULT_SIMC', 'foo')
        setattr(mock_settings, 'CHARACTERS', 'foo')
        setattr(s, 'settings', mock_settings)
        with pytest.raises(SystemExit) as excinfo:
            res = s.validate_config()
        assert excinfo.value.code == 1
        assert mocklog.error.call_args_list == [call("ERROR: Settings file must define CHARACTERS list")]

    def test_validate_config_characters_empty(self, mock_ns):
        """ test validate_config() if CHARACTERS is an empty list """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        mock_settings = Container()
        setattr(mock_settings, 'DEFAULT_SIMC', 'foo')
        setattr(mock_settings, 'CHARACTERS', [])
        setattr(s, 'settings', mock_settings)
        with pytest.raises(SystemExit) as excinfo:
            res = s.validate_config()
        assert excinfo.value.code == 1
        assert mocklog.error.call_args_list == [call("ERROR: Settings file must define CHARACTERS list with at least one character")]

    @pytest.mark.skipif(sys.version_info >= (3,3), reason="requires python < 3.3")
    def test_import_from_path_py27(self, mock_ns):
        """ test import_from_path() under py27 """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        # this is a bit of a hack...
        settings_mock = Mock()
        imp_mock = Mock()
        ls_mock = Mock()
        ls_mock.return_value = settings_mock
        imp_mock.load_source = ls_mock
        sys.modules['imp'] = imp_mock
        with patch('nightly_simcraft.imp', imp_mock):
            s.import_from_path('foobar')
            assert s.settings == settings_mock
        assert call('importing foobar - <py33') in mocklog.debug.call_args_list
        assert ls_mock.call_args_list == [call('settings', 'foobar')]
        assert call('imported settings module') in mocklog.debug.call_args_list

    @pytest.mark.skipif(sys.version_info < (3,3), reason="requires python3.3")
    def test_import_from_path_py33(self, mock_ns):
        """ test import_from_path() under py33 """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        settings_mock = Mock()
        machinery_mock = Mock()
        sfl_mock = Mock()
        loader_mock = Mock()
        loader_mock.load_module.return_value = settings_mock
        sfl_mock.return_value = loader_mock
        machinery_mock.SourceFileLoader = sfl_mock
        importlib_mock = Mock()
        nightly_simcraft.sys.modules['importlib'] = importlib_mock
        sys.modules['importlib.machinery'] = machinery_mock
        
        with patch('nightly_simcraft.importlib.machinery', machinery_mock):
            s.import_from_path('foobar')
            assert s.settings == settings_mock
        assert call('importing foobar - <py33') in mocklog.debug.call_args_list
        assert ls_mock.call_args_list == [call('settings', 'foobar')]
        assert call('imported settings module') in mocklog.debug.call_args_list

    def test_validate_character(self, mock_ns):
        """ test validate_character() with correct character """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        char = {'realm': 'rname', 'name': 'cname'}
        result = s.validate_character(char)
        assert result is True

    def test_validate_character_notdict(self, mock_ns):
        """ test validate_character() where char is not a dict """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        char = 'realm'
        mocklog.debug.reset_mock()
        result = s.validate_character(char)
        assert mocklog.debug.call_args_list == [call('Character is not a dict')]
        assert result is False

    def test_validate_character_no_realm(self, mock_ns):
        """ test validate_character() with character missing realm """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        char = {'name': 'cname'}
        mocklog.debug.reset_mock()
        result = s.validate_character(char)
        assert mocklog.debug.call_args_list == [call("'realm' not in char dict")]
        assert result is False

    def test_validate_character_no_char(self, mock_ns):
        """ test validate_character() with character missing name """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        char = {'realm': 'rname'}
        mocklog.debug.reset_mock()
        result = s.validate_character(char)
        assert mocklog.debug.call_args_list == [call("'name' not in char dict")]
        assert result is False

    def test_run(self, mock_ns):
        """ test run() in ideal/working situation """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        chars = [{'name': 'nameone', 'realm': 'realmone', 'email': 'foo@example.com'}]
        s_container = Container()
        setattr(s_container, 'CHARACTERS', chars)
        setattr(s, 'settings', s_container)
        mocklog.debug.reset_mock()
        with nested(
                patch('nightly_simcraft.NightlySimcraft.validate_character'),
                patch('nightly_simcraft.NightlySimcraft.get_battlenet'),
                patch('nightly_simcraft.NightlySimcraft.do_character'),
                patch('nightly_simcraft.NightlySimcraft.character_has_changes'),
        ) as (mock_validate, mock_get_bnet, mock_do_char, mock_chc):
            mock_chc.return_value = 'foo'
            mock_validate.return_value = True
            mock_get_bnet.return_value = {}
            s.run()
        assert mocklog.debug.call_args_list == [call("Doing character: nameone@realmone")]
        assert mock_validate.call_args_list == [call(chars[0])]
        assert mock_get_bnet.call_args_list == [call('realmone', 'nameone')]
        assert mock_do_char.call_args_list == [call('nameone@realmone', chars[0], 'foo')]
        assert mock_chc.call_args_list == [call('nameone@realmone', {})]

    def test_run_invalid_character(self, mock_ns):
        """ test run() with an invalid character """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        chars = [{'name': 'nameone', 'realm': 'realmone', 'email': 'foo@example.com'}]
        s_container = Container()
        setattr(s_container, 'CHARACTERS', chars)
        setattr(s, 'settings', s_container)
        mocklog.debug.reset_mock()
        with nested(
                patch('nightly_simcraft.NightlySimcraft.validate_character'),
                patch('nightly_simcraft.NightlySimcraft.get_battlenet'),
                patch('nightly_simcraft.NightlySimcraft.do_character'),
                patch('nightly_simcraft.NightlySimcraft.character_has_changes'),
        ) as (mock_validate, mock_get_bnet, mock_do_char, mock_chc):
            mock_chc.return_value = None
            mock_validate.return_value = False
            mock_get_bnet.return_value = {}
            s.run()
        assert mocklog.debug.call_args_list == [call("Doing character: nameone@realmone")]
        assert mock_validate.call_args_list == [call(chars[0])]
        assert mock_get_bnet.call_args_list == []
        assert mocklog.warning.call_args_list == [call("Character configuration not valid, skipping: nameone@realmone")]
        assert mock_do_char.call_args_list == []
        assert mock_chc.call_args_list == []

    def test_run_no_battlenet(self, mock_ns):
        """ test run() with character not found on battlenet """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        chars = [{'name': 'nameone', 'realm': 'realmone', 'email': 'foo@example.com'}]
        s_container = Container()
        setattr(s_container, 'CHARACTERS', chars)
        setattr(s, 'settings', s_container)
        mocklog.debug.reset_mock()
        with nested(
                patch('nightly_simcraft.NightlySimcraft.validate_character'),
                patch('nightly_simcraft.NightlySimcraft.get_battlenet'),
                patch('nightly_simcraft.NightlySimcraft.do_character'),
                patch('nightly_simcraft.NightlySimcraft.character_has_changes'),
        ) as (mock_validate, mock_get_bnet, mock_do_char, mock_chc):
            mock_validate.return_value = True
            mock_get_bnet.return_value = None
            mock_chc.return_value = True
            s.run()
        assert mocklog.debug.call_args_list == [call("Doing character: nameone@realmone")]
        assert mock_validate.call_args_list == [call(chars[0])]
        assert mock_get_bnet.call_args_list == [call('realmone', 'nameone')]
        assert mocklog.warning.call_args_list == [call("Character nameone@realmone not found on battlenet; skipping.")]
        assert mock_do_char.call_args_list == []
        assert mock_chc.call_args_list == []

    def test_run_not_updated(self, mock_ns):
        """ test run() with no updates to character """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        chars = [{'name': 'nameone', 'realm': 'realmone', 'email': 'foo@example.com'}]
        s_container = Container()
        setattr(s_container, 'CHARACTERS', chars)
        setattr(s, 'settings', s_container)
        mocklog.debug.reset_mock()
        with nested(
                patch('nightly_simcraft.NightlySimcraft.validate_character'),
                patch('nightly_simcraft.NightlySimcraft.get_battlenet'),
                patch('nightly_simcraft.NightlySimcraft.do_character'),
                patch('nightly_simcraft.NightlySimcraft.character_has_changes'),
        ) as (mock_validate, mock_get_bnet, mock_do_char, mock_chc):
            mock_chc.return_value = None
            mock_validate.return_value = True
            mock_get_bnet.return_value = {}
            s.run()
        assert mocklog.debug.call_args_list == [call("Doing character: nameone@realmone")]
        assert mock_validate.call_args_list == [call(chars[0])]
        assert mock_get_bnet.call_args_list == [call('realmone', 'nameone')]
        assert mock_do_char.call_args_list == []
        assert mock_chc.call_args_list == [call('nameone@realmone', {})]

    def test_get_battlenet(self, mock_ns, mock_bnet_character):
        """ test get_battlenet() """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        conn.get_character.return_value = mock_bnet_character
        result = s.get_battlenet('rname', 'cname')
        assert conn.get_character.call_args_list == [call(battlenet.UNITED_STATES,
                                                 'rname',
                                                 'cname'
                                                 )
        ]
        for i in ['connection', 'achievementPoints', 'lastModified', '_items', 'achievement_points']:
            assert i not in result
        assert result['stats']['spellCrit'] == 12.5        
        assert 'recipes' not in result['professions']['primary'][0]
        assert result['name'] == 'Jantman'
        assert result['level'] == 100
        assert result['professions']['primary'][0] == {u'name': u'Tailoring',
                                                       u'max': 675,
                                                       u'rank': 627,
                                                       u'id': 197,
                                                       u'icon': u'trade_tailoring'
        }
        assert result['realm'] == 'Area 52'
        assert result['class'] == 9
        assert result['race'] == 5
        assert result['stats']['critRating'] == 825
        assert result['items']['shoulder']['id'] == 115997
        assert result['talents'][0]['talents'][0]['spell']['name'] == u'Soul Leech'

    def test_get_battlenet_badchar(self, mock_ns, mock_bnet_character):
        """ test get_battlenet() with character not found """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        conn.get_character.side_effect = battlenet.exceptions.CharacterNotFound()
        result = s.get_battlenet('rname', 'cname')
        assert conn.get_character.call_args_list == [call(battlenet.UNITED_STATES,
                                                 'rname',
                                                 'cname'
                                                 )
        ]
        assert result is None
        assert mocklog.error.call_args_list == [call("ERROR - Character Not Found - realm='rname' character='cname'")]

    def test_load_char_cache_noexist(self, mock_ns):
        """ test load_character_cache() on nonexistent file """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        mocko = mock_open()
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', mocko, create=True),
        ) as (mock_fexist, m):
            mock_fexist.return_value = False
            res = s.load_character_cache()
        assert mocko.mock_calls == []
        assert mock_fexist.call_args_list == [call('/home/user/.nightly_simcraft/characters.pkl')]
        assert res == {}

    def test_load_char_cache(self, mock_ns):
        """ test load_character_cache() """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', create=True),
                patch('nightly_simcraft.pickle.load')
        ) as (mock_fexist, mocko, mock_pkl):
            mock_fexist.return_value = True
            mocko.return_value = 'filecontents'
            mock_pkl.return_value = 'unpickled'
            res = s.load_character_cache()
        assert mocko.mock_calls == [call('/home/user/.nightly_simcraft/characters.pkl', 'rb')]
        assert mock_pkl.mock_calls == [call('filecontents')]
        assert mock_fexist.call_args_list == [call('/home/user/.nightly_simcraft/characters.pkl')]
        assert res == 'unpickled'

    def test_write_char_cache(self, mock_ns):
        """ test write_character_cache() """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        cache_content = {"foo": "bar", "baz": 3}
        openmock = MagicMock()
        with nested(
                patch('nightly_simcraft.open', create=True),
                patch('nightly_simcraft.pickle.dump')
        ) as (mocko, mock_pkl):
            mocko.return_value = openmock
            s.character_cache = deepcopy(cache_content)
            s.write_character_cache()
        assert mocko.mock_calls == [call('/home/user/.nightly_simcraft/characters.pkl', 'wb'),
                                    call().__enter__(),
                                    call().__exit__(None, None, None)]
        assert mock_pkl.mock_calls == [call(cache_content, openmock.__enter__())]

    def test_char_has_changes_true(self, mock_ns, char_data):
        """ test character_has_changes() with changes """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        orig_data = char_data
        cname = char_data['name'] + '@' + char_data['realm']
        ccache = {cname: orig_data}
        new_data = deepcopy(orig_data)
        new_data['items']['shoulder'] = {u'stats': [{u'stat': 59, u'amount': 60}, {u'stat': 32, u'amount': 80}, {u'stat': 5, u'amount': 109}, {u'stat': 7, u'amount': 163}], u'name': u'Mantle of Hooded Nightmares of the Savage', u'tooltipParams': {}, u'armor': 60, u'quality': 3, u'itemLevel': 615, u'context': u'dungeon-normal', u'bonusLists': [83], u'id': 114395, u'icon': u'inv_cloth_draenordungeon_c_01shoulder'}
        s.character_cache = ccache
        with patch('nightly_simcraft.NightlySimcraft.character_diff') as mock_char_diff:
            mock_char_diff.return_value = 'foobar'
            result = s.character_has_changes(cname, new_data)
        assert result == 'foobar'
        assert mock_char_diff.call_args_list == [call(orig_data, new_data)]

    def test_character_diff_item(self, mock_ns, char_data):
        """ test character_diff() """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        cname = char_data['name'] + '@' + char_data['realm']
        ccache = {cname: char_data}
        new_data = deepcopy(char_data)
        new_data['items']['shoulder'] = {u'stats': [{u'stat': 59, u'amount': 60}, {u'stat': 32, u'amount': 80}, {u'stat': 5, u'amount': 109}, {u'stat': 7, u'amount': 163}], u'name': u'Mantle of Hooded Nightmares of the Savage', u'tooltipParams': {}, u'armor': 60, u'quality': 3, u'itemLevel': 615, u'context': u'dungeon-normal', u'bonusLists': [83], u'id': 114395, u'icon': u'inv_cloth_draenordungeon_c_01shoulder'}
        s.character_cache = ccache
        result = s.character_diff(char_data, new_data)
        expected = ["change items.shoulder.context from raid-finder to dungeon-normal",
                    "change [u'items', u'shoulder', u'stats', 0, u'stat'] from 32 to 59",
                    "change [u'items', u'shoulder', u'stats', 0, u'amount'] from 104 to 60",
                    "change [u'items', u'shoulder', u'stats', 1, u'stat'] from 5 to 32",
                    "change [u'items', u'shoulder', u'stats', 1, u'amount'] from 138 to 80",
                    "change [u'items', u'shoulder', u'stats', 2, u'stat'] from 36 to 5",
                    "change [u'items', u'shoulder', u'stats', 2, u'amount'] from 72 to 109",
                    "change [u'items', u'shoulder', u'stats', 3, u'amount'] from 207 to 163",
                    "change items.shoulder.name from Twin-Gaze Spaulders to Mantle of Hooded Nightmares of the Savage",
                    "remove items.shoulder.tooltipParams [(u'transmogItem', 31054)]",
                    "change items.shoulder.armor from 71 to 60",
                    "change items.shoulder.quality from 4 to 3",
                    "change items.shoulder.icon from inv_shoulder_cloth_draenorlfr_c_01 to inv_cloth_draenordungeon_c_01shoulder",
                    "change items.shoulder.itemLevel from 640 to 615",
                    "change items.shoulder.id from 115997 to 114395",
                    "add items.shoulder.bonusLists [(0, 83)]",
                    ]
        expected_s = "\n".join(expected)
        assert result == expected_s

    def test_char_has_changes_false(self, mock_ns, char_data):
        """ test character_has_changes() without changes """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        orig_data = char_data
        cname = char_data['name'] + '@' + char_data['realm']
        ccache = {cname: orig_data}
        new_data = deepcopy(orig_data)
        s.character_cache = ccache
        result = s.character_has_changes(cname, new_data)
        assert result is None

    def test_char_has_changes_new(self, mock_ns, char_data):
        """ test character_has_changes() on never-before-seen character """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        orig_data = char_data
        cname = char_data['name'] + '@' + char_data['realm']
        ccache = {}
        new_data = deepcopy(orig_data)
        s.character_cache = ccache
        result = s.character_has_changes(cname, new_data)
        assert result == "Character not in cache (has not been seen before)."

    def test_do_character_no_simc(self, mock_ns):
        """ test do_character() with SIMC_PATH non-existant """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_name = 'cname@rname'
        c_settings = {'realm': 'rname', 'name': 'cname', 'email': ['foo@example.com']}
        c_diff = 'diffcontent'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        
        first_dt = False
        def mock_dtnow_se(*args, **kwargs):
            if first_dt:
                return datetime.datetime(2014, 1, 1, 0, 0, 0)
            return datetime.datetime(2014, 1, 1, 1, 2, 3)
        def mock_ope_se(p):
            return False
        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', create=True),
                patch('nightly_simcraft.os.chdir'),
                patch('nightly_simcraft.NightlySimcraft.now'),
                patch('nightly_simcraft.subprocess.check_output'),
                patch('nightly_simcraft.NightlySimcraft.send_char_email'),
        ) as (mock_ope, mocko, mock_chdir, mock_dtnow, mock_subp, mock_sce):
            mock_ope.side_effect = mock_ope_se
            mock_dtnow.side_effect = mock_dtnow_se
            s.settings = settings
            s.do_character(c_name, c_settings, c_diff)
        assert mock_ope.call_args_list == [call('/path/to/simc')]
        assert mocko.mock_calls == []
        assert mock_chdir.call_args_list == []
        assert mock_subp.call_args_list == []
        assert mock_sce.call_args_list == []
        assert mocklog.error.call_args_list == [call('ERROR: simc path /path/to/simc does not exist')]

    def test_do_character(self, mock_ns):
        """ test do_character() in normal case """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_name = 'cname@rname'
        c_settings = {'realm': 'rname', 'name': 'cname', 'email': ['foo@example.com']}
        c_diff = 'diffcontent'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        
        def mock_ope_se(p):
            return True

        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', create=True),
                patch('nightly_simcraft.os.chdir'),
                patch('nightly_simcraft.NightlySimcraft.now'),
                patch('nightly_simcraft.subprocess.check_output'),
                patch('nightly_simcraft.NightlySimcraft.send_char_email'),
        ) as (mock_ope, mocko, mock_chdir, mock_dtnow, mock_subp, mock_sce):
            mock_ope.side_effect = mock_ope_se
            mock_dtnow.side_effect = [datetime.datetime(2014, 1, 1, 0, 0, 0), datetime.datetime(2014, 1, 1, 1, 2, 3)]
            mock_subp.return_value = 'subprocessoutput'
            s.settings = settings
            s.do_character(c_name, c_settings, c_diff)
        assert mock_ope.call_args_list == [call('/path/to/simc'), call('/home/user/.nightly_simcraft/cname@rname.html')]
        assert mocko.mock_calls == [call('/home/user/.nightly_simcraft/cname@rname.simc', 'w'),
                                    call().__enter__(),
                                    call().__enter__().write('"armory=us,rname,cname"\n'),
                                    call().__enter__().write('calculate_scale_factors=1\n'),
                                    call().__enter__().write('html=cname@rname.html'),
                                    call().__exit__(None, None, None)]
        assert mock_chdir.call_args_list == [call('/home/user/.nightly_simcraft')]
        assert mock_subp.call_args_list == [call(['/path/to/simc',
                                                  '/home/user/.nightly_simcraft/cname@rname.simc'],
                                                 stderr=subprocess.STDOUT)]
        assert mock_sce.call_args_list == [call('cname@rname',
                                                {'realm': 'rname', 'name': 'cname', 'email': ['foo@example.com']},
                                                'diffcontent',
                                                '/home/user/.nightly_simcraft/cname@rname.html',
                                                datetime.timedelta(seconds=3723),
                                                'subprocessoutput')]
        assert mocklog.error.call_args_list == []

    def test_do_character_simc_error(self, mock_ns):
        """ test do_character() with simc exiting non-0 """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_name = 'cname@rname'
        c_settings = {'realm': 'rname', 'name': 'cname', 'email': ['foo@example.com']}
        c_diff = 'diffcontent'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        
        def mock_ope_se(p):
            return True

        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', create=True),
                patch('nightly_simcraft.os.chdir'),
                patch('nightly_simcraft.NightlySimcraft.now'),
                patch('nightly_simcraft.subprocess.check_output'),
                patch('nightly_simcraft.NightlySimcraft.send_char_email'),
        ) as (mock_ope, mocko, mock_chdir, mock_dtnow, mock_subp, mock_sce):
            mock_ope.side_effect = mock_ope_se
            mock_dtnow.side_effect = [datetime.datetime(2014, 1, 1, 0, 0, 0), datetime.datetime(2014, 1, 1, 1, 2, 3)]
            mock_subp.side_effect = subprocess.CalledProcessError(1, 'command', 'erroroutput')
            s.settings = settings
            s.do_character(c_name, c_settings, c_diff)
        assert mock_ope.call_args_list == [call('/path/to/simc')]
        assert mocko.mock_calls == [call('/home/user/.nightly_simcraft/cname@rname.simc', 'w'),
                                    call().__enter__(),
                                    call().__enter__().write('"armory=us,rname,cname"\n'),
                                    call().__enter__().write('calculate_scale_factors=1\n'),
                                    call().__enter__().write('html=cname@rname.html'),
                                    call().__exit__(None, None, None)]
        assert mock_chdir.call_args_list == [call('/home/user/.nightly_simcraft')]
        assert mock_subp.call_args_list == [call(['/path/to/simc',
                                                  '/home/user/.nightly_simcraft/cname@rname.simc'],
                                                 stderr=subprocess.STDOUT)]
        assert mock_sce.call_args_list == []
        assert mocklog.error.call_args_list == [call('Error running simc!')]

    def test_do_character_no_html(self, mock_ns):
        """ do_character() - simc runs but HTML not created """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_name = 'cname@rname'
        c_settings = {'realm': 'rname', 'name': 'cname', 'email': ['foo@example.com']}
        c_diff = 'diffcontent'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        
        def mock_ope_se(p):
            if p == '/home/user/.nightly_simcraft/cname@rname.html':
                return False
            return True

        with nested(
                patch('nightly_simcraft.os.path.exists'),
                patch('nightly_simcraft.open', create=True),
                patch('nightly_simcraft.os.chdir'),
                patch('nightly_simcraft.NightlySimcraft.now'),
                patch('nightly_simcraft.subprocess.check_output'),
                patch('nightly_simcraft.NightlySimcraft.send_char_email'),
        ) as (mock_ope, mocko, mock_chdir, mock_dtnow, mock_subp, mock_sce):
            mock_ope.side_effect = mock_ope_se
            mock_dtnow.side_effect = [datetime.datetime(2014, 1, 1, 0, 0, 0), datetime.datetime(2014, 1, 1, 1, 2, 3)]
            mock_subp.return_value = 'simcoutput'
            s.settings = settings
            s.do_character(c_name, c_settings, c_diff)
        assert mock_ope.call_args_list == [call('/path/to/simc'), call('/home/user/.nightly_simcraft/cname@rname.html')]
        assert mocko.mock_calls == [call('/home/user/.nightly_simcraft/cname@rname.simc', 'w'),
                                    call().__enter__(),
                                    call().__enter__().write('"armory=us,rname,cname"\n'),
                                    call().__enter__().write('calculate_scale_factors=1\n'),
                                    call().__enter__().write('html=cname@rname.html'),
                                    call().__exit__(None, None, None)]
        assert mock_chdir.call_args_list == [call('/home/user/.nightly_simcraft')]
        assert mock_subp.call_args_list == [call(['/path/to/simc',
                                                  '/home/user/.nightly_simcraft/cname@rname.simc'],
                                                 stderr=subprocess.STDOUT)]
        assert mock_sce.call_args_list == []
        assert mocklog.error.call_args_list == [call('ERROR: simc finished but HTML file not found on disk.')]

    def test_send_char_email(self, mock_ns):
        """ test send_char_email() in normal case """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_settings = {'realm': 'rname', 'name': 'cname', 'email': ['foo@example.com']}
        c_name = 'cname@rname'
        c_diff = 'diffcontent'
        html_path = '/path/to/output.html'
        duration = datetime.timedelta(seconds=3723)  # 1h 2m 3s
        output = 'simc_output_string'
        subj = 'SimulationCraft output for cname@rname'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        with nested(
                patch('nightly_simcraft.NightlySimcraft.send_gmail'),
                patch('nightly_simcraft.NightlySimcraft.format_message'),
                patch('nightly_simcraft.NightlySimcraft.send_local'),
        ) as (mock_gmail, mock_format, mock_local):
            mock_format.return_value = 'msgbody'
            s.settings = settings
            s.send_char_email(c_name,
                              c_settings,
                              c_diff,
                              html_path,
                              duration,
                              output)
        assert mock_format.call_args_list == [call('foo@example.com',
                                                   subj,
                                                   c_name,
                                                   c_diff,
                                                   html_path,
                                                   duration,
                                                   output)]
        assert mock_local.call_args_list == [call('foo@example.com',
                                                  'SimulationCraft output for cname@rname',
                                                  'msgbody')]
        assert mock_gmail.call_args_list == []

    def test_send_char_string_email(self, mock_ns):
        """ test send_char_email() with email as a string """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_settings = {'realm': 'rname',
                      'name': 'cname',
                      'email': 'foo@example.com'}
        c_name = 'cname@rname'
        c_diff = 'diffcontent'
        html_path = '/path/to/output.html'
        duration = datetime.timedelta(seconds=3723)  # 1h 2m 3s
        output = 'simc_output_string'
        subj = 'SimulationCraft output for cname@rname'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        with nested(
                patch('nightly_simcraft.NightlySimcraft.send_gmail'),
                patch('nightly_simcraft.NightlySimcraft.format_message'),
                patch('nightly_simcraft.NightlySimcraft.send_local'),
        ) as (mock_gmail, mock_format, mock_local):
            mock_format.return_value = 'msgbody'
            s.settings = settings
            s.send_char_email(c_name,
                              c_settings,
                              c_diff,
                              html_path,
                              duration,
                              output)
        assert mock_format.call_args_list == [call('foo@example.com',
                                                   subj,
                                                   c_name,
                                                   c_diff,
                                                   html_path,
                                                   duration,
                                                   output)]
        assert mock_local.call_args_list == [call('foo@example.com',
                                                  'SimulationCraft output for cname@rname',
                                                  'msgbody')]
        assert mock_gmail.call_args_list == []

    def test_send_char_string_email_gmail(self, mock_ns):
        """ test send_char_email() via gmail """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_settings = {'realm': 'rname',
                      'name': 'cname',
                      'email': 'foo@example.com'}
        c_name = 'cname@rname'
        c_diff = 'diffcontent'
        html_path = '/path/to/output.html'
        duration = datetime.timedelta(seconds=3723)  # 1h 2m 3s
        output = 'simc_output_string'
        subj = 'SimulationCraft output for cname@rname'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        setattr(settings, 'GMAIL_USERNAME', 'gmailuser')
        setattr(settings, 'GMAIL_PASSWORD', 'gmailpass')
        with nested(
                patch('nightly_simcraft.NightlySimcraft.send_gmail'),
                patch('nightly_simcraft.NightlySimcraft.format_message'),
                patch('nightly_simcraft.NightlySimcraft.send_local'),
        ) as (mock_gmail, mock_format, mock_local):
            mock_format.return_value = 'msgbody'
            s.settings = settings
            s.send_char_email(c_name,
                              c_settings,
                              c_diff,
                              html_path,
                              duration,
                              output)
        assert mock_format.call_args_list == [call('foo@example.com',
                                                   subj,
                                                   c_name,
                                                   c_diff,
                                                   html_path,
                                                   duration,
                                                   output)]
        assert mock_gmail.call_args_list == [call('foo@example.com',
                                                  'SimulationCraft output for cname@rname',
                                                  'msgbody')]
        assert mock_local.call_args_list == []

    def test_send_char_email_dryrun(self, mock_ns):
        """ test send_char_email() for a dry run """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        c_settings = {'realm': 'rname',
                      'name': 'cname',
                      'email': ['foo@example.com']}
        c_name = 'cname@rname'
        c_diff = 'diffcontent'
        html_path = '/path/to/output.html'
        duration = datetime.timedelta(seconds=3723)  # 1h 2m 3s
        output = 'simc_output_string'
        subj = 'SimulationCraft output for cname@rname'
        settings = Container()
        setattr(settings, 'SIMC_PATH', '/path/to/simc')
        setattr(settings, 'CHARACTERS', [c_settings])
        with nested(
                patch('nightly_simcraft.NightlySimcraft.send_gmail'),
                patch('nightly_simcraft.NightlySimcraft.format_message'),
                patch('nightly_simcraft.NightlySimcraft.send_local'),
        ) as (mock_gmail, mock_format, mock_local):
            mock_format.return_value = 'msgbody'
            s.settings = settings
            s.dry_run = True
            s.send_char_email(c_name,
                              c_settings,
                              c_diff,
                              html_path,
                              duration,
                              output)
        assert mocklog.info.call_args_list == [call("Sending email for character cname@rname to foo@example.com")]
        assert mocklog.warning.call_args_list == [call("DRY RUN - not actually sending email")]
        assert mock_format.call_args_list == []
        assert mock_local.call_args_list == []
        assert mock_gmail.call_args_list == []

    def test_format_message(self, mock_ns):
        bn, rc, mocklog, s, conn, lcc = mock_ns
        dest_addr = 'foo@example.com'
        subj = 'mysubj'
        c_name = 'cname@rname'
        c_diff = 'characterDiffHere'
        html_path = '/path/to/html'
        duration = datetime.timedelta(seconds=3723)  # 1h 2m 3s
        output = 'simcoutput'
        # foo
        expected = 'SimulationCraft was run for cname@rname due to the following changes:\n'
        expected += '\ncharacterDiffHere\n\n'
        expected += 'The run was completed in 1:02:03 and the HTML report is attached.\n\n'
        expected += 'SimulationCraft output: \n\nsimcoutput\n\n'
        expected += 'This run was done on nodename at 2014-01-01 00:00:00 by nightly_simcraft.py va.b.c'
        with nested(
                patch('nightly_simcraft.platform.node'),
                patch('nightly_simcraft.getpass.getuser'),
                patch('nightly_simcraft.NightlySimcraft.now'),
        ) as (mock_node, mock_user, mock_now):
            mock_node.return_value = 'nodename'
            mock_user.return_value = 'username'
            mock_now.return_value = datetime.datetime(2014, 1, 1, 0, 0, 0)
            with patch.object(s, 'VERSION', 'a.b.c'):
                res = s.format_message(dest_addr,
                                       subj,
                                       c_name,
                                       c_diff,
                                       html_path,
                                       duration,
                                       output)
            assert res == (expected, 'username@nodename')
        
    def test_make_char_name(self, mock_ns):
        """ make_character_name() tests """
        bn, rc, mocklog, s, conn, lcc = mock_ns
        assert s.make_character_name('n', 'r') == 'n@r'
        assert s.make_character_name('MyName', 'MyRealm') == 'MyName@MyRealm'
        assert s.make_character_name('sómÊñámé', 'Area 52') == 'sómÊñámé@Area52'
        
    @freeze_time("2014-01-01 01:02:03")
    def test_now(self, mock_ns):
        bn, rc, mocklog, s, conn, lcc = mock_ns
        result = s.now()
        assert result == datetime.datetime(2014, 1, 1, 1, 2, 3)

    @pytest.fixture
    def bnet_data(self):
        """ sample data returned by battlenet """
        data = {u'realm': u'Area 52', u'name': u'Jantman', u'battlegroup': u'Vindication', u'level': 100, u'lastModified': 1420861012000, u'professions': {u'primary': [{u'name': u'Tailoring', u'max': 675, u'recipes': [2385, 2386, 2387, 2392, 2393, 2394, 2395, 2396, 2397, 2399, 2401, 2402, 2406, 2963, 2964, 3755, 3757, 3813, 3839, 3840, 3841, 3842, 3843, 3845, 3848, 3850, 3852, 3855, 3859, 3861, 3865, 3866, 3871, 3914, 3915, 6521, 6690, 7623, 7624, 8465, 8467, 8483, 8489, 8758, 8760, 8762, 8764, 8766, 8770, 8772, 8774, 8776, 8791, 8799, 8804, 12044, 12045, 12046, 12048, 12049, 12050, 12052, 12053, 12055, 12061, 12065, 12067, 12069, 12070, 12071, 12072, 12073, 12074, 12076, 12077, 12079, 12082, 12088, 12092, 18401, 18402, 18403, 18406, 18407, 18409, 18410, 18411, 18413, 18414, 18415, 18416, 18417, 18420, 18421, 18423, 18424, 18437, 18438, 18441, 18442, 18444, 18446, 18449, 18450, 18451, 18453, 26745, 26746, 26764, 26765, 26770, 26771, 26772, 31460, 44950, 55898, 55899, 55900, 55901, 55902, 55903, 55904, 55906, 55907, 55908, 55910, 55911, 55913, 55914, 55919, 55920, 55921, 55922, 55923, 55924, 55925, 55941, 55943, 55995, 56000, 56001, 56002, 56003, 56007, 56008, 56010, 56014, 56015, 56018, 56019, 56020, 56021, 56022, 56023, 56024, 56025, 56026, 56027, 56028, 56029, 56030, 56031, 59582, 59583, 59584, 59585, 59586, 59587, 59588, 59589, 60969, 60971, 60990, 60993, 60994, 63742, 64729, 64730, 74964, 75247, 75248, 75249, 75250, 75251, 75252, 75253, 75254, 75255, 75256, 75257, 75258, 75259, 75260, 75261, 75264, 75265, 75268, 125496, 125497, 142960, 143011, 146925, 168835, 168837, 168838, 168839, 168840, 168841, 168842, 168843, 168844, 168852, 168853, 168854, 176058], u'rank': 627, u'id': 197, u'icon': u'trade_tailoring'}, {u'name': u'Enchanting', u'max': 675, u'recipes': [7418, 7421, 7428, 14293, 74236, 74238, 104395, 104398, 104414, 104417, 104420, 104425, 104440, 104445, 158907, 158908, 158909, 158910, 158911, 159236, 162948, 169091, 169092, 177043], u'rank': 622, u'id': 333, u'icon': u'trade_engraving'}], u'secondary': [{u'name': u'First Aid', u'max': 675, u'recipes': [3275, 102699, 172539, 172540, 172541, 172542], u'rank': 600, u'id': 129, u'icon': u'spell_holy_sealofsacrifice'}, {u'name': u'Archaeology', u'max': 0, u'recipes': [], u'rank': 0, u'id': 794, u'icon': u'trade_archaeology'}, {u'name': u'Fishing', u'max': 675, u'recipes': [], u'rank': 89, u'id': 356, u'icon': u'trade_fishing'}, {u'name': u'Cooking', u'max': 675, u'recipes': [2538, 2540, 8604, 161001, 161002], u'rank': 1, u'id': 185, u'icon': u'inv_misc_food_15'}]}, u'appearance': {u'faceVariation': 8, u'featureVariation': 2, u'hairColor': 9, u'showCloak': False, u'skinColor': 3, u'hairVariation': 8, u'showHelm': True}, u'totalHonorableKills': 0, u'class': 9, u'talents': [{u'selected': True, u'calcGlyph': u'ZWVc', u'calcSpec': u'b', u'calcTalent': u'110200.', u'talents': [{u'tier': 0, u'column': 1, u'spell': {u'id': 108370, u'castTime': u'Passive', u'description': u'Shadow Bolt, Soul Fire, Chaos Bolt, Shadowburn, Touch of Chaos, Incinerate, Haunt, and Drain Soul grant you and your pet shadowy shields that absorb a percentage of the damage they dealt for 15 sec.', u'name': u'Soul Leech', u'icon': u'warlock_siphonlife'}}, {u'tier': 1, u'column': 1, u'spell': {u'description': u"Horrifies an enemy target into fleeing, incapacitating them for 3 sec, and restores 11% of the caster's maximum health.", u'castTime': u'Instant', u'range': u'30 yd range', u'cooldown': u'45 sec cooldown', u'icon': u'ability_warlock_mortalcoil', u'id': 6789, u'name': u'Mortal Coil'}}, {u'tier': 2, u'column': 0, u'spell': {u'id': 108415, u'castTime': u'Passive', u'description': u'20% of all damage taken is split with your demon pet, and 3% of damage you deal heals you and your demon.', u'name': u'Soul Link', u'icon': u'ability_warlock_soullink'}}, {u'tier': 3, u'column': 2, u'spell': {u'description': u'Purges all Magic effects, movement impairing effects, and loss of control effects from yourself and your demon.', u'powerCost': u'20% of max health', u'castTime': u'Instant', u'cooldown': u'2 min cooldown', u'icon': u'warlock_spelldrain', u'id': 108482, u'name': u'Unbound Will'}}, {u'tier': 4, u'column': 0, u'spell': {u'id': 108499, u'castTime': u'Passive', u'description': u'You command stronger demons, replacing your normal minions. These demons deal 20% additional damage and have more powerful abilities. \n\n\n\nSpells Learned:\n\n Summon Fel Imp\n\n Summon Voidlord\n\n Summon Shivarra\n\n Summon Observer \n\n Summon Abyssal\n\n Summon Terrorguard', u'name': u'Grimoire of Supremacy', u'icon': u'warlock_grimoireofcommand'}}, {u'tier': 5, u'column': 0, u'spell': {u'id': 108505, u'castTime': u'Passive', u'description': u'Dark Soul now has 2 charges.', u'name': u"Archimonde's Darkness", u'icon': u'achievement_boss_archimonde'}}], u'glyphs': {u'major': [{u'item': 42454, u'glyph': 273, u'name': u'Glyph of Conflagrate', u'icon': u'spell_fire_fireball'}, {u'item': 0, u'glyph': 279, u'name': u'Glyph of Demon Training', u'icon': u'spell_shadow_summonfelhunter'}, {u'item': 0, u'glyph': 281, u'name': u'Glyph of Healthstone', u'icon': u'inv_stone_04'}], u'minor': [{u'item': 42457, u'glyph': 276, u'name': u'Glyph of Nightmares', u'icon': u'ability_mount_nightmarehorse'}]}, u'spec': {u'description': u'A master of chaos who calls down fire to burn and demolish enemies.', u'role': u'DPS', u'backgroundImage': u'bg-warlock-destruction', u'icon': u'spell_shadow_rainoffire', u'order': 2, u'name': u'Destruction'}}, {u'talents': [], u'glyphs': {u'major': [], u'minor': []}, u'calcTalent': u'', u'calcSpec': u'', u'calcGlyph': u''}], u'race': 5, u'calcClass': u'V', u'achievementPoints': 2225, u'gender': 0, u'stats': {u'bonusArmor': 0, u'critRating': 825, u'powerType': u'mana', u'multistrikeRating': 5.621212, u'mainHandDps': 132.29324, u'int': 3054, u'leechRatingBonus': 0.0, u'spr': 1160, u'spellCritRating': 825, u'avoidanceRating': 0.0, u'spellPower': 4234, u'rangedDps': -1.0, u'leechRating': 0.0, u'crit': 12.5, u'mastery': 37.99091, u'multistrike': 5.621212, u'versatilityDamageDoneBonus': 2.107692, u'armor': 547, u'avoidanceRatingBonus': 0.0, u'spellCrit': 12.5, u'mana5Combat': 60558.0, u'mana5': 60558.0, u'health': 237300, u'rangedDmgMax': -1.0, u'rangedDmgMin': -1.0, u'hasteRatingPercent': 4.41, u'leech': 0.0, u'versatilityDamageTakenBonus': 1.053846, u'dodge': 3.0, u'power': 160000, u'spellPen': 0, u'mainHandSpeed': 3.161, u'attackPower': 0, u'speedRating': 0.0, u'multistrikeRatingBonus': 0.621212, u'hasteRating': 441, u'masteryRating': 513, u'blockRating': 0, u'parry': 0.0, u'versatility': 274, u'parryRating': 0, u'dodgeRating': 0, u'sta': 3955, u'mainHandDmgMin': 334.0, u'speedRatingBonus': 0.0, u'mainHandDmgMax': 503.0, u'agi': 983, u'offHandDps': 0.265196, u'rangedSpeed': -1.0, u'versatilityHealingDoneBonus': 2.107692, u'offHandDmgMax': 1.0, u'haste': 4.410004, u'rangedAttackPower': 0, u'str': 550, u'offHandDmgMin': 0.0, u'block': 0.0, u'offHandSpeed': 1.916}, u'items': {u'shoulder': {u'stats': [{u'stat': 32, u'amount': 104}, {u'stat': 5, u'amount': 138}, {u'stat': 36, u'amount': 72}, {u'stat': 7, u'amount': 207}], u'name': u'Twin-Gaze Spaulders', u'tooltipParams': {u'transmogItem': 31054}, u'armor': 71, u'quality': 4, u'itemLevel': 640, u'context': u'raid-finder', u'bonusLists': [], u'id': 115997, u'icon': u'inv_shoulder_cloth_draenorlfr_c_01'}, u'averageItemLevelEquipped': 623, u'averageItemLevel': 623, u'neck': {u'stats': [{u'stat': 59, u'amount': 41}, {u'stat': 49, u'amount': 46}, {u'stat': 5, u'amount': 66}, {u'stat': 7, u'amount': 99}], u'name': u'Skywatch Adherent Locket', u'tooltipParams': {}, u'armor': 0, u'quality': 4, u'itemLevel': 592, u'context': u'quest-reward', u'bonusLists': [15], u'id': 114951, u'icon': u'inv_misc_necklace_6_0_024'}, u'trinket2': {u'stats': [{u'stat': 5, u'amount': 120}], u'name': u'Tormented Emblem of Flame', u'tooltipParams': {}, u'armor': 0, u'quality': 3, u'itemLevel': 600, u'context': u'dungeon-normal', u'bonusLists': [], u'id': 114367, u'icon': u'inv_jewelry_talisman_11'}, u'finger2': {u'stats': [{u'stat': 32, u'amount': 66}, {u'stat': 5, u'amount': 94}, {u'stat': 36, u'amount': 57}, {u'stat': 7, u'amount': 141}], u'name': u'Diamondglow Circle', u'tooltipParams': {}, u'armor': 0, u'quality': 3, u'itemLevel': 630, u'context': u'dungeon-heroic', u'bonusLists': [524], u'id': 109763, u'icon': u'inv_60dungeon_ring2d'}, u'trinket1': {u'stats': [{u'stat': 5, u'amount': 175}], u'name': u"Sandman's Pouch", u'tooltipParams': {}, u'armor': 0, u'quality': 4, u'itemLevel': 640, u'context': u'trade-skill', u'bonusLists': [525, 529], u'id': 112320, u'icon': u'inv_inscription_trinket_mage'}, u'finger1': {u'stats': [{u'stat': 40, u'amount': 54}, {u'stat': 49, u'amount': 77}, {u'stat': 5, u'amount': 103}, {u'stat': 7, u'amount': 155}], u'name': u'Solium Band of Wisdom', u'tooltipParams': {}, u'armor': 0, u'quality': 4, u'itemLevel': 640, u'context': u'quest-reward', u'bonusLists': [], u'id': 118291, u'icon': u'inv_misc_6oring_purplelv1'}, u'mainHand': {u'stats': [{u'stat': 40, u'amount': 81}, {u'stat': 5, u'amount': 139}, {u'stat': 36, u'amount': 99}, {u'stat': 7, u'amount': 208}, {u'stat': 45, u'amount': 795}], u'name': u'Staff of Trials', u'tooltipParams': {u'transmogItem': 32374}, u'armor': 0, u'quality': 3, u'itemLevel': 610, u'weaponInfo': {u'dps': 124.69697, u'damage': {u'max': 494, u'exactMax': 494.0, u'min': 329, u'exactMin': 329.0}, u'weaponSpeed': 3.3}, u'context': u'quest-reward', u'bonusLists': [], u'id': 119463, u'icon': u'inv_staff_2h_draenordungeon_c_05'}, u'chest': {u'stats': [{u'stat': 49, u'amount': 131}, {u'stat': 32, u'amount': 107}, {u'stat': 5, u'amount': 184}, {u'stat': 7, u'amount': 275}], u'name': u'Hexweave Robe of the Peerless', u'tooltipParams': {u'transmogItem': 31052}, u'armor': 94, u'quality': 4, u'itemLevel': 640, u'context': u'trade-skill', u'bonusLists': [50, 525, 538], u'id': 114813, u'icon': u'inv_cloth_draenorcrafted_d_01robe'}, u'wrist': {u'stats': [{u'stat': 32, u'amount': 63}, {u'stat': 5, u'amount': 94}, {u'stat': 36, u'amount': 63}, {u'stat': 7, u'amount': 141}], u'name': u'Bracers of Arcane Mystery', u'tooltipParams': {}, u'armor': 39, u'quality': 3, u'itemLevel': 630, u'context': u'dungeon-heroic', u'bonusLists': [524], u'id': 109864, u'icon': u'inv_cloth_draenordungeon_c_01bracer'}, u'back': {u'stats': [{u'stat': 49, u'amount': 57}, {u'stat': 32, u'amount': 66}, {u'stat': 5, u'amount': 94}, {u'stat': 7, u'amount': 141}], u'name': u'Drape of Frozen Dreams', u'tooltipParams': {}, u'armor': 44, u'quality': 3, u'itemLevel': 630, u'context': u'dungeon-heroic', u'bonusLists': [524], u'id': 109926, u'icon': u'inv_cape_draenordungeon_c_02_plate'}, u'hands': {u'stats': [{u'stat': 32, u'amount': 53}, {u'stat': 40, u'amount': 63}, {u'stat': 5, u'amount': 89}, {u'stat': 7, u'amount': 133}], u'name': u'Windshaper Gloves', u'tooltipParams': {u'transmogItem': 31050}, u'armor': 41, u'quality': 2, u'itemLevel': 593, u'context': u'quest-reward', u'bonusLists': [], u'id': 114689, u'icon': u'inv_cloth_draenorquest95_b_01glove'}, u'legs': {u'stats': [{u'stat': 49, u'amount': 101}, {u'stat': 32, u'amount': 118}, {u'stat': 5, u'amount': 167}, {u'stat': 7, u'amount': 251}], u'name': u'Lightbinder Leggings', u'tooltipParams': {u'transmogItem': 31053}, u'armor': 77, u'quality': 3, u'itemLevel': 630, u'context': u'dungeon-heroic', u'bonusLists': [524], u'id': 109807, u'icon': u'inv_cloth_draenordungeon_c_01pant'}, u'head': {u'stats': [{u'stat': 51, u'amount': 63}, {u'stat': 32, u'amount': 139}, {u'stat': 5, u'amount': 184}, {u'stat': 36, u'amount': 93}, {u'stat': 7, u'amount': 275}], u'name': u'Crown of Power', u'tooltipParams': {u'transmogItem': 31051}, u'armor': 77, u'quality': 4, u'itemLevel': 640, u'context': u'', u'bonusLists': [], u'id': 118942, u'icon': u'inv_crown_02'}, u'feet': {u'stats': [{u'stat': 32, u'amount': 70}, {u'stat': 5, u'amount': 97}, {u'stat': 36, u'amount': 57}, {u'stat': 7, u'amount': 146}], u'name': u'Windshaper Treads', u'tooltipParams': {}, u'armor': 51, u'quality': 3, u'itemLevel': 603, u'context': u'quest-reward', u'bonusLists': [171], u'id': 114684, u'icon': u'inv_cloth_draenorquest95_b_01boot'}, u'waist': {u'stats': [{u'stat': 49, u'amount': 101}, {u'stat': 40, u'amount': 76}, {u'stat': 5, u'amount': 138}, {u'stat': 7, u'amount': 207}], u'name': u'Hexweave Belt of the Harmonious', u'tooltipParams': {}, u'armor': 53, u'quality': 4, u'itemLevel': 640, u'context': u'trade-skill', u'bonusLists': [213, 525, 537], u'id': 114816, u'icon': u'inv_cloth_draenorcrafted_d_01belt'}}, u'thumbnail': u'internal-record-3676/42/119864362-avatar.jpg'}
        return data

    @pytest.fixture
    def char_data(self):
        """ sample Character data """
        data = {u'realm': u'Area 52', u'name': u'Jantman', u'battlegroup': u'Vindication', u'level': 100, u'professions': {u'primary': [{u'name': u'Tailoring', u'max': 675, u'rank': 627, u'id': 197, u'icon': u'trade_tailoring'}, {u'name': u'Enchanting', u'max': 675, u'rank': 622, u'id': 333, u'icon': u'trade_engraving'}], u'secondary': [{u'name': u'First Aid', u'max': 675, u'rank': 600, u'id': 129, u'icon': u'spell_holy_sealofsacrifice'}, {u'name': u'Archaeology', u'max': 0, u'rank': 0, u'id': 794, u'icon': u'trade_archaeology'}, {u'name': u'Fishing', u'max': 675, u'rank': 89, u'id': 356, u'icon': u'trade_fishing'}, {u'name': u'Cooking', u'max': 675, u'rank': 1, u'id': 185, u'icon': u'inv_misc_food_15'}]}, u'appearance': {u'faceVariation': 8, u'featureVariation': 2, u'hairColor': 9, u'showCloak': False, u'skinColor': 3, u'hairVariation': 8, u'showHelm': True}, u'totalHonorableKills': 0, u'class': 9, u'talents': [{u'selected': True, u'calcGlyph': u'ZWVc', u'calcSpec': u'b', u'calcTalent': u'110200.', u'talents': [{u'tier': 0, u'column': 1, u'spell': {u'castTime': u'Passive', u'description': u'Shadow Bolt, Soul Fire, Chaos Bolt, Shadowburn, Touch of Chaos, Incinerate, Haunt, and Drain Soul grant you and your pet shadowy shields that absorb a percentage of the damage they dealt for 15 sec.', u'id': 108370, u'name': u'Soul Leech', u'icon': u'warlock_siphonlife'}}, {u'tier': 1, u'column': 1, u'spell': {u'description': u"Horrifies an enemy target into fleeing, incapacitating them for 3 sec, and restores 11% of the caster's maximum health.", u'castTime': u'Instant', u'range': u'30 yd range', u'cooldown': u'45 sec cooldown', u'icon': u'ability_warlock_mortalcoil', u'id': 6789, u'name': u'Mortal Coil'}}, {u'tier': 2, u'column': 0, u'spell': {u'castTime': u'Passive', u'description': u'20% of all damage taken is split with your demon pet, and 3% of damage you deal heals you and your demon.', u'id': 108415, u'name': u'Soul Link', u'icon': u'ability_warlock_soullink'}}, {u'tier': 3, u'column': 2, u'spell': {u'description': u'Purges all Magic effects, movement impairing effects, and loss of control effects from yourself and your demon.', u'id': 108482, u'castTime': u'Instant', u'cooldown': u'2 min cooldown', u'icon': u'warlock_spelldrain', u'powerCost': u'20% of max health', u'name': u'Unbound Will'}}, {u'tier': 4, u'column': 0, u'spell': {u'castTime': u'Passive', u'description': u'You command stronger demons, replacing your normal minions. These demons deal 20% additional damage and have more powerful abilities. \n\n\n\nSpells Learned:\n\n Summon Fel Imp\n\n Summon Voidlord\n\n Summon Shivarra\n\n Summon Observer \n\n Summon Abyssal\n\n Summon Terrorguard', u'id': 108499, u'name': u'Grimoire of Supremacy', u'icon': u'warlock_grimoireofcommand'}}, {u'tier': 5, u'column': 0, u'spell': {u'castTime': u'Passive', u'description': u'Dark Soul now has 2 charges.', u'id': 108505, u'name': u"Archimonde's Darkness", u'icon': u'achievement_boss_archimonde'}}], u'glyphs': {u'major': [{u'item': 42454, u'glyph': 273, u'name': u'Glyph of Conflagrate', u'icon': u'spell_fire_fireball'}, {u'item': 0, u'glyph': 279, u'name': u'Glyph of Demon Training', u'icon': u'spell_shadow_summonfelhunter'}, {u'item': 0, u'glyph': 281, u'name': u'Glyph of Healthstone', u'icon': u'inv_stone_04'}], u'minor': [{u'item': 42457, u'glyph': 276, u'name': u'Glyph of Nightmares', u'icon': u'ability_mount_nightmarehorse'}]}, u'spec': {u'description': u'A master of chaos who calls down fire to burn and demolish enemies.', u'role': u'DPS', u'backgroundImage': u'bg-warlock-destruction', u'icon': u'spell_shadow_rainoffire', u'order': 2, u'name': u'Destruction'}}, {u'talents': [], u'glyphs': {u'major': [], u'minor': []}, u'calcTalent': u'', u'calcSpec': u'', u'calcGlyph': u''}], u'race': 5, u'calcClass': u'V', u'gender': 0, u'stats': {u'bonusArmor': 0, u'critRating': 825, u'spellCritRating': 825, u'multistrikeRating': 5.621212, u'mainHandDps': 132.29324, u'int': 3054, u'leechRatingBonus': 0.0, u'spr': 1160, u'powerType': u'mana', u'avoidanceRating': 0.0, u'spellPower': 4234, u'rangedDps': -1.0, u'leechRating': 0.0, u'crit': 12.5, u'multistrike': 5.621212, u'versatilityDamageDoneBonus': 2.107692, u'dodgeRating': 0, u'rangedSpeed': -1.0, u'armor': 547, u'avoidanceRatingBonus': 0.0, u'spellCrit': 12.5, u'mana5Combat': 60558.0, u'mana5': 60558.0, u'health': 237300, u'rangedDmgMax': -1.0, u'rangedDmgMin': -1.0, u'multistrikeRatingBonus': 0.621212, u'hasteRatingPercent': 4.41, u'leech': 0.0, u'hasteRating': 441, u'dodge': 3.0, u'power': 160000, u'spellPen': 0, u'mainHandSpeed': 3.161, u'attackPower': 0, u'speedRating': 0.0, u'parry': 0.0, u'masteryRating': 513, u'blockRating': 0, u'versatility': 274, u'parryRating': 0, u'mainHandDmgMax': 503.0, u'sta': 3955, u'mainHandDmgMin': 334.0, u'speedRatingBonus': 0.0, u'versatilityDamageTakenBonus': 1.053846, u'agi': 983, u'offHandDps': 0.265196, u'mastery': 37.99091, u'versatilityHealingDoneBonus': 2.107692, u'offHandDmgMax': 1.0, u'haste': 4.410004, u'rangedAttackPower': 0, u'str': 550, u'offHandDmgMin': 0.0, u'block': 0.0, u'offHandSpeed': 1.916}, u'items': {u'shoulder': {u'stats': [{u'stat': 32, u'amount': 104}, {u'stat': 5, u'amount': 138}, {u'stat': 36, u'amount': 72}, {u'stat': 7, u'amount': 207}], u'name': u'Twin-Gaze Spaulders', u'tooltipParams': {u'transmogItem': 31054}, u'armor': 71, u'itemLevel': 640, u'bonusLists': [], u'context': u'raid-finder', u'quality': 4, u'id': 115997, u'icon': u'inv_shoulder_cloth_draenorlfr_c_01'}, u'averageItemLevelEquipped': 623, u'averageItemLevel': 623, u'neck': {u'stats': [{u'stat': 59, u'amount': 41}, {u'stat': 49, u'amount': 46}, {u'stat': 5, u'amount': 66}, {u'stat': 7, u'amount': 99}], u'name': u'Skywatch Adherent Locket', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 592, u'bonusLists': [15], u'context': u'quest-reward', u'quality': 4, u'id': 114951, u'icon': u'inv_misc_necklace_6_0_024'}, u'trinket2': {u'stats': [{u'stat': 5, u'amount': 120}], u'name': u'Tormented Emblem of Flame', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 600, u'bonusLists': [], u'context': u'dungeon-normal', u'quality': 3, u'id': 114367, u'icon': u'inv_jewelry_talisman_11'}, u'finger2': {u'stats': [{u'stat': 32, u'amount': 66}, {u'stat': 5, u'amount': 94}, {u'stat': 36, u'amount': 57}, {u'stat': 7, u'amount': 141}], u'name': u'Diamondglow Circle', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109763, u'icon': u'inv_60dungeon_ring2d'}, u'trinket1': {u'stats': [{u'stat': 5, u'amount': 175}], u'name': u"Sandman's Pouch", u'tooltipParams': {}, u'armor': 0, u'itemLevel': 640, u'bonusLists': [525, 529], u'context': u'trade-skill', u'quality': 4, u'id': 112320, u'icon': u'inv_inscription_trinket_mage'}, u'finger1': {u'stats': [{u'stat': 40, u'amount': 54}, {u'stat': 49, u'amount': 77}, {u'stat': 5, u'amount': 103}, {u'stat': 7, u'amount': 155}], u'name': u'Solium Band of Wisdom', u'tooltipParams': {}, u'armor': 0, u'itemLevel': 640, u'bonusLists': [], u'context': u'quest-reward', u'quality': 4, u'id': 118291, u'icon': u'inv_misc_6oring_purplelv1'}, u'mainHand': {u'stats': [{u'stat': 40, u'amount': 81}, {u'stat': 5, u'amount': 139}, {u'stat': 36, u'amount': 99}, {u'stat': 7, u'amount': 208}, {u'stat': 45, u'amount': 795}], u'tooltipParams': {u'transmogItem': 32374}, u'bonusLists': [], u'armor': 0, u'itemLevel': 610, u'name': u'Staff of Trials', u'weaponInfo': {u'dps': 124.69697, u'damage': {u'max': 494, u'exactMin': 329.0, u'exactMax': 494.0, u'min': 329}, u'weaponSpeed': 3.3}, u'context': u'quest-reward', u'quality': 3, u'id': 119463, u'icon': u'inv_staff_2h_draenordungeon_c_05'}, u'chest': {u'stats': [{u'stat': 49, u'amount': 131}, {u'stat': 32, u'amount': 107}, {u'stat': 5, u'amount': 184}, {u'stat': 7, u'amount': 275}], u'name': u'Hexweave Robe of the Peerless', u'tooltipParams': {u'transmogItem': 31052}, u'armor': 94, u'itemLevel': 640, u'bonusLists': [50, 525, 538], u'context': u'trade-skill', u'quality': 4, u'id': 114813, u'icon': u'inv_cloth_draenorcrafted_d_01robe'}, u'wrist': {u'stats': [{u'stat': 32, u'amount': 63}, {u'stat': 5, u'amount': 94}, {u'stat': 36, u'amount': 63}, {u'stat': 7, u'amount': 141}], u'name': u'Bracers of Arcane Mystery', u'tooltipParams': {}, u'armor': 39, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109864, u'icon': u'inv_cloth_draenordungeon_c_01bracer'}, u'back': {u'stats': [{u'stat': 49, u'amount': 57}, {u'stat': 32, u'amount': 66}, {u'stat': 5, u'amount': 94}, {u'stat': 7, u'amount': 141}], u'name': u'Drape of Frozen Dreams', u'tooltipParams': {}, u'armor': 44, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109926, u'icon': u'inv_cape_draenordungeon_c_02_plate'}, u'hands': {u'stats': [{u'stat': 32, u'amount': 53}, {u'stat': 40, u'amount': 63}, {u'stat': 5, u'amount': 89}, {u'stat': 7, u'amount': 133}], u'name': u'Windshaper Gloves', u'tooltipParams': {u'transmogItem': 31050}, u'armor': 41, u'itemLevel': 593, u'bonusLists': [], u'context': u'quest-reward', u'quality': 2, u'id': 114689, u'icon': u'inv_cloth_draenorquest95_b_01glove'}, u'legs': {u'stats': [{u'stat': 49, u'amount': 101}, {u'stat': 32, u'amount': 118}, {u'stat': 5, u'amount': 167}, {u'stat': 7, u'amount': 251}], u'name': u'Lightbinder Leggings', u'tooltipParams': {u'transmogItem': 31053}, u'armor': 77, u'itemLevel': 630, u'bonusLists': [524], u'context': u'dungeon-heroic', u'quality': 3, u'id': 109807, u'icon': u'inv_cloth_draenordungeon_c_01pant'}, u'head': {u'stats': [{u'stat': 51, u'amount': 63}, {u'stat': 32, u'amount': 139}, {u'stat': 5, u'amount': 184}, {u'stat': 36, u'amount': 93}, {u'stat': 7, u'amount': 275}], u'name': u'Crown of Power', u'tooltipParams': {u'transmogItem': 31051}, u'armor': 77, u'itemLevel': 640, u'bonusLists': [], u'context': u'', u'quality': 4, u'id': 118942, u'icon': u'inv_crown_02'}, u'feet': {u'stats': [{u'stat': 32, u'amount': 70}, {u'stat': 5, u'amount': 97}, {u'stat': 36, u'amount': 57}, {u'stat': 7, u'amount': 146}], u'name': u'Windshaper Treads', u'tooltipParams': {}, u'armor': 51, u'itemLevel': 603, u'bonusLists': [171], u'context': u'quest-reward', u'quality': 3, u'id': 114684, u'icon': u'inv_cloth_draenorquest95_b_01boot'}, u'waist': {u'stats': [{u'stat': 49, u'amount': 101}, {u'stat': 40, u'amount': 76}, {u'stat': 5, u'amount': 138}, {u'stat': 7, u'amount': 207}], u'name': u'Hexweave Belt of the Harmonious', u'tooltipParams': {}, u'armor': 53, u'itemLevel': 640, u'bonusLists': [213, 525, 537], u'context': u'trade-skill', u'quality': 4, u'id': 114816, u'icon': u'inv_cloth_draenorcrafted_d_01belt'}}, u'thumbnail': u'internal-record-3676/42/119864362-avatar.jpg'}
        return data
