#!/usr/bin/env python
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
from mock import MagicMock, call, patch, Mock
from contextlib import nested
import sys
from surrogate import surrogate

import battlenet
import nightly_simcraft


class Container:
    pass


class Test_NightlySimcraft:

    @pytest.fixture
    def mock_ns(self):
        bn = MagicMock(spec_set=battlenet.Connection)
        rc = Mock()
        mocklog = MagicMock(spec_set=logging.Logger)
        with nested(
                patch('nightly_simcraft.battlenet.Connection', bn),
                patch('nightly_simcraft.NightlySimcraft.read_config', rc),
        ) as (bnp, rcp):
            s = nightly_simcraft.NightlySimcraft(verbose=2, logger=mocklog)
        return (bn, rc, mocklog, s)

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
        bn, rc, mocklog, s = mock_ns
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
        bn, rc, mocklog, s = mock_ns
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
        bn, rc, mocklog, s = mock_ns
        mock_settings = Container()
        setattr(mock_settings, 'DEFAULT_SIMC', 'foo')
        setattr(s, 'settings', mock_settings)
        with pytest.raises(SystemExit) as excinfo:
            res = s.validate_config()
        assert excinfo.value.code == 1
        assert mocklog.error.call_args_list == [call("ERROR: Settings file must define CHARACTERS list")]

    def test_validate_config_characters_not_list(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
        mock_settings = Container()
        setattr(mock_settings, 'DEFAULT_SIMC', 'foo')
        setattr(mock_settings, 'CHARACTERS', 'foo')
        setattr(s, 'settings', mock_settings)
        with pytest.raises(SystemExit) as excinfo:
            res = s.validate_config()
        assert excinfo.value.code == 1
        assert mocklog.error.call_args_list == [call("ERROR: Settings file must define CHARACTERS list")]

    def test_validate_config_characters_empty(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
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
        bn, rc, mocklog, s = mock_ns
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
        bn, rc, mocklog, s = mock_ns
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
        bn, rc, mocklog, s = mock_ns
        char = {'realm': 'rname', 'name': 'cname'}
        result = s.validate_character(char)
        assert result is True

    def test_validate_character_notdict(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
        char = 'realm'
        mocklog.debug.reset_mock()
        result = s.validate_character(char)
        assert mocklog.debug.call_args_list == [call('Character is not a dict')]
        assert result is False

    def test_validate_character_no_realm(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
        char = {'name': 'cname'}
        mocklog.debug.reset_mock()
        result = s.validate_character(char)
        assert mocklog.debug.call_args_list == [call("'realm' not in char dict")]
        assert result is False

    def test_validate_character_no_char(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
        char = {'realm': 'rname'}
        mocklog.debug.reset_mock()
        result = s.validate_character(char)
        assert mocklog.debug.call_args_list == [call("'name' not in char dict")]
        assert result is False

    def test_run(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
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
            mock_chc.return_value = True
            mock_validate.return_value = True
            mock_get_bnet.return_value = {}
            s.run()
        assert mocklog.debug.call_args_list == [call("Doing character: nameone@realmone")]
        assert mock_validate.call_args_list == [call(chars[0])]
        assert mock_get_bnet.call_args_list == [call('realmone', 'nameone')]
        assert mock_do_char.call_args_list == [call(chars[0])]
        assert mock_chc.call_args_list == [call(chars[0], {})]

    def test_run_invalid_character(self, mock_ns):
        bn, rc, mocklog, s = mock_ns
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
            mock_chc.return_value = True
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
        bn, rc, mocklog, s = mock_ns
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
        bn, rc, mocklog, s = mock_ns
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
            mock_chc.return_value = False
            mock_validate.return_value = True
            mock_get_bnet.return_value = {}
            s.run()
        assert mocklog.debug.call_args_list == [call("Doing character: nameone@realmone")]
        assert mock_validate.call_args_list == [call(chars[0])]
        assert mock_get_bnet.call_args_list == [call('realmone', 'nameone')]
        assert mock_do_char.call_args_list == []
        assert mock_chc.call_args_list == [call(chars[0], {})]

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
