#!/usr/bin/env python
"""
Though they're often overlooked for small, single file programs/scripts,
automated unit tests greatly speed up both development and troubleshooting.

This is a test script for my skeleton.py generic Python script skeleton,
usable with py.test. It can also serve as a generic example of how to
use py.test to test a standalone Python script (i.e. not in a package).

Requirements
=============

* pytest
* mock
* (optional) pytest-cov
* (optional) pep8, pytest-pep8

Install these with:

    pip install pytest mock

Install the optional dependencies with:

    pip install pytest-cov pep8 pytest-pep8

Usage
======

To just run the tests (with verbose output):

    py.test -vv test_skeleton.py

To also run PEP8 style checking:

    py.test -vv --pep8 test_skeleton.py skeleton.py

The pep8 test requires that we also specify skeleton.py on the command line, to check it.
You may want to ignore some PEP8 checks that may be commonly violated, such as E501 (line
length of maximum 80 characters) or relax them a bit. To do so, in the same directory as
this file, create a ``pytest.ini`` file with the appropriate content, e.g.:

    [pytest]
    pep8maxlinelength = 99

To also print a coverage report (requires `pytest-cov`):

    py.test -vv --pep8 --cov-report term-missing --cov=skeleton test_skeleton.py skeleton.py

To generate a nicely-readable HTML coverage report, use ``--cov-report html``.

You'll probably also want to include a coverage configuration file; add
``--cov-config .coveragerc`` to the command line, and create ``.coveragerc``
as desired, e.g.:

    [run]
    branch = True

    [report]
    exclude_lines =
        # this cant ever be run by py.test, but it just calls one function,
        # so ignore it
        if __name__ == .__main__.:

Information
============

The latest version of this script is available at:
<https://github.com/jantman/misc-scripts/blob/master/test_skeleton.py>

Copyright 2015 Jason Antman <jason@jasonantman.com>
  <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2015-01-10 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import pytest
import skeleton
import logging
from mock import MagicMock, call, patch


class Test_SimpleScript:
    """
    this class tests skeleton.py's SimpleScript class
    there's no reason they both have to be classes, but once again,
    this is just done as an example
    """

    def test_init(self):
        """ test SimpleScript.init() """
        s = skeleton.SimpleScript()
        assert s.dry_run is False
        assert type(s.logger) == logging.Logger
        assert s.logger.level == logging.NOTSET

    def test_init_logger(self):
        """ test SimpleScript.init() with specified logger """
        m = MagicMock(spec_set=logging.Logger)
        s = skeleton.SimpleScript(logger=m)
        assert s.logger == m

    def test_init_dry_run(self):
        """ test SimpleScript.init() with dry_run=True """
        s = skeleton.SimpleScript(dry_run=True)
        assert s.dry_run is True

    def test_init_verbose(self):
        """ test SimpleScript.init() with verbose=1 """
        s = skeleton.SimpleScript(verbose=1)
        assert s.logger.level == logging.INFO

    def test_init_debug(self):
        """ test SimpleScript.init() with verbose=2 """
        s = skeleton.SimpleScript(verbose=2)
        assert s.logger.level == logging.DEBUG

    def test_run(self, capsys):
        """ test run method """
        m = MagicMock(spec_set=logging.Logger)
        s = skeleton.SimpleScript(logger=m)
        s.run()
        assert m.info.call_args_list == [call("info-level log message")]
        assert m.debug.call_args_list == [call("debug-level log message")]
        assert m.error.call_args_list == [call("error-level log message")]
        out, err = capsys.readouterr()
        assert out == "run.\n"


def test_parse_argv():
    """ test skeleton.py parse_argv() """
    argv = ['-d', '-vv']
    args = skeleton.parse_args(argv)
    assert args.dry_run is True
    assert args.verbose == 2
