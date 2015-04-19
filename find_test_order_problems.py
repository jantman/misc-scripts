#!/usr/bin/env python
"""
find_test_order_problems.py
----------------------------

Script to run tests multiple times and analyze JUnit results XML, to find tests with order-dependent failures.

Runs a test command N times, capturing the results.xml
output after each run; when all runs are complete, attempts
to identify which test execution orders cause problems.
Only really useful with test runners that randomize order.

NOTE: This is currently very simple in its analysis. "Stupid"
would be an accurate descriptor. It only understands top-level
test suites (i.e. only suites, not test cases). It will also
complain if the first test that fails in multiple runs is different.

Source, Issues and Improvements
================================

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/find_test_order_problems.py>

Requirements
=============

- python 2.7+
- xunitparser (tested with 1.3.3)

Copyright
==========

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

Changelog
=========

2015-04-18 Jason Antman <jason@jasonantman.com>:
  - initial version
"""

import sys
import os
import argparse
import logging
import subprocess
import shlex

import xunitparser

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

class TestOrderAnalyzer:
    """ class to run tests and analyze results """

    def __init__(self, test_command, num_runs, results_file, until_fail=False):
        self.test_command = test_command
        if ' ' in test_command:
            self.test_command = shlex.split(test_command)
            logger.info("Test command: {t}".format(t=self.test_command))
        self.num_runs = num_runs
        self.run_until_fail = until_fail
        if self.run_until_fail:
            logger.info("Stopping tests after first failed run (with at least one success)")
        self.results_file = results_file

    def run_test(self):
        """run the test command, return True if it exited 0 or False otherwise"""
        if os.path.exists(self.results_file):
            logger.info("Removing {f}".format(f=self.results_file))
            os.remove(self.results_file)
        logger.error("Starting test run.")
        result = subprocess.call(self.test_command)
        logger.info("Test command exited {r}".format(r=result))
        if result == 0:
            return True
        return False

    def parse_results(self):
        """
        Parse the XUnit results. Return a 2-item dict:
        'result': :py:class:`xunitparser.TestResult`
        'suite': :py:class:`xunitparser.TestSuite`
        """
        if not os.path.exists(self.results_file):
            logger.error("ERROR: results file does not exist.")
            return None
        ts, r = xunitparser.parse(open(self.results_file))
        return {'result': r, 'suite': ts}

    def run_all_tests(self):
        """
        Run all tests. Return a dict with keys 'passed' and 'failed',
        with each value a list of :py:class:`xunitparser.TestSuite`
        """
        results = {'failed': [], 'passed': []}
        for i in xrange(0, self.num_runs):
            logger.debug("Starting test session {i}".format(i=i))
            test_succeeded = self.run_test()
            parsed = self.parse_results()
            if not test_succeeded or len(parsed['result'].failures) > 0 or len(parsed['result'].errors) > 0:
                results['failed'].append(parsed['suite'])
            else:
                results['passed'].append(parsed['suite'])
            if self.run_until_fail and len(results['passed']) > 0 and len(results['failed']) > 0:
                logger.info("Stopping test runs; have at least one each of failed and passed runs")
                break
        return results

    def analyze_results(self, results):
        """very simple results analysis"""
        first_fail = set() # first test to fail
        pre_fail = set() # tests that always succeeded before failure
        post_fail = set() # tests that always succeeded after failure
        always_pre_fail = set() # tests that always succeeded before failure
        always_post_fail = set() # tests that always succeeded after failure
        before_fail = set() # test directly before failure
        # iterate over the test runs we did
        print("Analyzing {f} failed and {p} passed test runs...".format(
            f=len(results['failed']),
            p=len(results['passed'])
        ))
        for test_run in results['failed']:
            failed = False
            tmp_first_fail = None
            tmp_pre_fail = []
            tmp_post_fail = []
            tmp_before_fail = []
            last_test = ''
            # iterate over the test cases in this run
            for testcase in test_run:
                if testcase.result == 'success':
                    if failed:
                        tmp_post_fail.append(testcase.methodname)
                    else:
                        tmp_pre_fail.append(testcase.methodname)
                    last_test = testcase.methodname
                    continue
                # else a failure
                if failed:
                    # this is a subsequent failure; done with cases in this run
                    last_test = testcase.methodname
                    continue
                # the first failure
                tmp_first_fail = testcase.methodname
                tmp_before_fail = last_test
                last_test = testcase.methodname
                failed = True
            first_fail.add(tmp_first_fail)
            before_fail.add(tmp_before_fail)
            always_pre_fail = set(always_pre_fail).intersection(tmp_pre_fail)
            always_post_fail = set(always_post_fail).intersection(tmp_post_fail)
            pre_fail.update(tmp_pre_fail)
            post_fail.update(tmp_post_fail)
        print("\n\nAnalysis of {l} failed test runs:".format(l=len(results['failed'])))
        print("Tests that failed first:")
        for x in first_fail:
            print("\t" + x)
        print("")
        print("Tests immediately before failure:")
        for x in before_fail:
            print("\t" + x)
        print("")
        print("Tests that **always** succeeded before first failure:")
        for x in always_pre_fail:
            print("\t" + x)
        print("")
        print("All tests that succeeded before first failure:")
        for x in pre_fail:
            print("\t" + x)
        print("")
        print("Tests that **always** succeeded after first failure:")
        for x in always_post_fail:
            print("\t" + x)
        print("")
        print("All tests that succeeded after first failure:")
        for x in post_fail:
            print("\t" + x)

    def run(self):
        """main entry point - run commands, collect and analyze results"""
        logger.info("Running tests...")
        results = self.run_all_tests()
        if len(results['failed']) < 1:
            logger.error("ERROR - did not get any failed tests in {n} runs; "
                         "try increasing the run count..".format(n=self.num_runs))
            raise SystemExit(1)
        self.analyze_results(results)

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('test_command', type=str, help='test command to run')
    p.add_argument('-n', '--num-runs', dest='num_runs', action='store',
                   type=int, default=10, help='number of times to run tests')
    p.add_argument('-u', '--until-fail', dest='until_fail', action='store_true',
                   default=False,
                   help='stop running tests once we have a failed run (and at least one success)')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')
    p.add_argument('-r', '--results-file', dest='results_file', action='store',
                   type=str, default='results.xml',
                   help='results XML file name; default: results.xml')
    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif verbose > 0:
        logger.setLevel(logging.INFO)

    runner = TestOrderAnalyzer(args.test_command, args.num_runs, args.results_file, until_fail=args.until_fail)
    runner.run()
