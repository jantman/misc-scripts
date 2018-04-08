#!/home/jantman/venvs/foo/bin/python
"""
xb3_to_graphite.py
===================

Script to pull stats from Comcast/Xfinity XB3 ScientificAtlanta DPC-3941T
and push them to Graphite.

Tested With
-----------

* XB3 Scientific-Atlanta DPC3941T rev 1.0 running DPC3941_2.5p2s1_PROD_sey

Requirements
------------

- phantomjs (tested with 2.1.1)
- selenium (``pip install selenium``; tested with 2.42.1)

Usage
-----

Export your modem username and password as ``MODEM_USER`` and
``MODEM_PASSWORD`` environment variables, respectively. See
``xb3_to_graphite.py -h`` for further information.

License
-------

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/xb3_to_graphite.py>

CHANGELOG
---------

2017-06-09 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import logging
import sys
import argparse
import re
import socket
import os
import time
import codecs
from hashlib import md5

try:
    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.desired_capabilities import \
        DesiredCapabilities
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    sys.stderr.write("Error importing selenium - 'pip install selenium'\n")
    raise SystemExit(1)

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

# suppress selenium DEBUG logging
selenium_log = logging.getLogger('selenium')
selenium_log.setLevel(logging.INFO)
selenium_log.propagate = True


class GraphiteSender(object):

    NUM_PER_FLUSH = 20
    FLUSH_SLEEP_SEC = 3

    def __init__(self, host, port, prefix, dry_run=False):
        self.host = host
        self.port = port
        self._prefix = prefix
        self._dry_run = dry_run
        self._send_queue = []
        logger.info('Graphite data will send to %s:%s with prefix: %s.',
                    host, port, prefix)

    def _graphite_send(self, send_str):
        """
        Send data to graphite

        :param send_str: data string to send
        :type send_str: str
        """
        if self._dry_run:
            logger.warning('DRY RUN - Would send to graphite:\n%s', send_str)
            return
        logger.debug('Opening socket connection to %s:%s', self.host, self.port)
        sock = socket.create_connection((self.host, self.port), 10)
        logger.debug('Sending data: "%s"', send_str)
        sock.sendall(send_str)
        logger.info('Data sent to Graphite')
        sock.close()

    def _clean_name(self, metric_name):
        """
        Return a graphite-safe metric name.

        :param metric_name: original metric name
        :type metric_name: str
        :return: graphite-safe metric name
        :rtype: str
        """
        metric_name = metric_name.lower()
        newk = re.sub(r'[^\\.A-Za-z0-9_-]', '_', metric_name)
        if newk != metric_name:
            logger.debug('Cleaned metric name from "%s" to "%s"',
                         metric_name, newk)
        return newk

    def send_data(self, data):
        """
        Queue data to send to graphite. Flush at each given interval.

        :param data: list of data dicts.
        :type data: list
        """
        if isinstance(data, type({})):
            data = [data]
        for d in data:
            ts = d.get('ts', int(time.time()))
            for k in sorted(d.keys()):
                if k == 'ts':
                    continue
                self._send_queue.append((
                    '%s.%s' % (self._prefix, self._clean_name(k)),
                    d[k],
                    ts
                ))
        if len(self._send_queue) >= self.NUM_PER_FLUSH:
            self.flush()

    def flush(self):
        """
        Flush data to Graphite
        """
        logger.debug('Flushing Graphite queue...')
        while len(self._send_queue) > 0:
            send_str = ''
            for i in range(0, self.NUM_PER_FLUSH):
                try:
                    tup = self._send_queue.pop(0)
                except IndexError:
                    break
                send_str += "%s %s %d\n" % (tup[0], tup[1], tup[2])
            if send_str == '':
                return
            self._graphite_send(send_str)
            time.sleep(self.FLUSH_SLEEP_SEC)


class XB3ToGraphite(object):

    def __init__(self, modem_ip, modem_user, modem_passwd,
                 graphite_host='127.0.0.1', graphite_port=2003, dry_run=False,
                 graphite_prefix='xb3', selenium_debug=False,
                 browser_name='phantomjs'):
        """
        XB3 to Graphite sender

        :param modem_ip: modem IP address
        :type modem_ip: str
        :param modem_user: modem login username
        :type modem_user: str
        :param modem_passwd: modem login password
        :type modem_passwd: sre
        :param graphite_host: graphite server IP or hostname
        :type graphite_host: str
        :param graphite_port: graphite line receiver port
        :type graphite_port: int
        :param dry_run: whether to actually send metrics or just print them
        :type dry_run: bool
        :param graphite_prefix: graphite metric prefix
        :type graphite_prefix: str
        :param selenium_debug: if True, screenshot every page to ./
        :type selenium_debug: bool
        :param browser_name: name of browser to use
        :type browser_name: str
        """
        self.graphite = GraphiteSender(
            graphite_host, graphite_port, graphite_prefix,
            dry_run=dry_run
        )
        self.dry_run = dry_run
        self.modem_ip = modem_ip
        self.user = modem_user
        self.passwd = modem_passwd
        self.selenium_debug = selenium_debug
        self.browser_name = browser_name

    def run(self):
        getter = XB3StatsGetter(
            self.modem_ip, self.user, self.passwd, self.selenium_debug,
            browser_name=self.browser_name
        )
        stats = getter.get_stats()
        self.graphite.send_data(stats)
        self.graphite.flush()


class XB3StatsGetter(object):

    TIME_INTERVAL_RE = re.compile(r'^([0-9]+)([dhms])$')

    def __init__(self, ip, user, passwd, debug=False, browser_name='phantomjs'):
        """
        :param ip: modem IP address
        :type ip: str
        :param user: modem login username
        :type user: str
        :param passwd: modem login passwd
        :type passwd: str
        :param debug: if True, screenshot every page to `./`
        :type debug: bool
        :param browser_name: name of browser to use
        :type browser_name: str
        """
        logger.debug('Initializing XB3StatsGetter ip=%s user=%s', ip, user)
        self.ip = ip
        self.username = user
        self.password = passwd
        self.base_url = 'http://%s/' % self.ip
        self._screenshot = debug
        self._screenshot_num = 1
        self.user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:33.0) ' \
                          'Gecko/20100101 Firefox/33.0'
        logger.debug('Getting browser instance...')
        self.browser = self.get_browser(browser_name=browser_name)

    def get_stats(self):
        """
        Get statistics from modem; return a dict

        :return: stats
        :rtype: dict
        """
        stats = self._get_public_stats()
        try:
            self._do_login()
            status = self._identify_system()
            stats.update(self._get_stats())
            self.browser.quit()
        except Exception:
            self.browser.quit()
            logger.critical('Error getting stats', exc_info=True)
        logger.debug('stats: %s', stats)
        return stats

    def _get_stats(self):
        stats = self._get_at_a_glance()
        stats.update(self._get_comcast())
        return stats

    def _identify_system(self):
        self.get(self.base_url + 'hardware.php')
        self.wait_for_page_load()
        self.do_screenshot()
        status = self._form_row_to_dict(self.browser)
        logger.debug('Hardware: %s', status)
        self.get(self.base_url + 'software.php')
        self.wait_for_page_load()
        self.do_screenshot()
        status.update(self._form_row_to_dict(self.browser))
        logger.info('System information: %s', status)
        return status

    def _get_comcast(self):
        stats = {}
        self.get(self.base_url + 'comcast_network.php')
        self.wait_for_page_load()
        self.do_screenshot()
        modules = self.browser.find_elements_by_class_name('module')
        for module in modules:
            logger.debug('module: %s', module)
            t = self._try_find(module, By.TAG_NAME, 'table')
            if t is None:
                data = self._form_row_to_dict(module)
                title = self._try_find(module, By.TAG_NAME, 'h2').text
                logger.debug('t is None; title=%s data=%s', title, data)
                stats.update(
                    self._handle_comcast_network_module(
                        title, data
                    )
                )
            else:
                data = self._table_to_dict(t)
                logger.debug('t is NOT None; data: %s', data)
                stats.update(
                    self._handle_comcast_network_module(
                        data['title'], data['data']
                    )
                )
        return stats

    def _handle_comcast_network_module(self, title, data):
        res = {}
        if title.strip() == 'Cable Modem':
            if 'Serial Number' in data:
                res['cable_modem.serial_number'] = int(data['Serial Number'])
            if 'Download Version' in data:
                res['cable_modem.serial_number_numeric'] = self.str_to_numeric(
                    data['Download Version']
                )
                res['cable_modem.serial_number_len'] = len(
                    data['Download Version']
                )
            res['cable_modem.boot_ver'] = self.str_to_numeric(
                data['BOOT Version']
            )
            res['cable_modem.hw_ver'] = self.str_to_numeric(data['HW Version'])
            res['cable_modem.core_ver'] = self.str_to_numeric(
                data['Core Version']
            )
        elif title.strip() == 'Initialization Procedure':
            for k, v in data.iteritems():
                val = 0
                if v == 'Complete':
                    val = 1
                name = k.lower()
                res['initialization.%s' % name] = val
        elif title.strip() == 'XFINITY Network':
            res['xfinity_network.internet_is_active'] = 0
            if data.get('Internet', '') == 'Active':
                res['xfinity_network.internet_is_active'] = 1
            res['xfinity_network.wan_ip_numerics'] = self.str_to_numeric(
                data['WAN IP Address (IPv4)']
            )
            res['xfinity_network.dhcp_lease_remaining_seconds.' \
                'ipv4'] = self._time_str_to_int_seconds(
                data['DHCP Lease Expire Time (IPv4)']
            )
            res['xfinity_network.sys_uptime_seconds' \
                ''] = self._time_str_to_int_seconds(data['System Uptime'])
        elif title.strip() == "Upstream\nChannel Bonding Value":
            table = {r['title']: r['elems'] for r in data}
            logger.debug('UPSTREAM: %s', table)
            for idx, chan in enumerate(table['Index']):
                if table['Lock Status'][idx] == 'Locked':
                    res['upstream.%s.locked' % chan] = 1
                else:
                    res['upstream.%s.locked' % chan] = 0
                res['upstream.%s.power_dBmV' % chan] = float(
                    table['Power Level'][idx].lower().replace(
                        'dbmv', ''
                    ).strip()
                )
                res['upstream.%s.frequency_MHz' % chan] = float(
                    table['Frequency'][idx].lower().replace('mhz', '').strip()
                )
                res['upstream.%s.sym_rate_ksym_sec' % chan] = float(
                    table['Symbol Rate'][idx].lower().replace(
                        'ksym/sec', ''
                    ).strip()
                )
        elif title.strip() == "Downstream\nChannel Bonding Value":
            table = {r['title']: r['elems'] for r in data}
            logger.debug('DOWNSTREAM: %s', table)
            for idx, chan in enumerate(table['Index']):
                if table['Lock Status'][idx] == 'Locked':
                    res['downstream.%s.locked' % chan] = 1
                else:
                    res['downstream.%s.locked' % chan] = 0
                res['downstream.%s.power_dBmV' % chan] = float(
                    table['Power Level'][idx].lower().replace(
                        'dbmv', ''
                    ).strip()
                )
                res['downstream.%s.frequency_MHz' % chan] = float(
                    table['Frequency'][idx].lower().replace('mhz', '').strip()
                )
                res['downstream.%s.snr_db' % chan] = float(
                    table['SNR'][idx].lower().replace('db', '').strip()
                )
        elif title.strip() == "CM Error Codewords":
            table = {r['title']: r['elems'] for r in data}
            logger.debug('CM Error Codewords: %s', table)
            for idx, corr in enumerate(table['Correctable Codewords']):
                chan = idx + 1
                res['cm_error_codewords.%s.correctable' % chan] = float(corr)
                res['cm_error_codewords.%s.uncorrectable' % chan] = float(
                    table['Uncorrectable Codewords'][idx]
                )
                res['cm_error_codewords.%s.unerrored' % chan] = float(
                    table['Unerrored Codewords'][idx]
                )
        else:
            logger.warning(
                'comcast_network page unknown module/section: \'%s\'', title
            )
        return {'comcast_network.%s' % k: res[k] for k in res}

    def str_to_numeric(self, s):
        """
        Return an integer of all the digits in a string. Really just used to
        try and tell if a version string changes.
        """
        return int(re.sub(r'[^0-9]', '', s))

    def _get_at_a_glance(self):
        stats = {}
        self.get(self.base_url + 'at_a_glance.php')
        self.wait_for_page_load()
        self.do_screenshot()
        devices = self.browser.find_element_by_xpath(
            '//div[@id="internet-usage"]').find_elements_by_class_name('form-row')
        stats['connected_devices.count'] = len(devices)
        br_en = self.browser.find_element_by_xpath(
            '//a[@title="Bridge Mode:Disable bridge mode"]'
        )
        if br_en.get_attribute('aria-checked') == 'true':
            stats['status.bridge_mode_enabled'] = 0
        else:
            stats['status.bridge_mode_enabled'] = 1
        return stats

    def _get_public_stats(self):
        """
        Get stats that we can access without logging in.

        :return: stats
        :rtype: dict
        """
        # TBD - looks like a pain to parse
        return {}

    def _do_login(self):
        self.get(self.base_url)
        logger.info('Logging in (%s)', self.browser.current_url)
        self.wait_for_page_load()
        self.do_screenshot()
        if 'xfinity.com' not in self.browser.page_source:
            raise RuntimeError('xfinity.com not in page source!')
        try:
            u = self.browser.find_element_by_id('username')
            u.clear()
            u.send_keys(self.username)
        except:
            logger.critical('Unable to find username input box!', exc_info=True)
            self.do_screenshot()
        try:
            p = self.browser.find_element_by_id('password')
            p.clear()
            p.send_keys(self.password)
        except:
            logger.critical('Unable to find passwd input box!', exc_info=True)
            self.error_screenshot()
            raise RuntimeError("Unable to find passwd input.")
        try:
            btn = self.browser.find_element_by_xpath('//input[@value="Login"]')
        except:
            logger.critical('Unable to find Login button!', exc_info=True)
            self.error_screenshot()
            raise RuntimeError("Unable to find Login button.")
        logger.debug('Clicking Login button')
        oldurl = self.browser.current_url
        btn.click()
        self.do_screenshot()
        count = 0
        while self.browser.current_url == oldurl:
            self.do_screenshot()
            count += 1
            if count > 10:
                self.error_screenshot()
                raise RuntimeError("Login button clicked but no redirect")
            logger.info('Sleeping 1s for redirect after login button click')
            time.sleep(1)
        self.wait_for_page_load()
        self.do_screenshot()
        if self.browser.current_url != self.base_url + 'at_a_glance.php':
            raise RuntimeError('Got unexpected URL: %s' %
                               self.browser.current_url)
        logger.debug('Login successful!')

    def do_screenshot(self):
        """take a debug screenshot"""
        if not self._screenshot:
            return
        fname = os.path.join(
            os.getcwd(), '{n}.png'.format(n=self._screenshot_num)
        )
        self.browser.get_screenshot_as_file(fname)
        logger.debug(
            "Screenshot: {f} of: {s}".format(
                f=fname,
                s=self.browser.current_url
            )
        )
        self._screenshot_num += 1

    def error_screenshot(self, fname=None):
        if fname is None:
            fname = os.path.join(os.getcwd(), 'webdriver_fail.png')
        self.browser.get_screenshot_as_file(fname)
        logger.error("Screenshot saved to: {s}".format(s=fname))
        logger.error("Page title: %s", self.browser.title)
        html_path = os.path.join(os.getcwd(), 'webdriver_fail.html')
        source = self.browser.execute_script(
            "return document.getElementsByTagName('html')[0].innerHTML"
        )
        with codecs.open(html_path, 'w', 'utf-8') as fh:
            fh.write(source)
        logger.error('Page source saved to: %s', html_path)

    def _time_str_to_int_seconds(self, s):
        orig = s
        # normalize time
        s = s.replace('days', 'd:')
        s = re.sub(r'\s', '', s)
        num_sec = 0
        for part in s.split(':'):
            m = self.TIME_INTERVAL_RE.match(part)
            if m is None:
                next
            num = int(m.group(1))
            i = m.group(2)
            if i == 's':
                num_sec += num
            elif i == 'm':
                num_sec += num * 60
            elif i == 'h':
                num_sec += num * 3600
            elif i == 'd':
                num_sec += num * 86400
        logger.debug('Parsed time string "%s" to %d seconds', orig, num_sec)
        return num_sec

    def _table_to_dict(self, tbl):
        res = {}
        data = []
        thead = self._try_find(tbl, By.TAG_NAME, 'thead')
        if thead is not None:
            res['title'] = thead.text
        tbody = self._try_find(tbl, By.TAG_NAME, 'tbody')
        if tbody is None:
            tbody = tbl
        for tr in tbody.find_elements_by_tag_name('tr'):
            elems = []
            for td in tr.find_elements_by_tag_name('td'):
                elems.append(td.text)
            th = self._try_find(tr, By.TAG_NAME, 'th', only_one=False)
            if th is not None and len(th) == 1:
                data.append({'title': th[0].text, 'elems': elems})
            else:
                data.append(elems)
        res['data'] = data
        return res

    def _form_row_to_dict(self, elem):
        res = {}
        for row in elem.find_elements_by_class_name('form-row'):
            name = row.find_element_by_class_name('readonlyLabel').text.strip(
                ''
            ).strip(':')
            val = row.find_element_by_class_name('value').text.strip('')
            res[name] = val
        return res

    def _try_find(self, elem, by, value, only_one=True):
        if only_one:
            func = elem.find_element
        else:
            func = elem.find_elements
        logger.debug('Trying to find "%s" by %s on %s', value, by, elem)
        try:
            res = func(by, value)
            assert res is not None
        except Exception as ex:
            logger.debug('Try find failed: %s', ex)
            return None
        return res

    def get(self, url):
        """logging wrapper around browser.get"""
        logger.info('GET %s', url)

        self.browser.get(url)
        for x in range(0, 5):
            try:
                WebDriverWait(self.browser, 15).until(
                    lambda x: self.browser.current_url != 'about:blank'
                )
                break
            except Exception:
                logger.warning('GET %s failed; trying again', url)
            self.browser.get(url)
            time.sleep(2)
        else:
            self.error_screenshot()
            raise RuntimeError('GET %s failed' % url)

    def get_browser(self, browser_name='phantomjs'):
        """get a webdriver browser instance """
        if browser_name == 'firefox':
            logger.debug("getting Firefox browser (local)")
            if 'DISPLAY' not in os.environ:
                logger.debug("exporting DISPLAY=:0")
                os.environ['DISPLAY'] = ":0"
            browser = webdriver.Firefox()
        elif browser_name == 'chrome':
            logger.debug("getting Chrome browser (local)")
            browser = webdriver.Chrome()
        elif browser_name == 'chrome-headless':
            logger.debug('getting Chrome browser (local) with --headless')
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            browser = webdriver.Chrome(chrome_options=chrome_options)
        elif browser_name == 'phantomjs':
            logger.debug("getting PhantomJS browser (local)")
            dcap = dict(DesiredCapabilities.PHANTOMJS)
            dcap["phantomjs.page.settings.userAgent"] = self.user_agent
            args = [
                '--ssl-protocol=any',
                '--ignore-ssl-errors=true',
                '--web-security=false'
            ]
            browser = webdriver.PhantomJS(
                desired_capabilities=dcap, service_args=args
            )
            browser.set_window_size(1024, 768)
        else:
            raise SystemExit(
                "ERROR: browser type must be one of 'firefox', 'chrome', "
                "'chrome-headless' or 'phantomjs', not '{b}'".format(
                b=browser_name
            ))
        logger.debug("returning browser")
        return browser

    def doc_readystate_is_complete(self, _):
        """ return true if document is ready/complete, false otherwise """
        result_str = self.browser.execute_script("return document.readyState")
        if result_str == "complete":
            return True
        return False

    def wait_for_ajax_load(self, timeout=20):
        """
        Function to wait for an ajax event to finish and trigger page load.

        Pieced together from
        http://stackoverflow.com/a/15791319

        timeout is in seconds
        """
        WebDriverWait(self.browser, timeout).until(
            self.doc_readystate_is_complete
        )
        return True

    def wait_for_page_load(self, timeout=20):
        """
        Function to wait for page load.

        timeout is in seconds
        """
        self.wait_for_ajax_load(timeout=timeout)
        count = 0
        while len(self.browser.page_source) < 30:
            if count > 20:
                self.error_screenshot()
                raise RuntimeError("Waited 20s for page source to be more "
                                   "than 30 bytes, but still too small...")
            count += 1
            logger.debug('Page source is only %d bytes; sleeping',
                         len(self.browser.page_source))
            time.sleep(1)


def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(
        description='Get stats from XB3 modem, push to graphite'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-P', '--graphite-prefix', action='store', type=str,
                   dest='prefix', default='xb3',
                   help='graphite metric prefix')
    p.add_argument('-H', '--graphite-host', dest='graphite_host', type=str,
                   action='store', default='127.0.0.1',
                   help='graphite IP or hostname')
    p.add_argument('-p', '--graphite-port', dest='graphite_port', type=int,
                   action='store', default=2003,
                   help='graphite line recevier port')
    p.add_argument('-i', '--ip', dest='modem_ip', action='store', type=str,
                   default='10.0.0.1',
                   help='Modem IP address (default: 10.0.0.1')
    p.add_argument('-S', '--screenshot', dest='screenshot', action='store_true',
                   default=False, help='screenshot every page for debugging')
    browsers = ['firefox', 'chrome', 'chrome-headless', 'phantomjs']
    p.add_argument('-b', '--browser-name', dest='browser_name', type=str,
                   default='phantomjs', choices=browsers,
                   help='browser to use; one of: %s' % browsers)
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()
    user = os.environ.get('MODEM_USER', None)
    if user is None:
        raise SystemExit('export MODEM_USER env var')
    passwd = os.environ.get('MODEM_PASSWORD', None)
    if passwd is None:
        raise SystemExit('export MODEM_PASSWORD env var')
    XB3ToGraphite(
        args.modem_ip, user, passwd, dry_run=args.dry_run,
        graphite_prefix=args.prefix, graphite_host=args.graphite_host,
        graphite_port=args.graphite_port, selenium_debug=args.screenshot,
        browser_name=args.browser_name
    ).run()
