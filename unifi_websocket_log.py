#!/usr/bin/env python
"""
Script to connect to UniFi controller websocket server and print all events,
for testing.

<https://github.com/jantman/misc-scripts/blob/master/unifi_websocket_log.py>

This script uses the aiounifi package that's used in the HomeAssistant UniFi
integration, and this script is largely based on
https://github.com/Kane610/aiounifi/blob/master/aiounifi/__main__.py

REQUIREMENTS:

Python >= 3.7 (written for 3.10)
aiounifi package (written for version 35)
"""

import sys
import argparse
import logging

import asyncio
from typing import TYPE_CHECKING, Any, Callable

import aiohttp
import async_timeout

import aiounifi
from aiounifi.controller import Controller

from ssl import SSLContext, CERT_NONE, create_default_context
from aiounifi.websocket import WebsocketSignal, WebsocketState
from aiounifi.models.message import Message, MessageKey
from aiounifi.models.event import Event, EventKey

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


def signalling_callback(
    signal: WebsocketSignal, data: dict[str, Any] | WebsocketState
) -> None:
    """Receive and print events from websocket."""
    logger.warning('SIGNAL_CALLBACK %s: %s (%s)', signal, data, type(data))


def message_callback(msg: Message):
    logger.warning('MESSAGE_CALLBACK: key=%s', msg.meta.message)


def event_callback(evt: Event):
    logger.warning(
        'EVENT_CALLBACK: key=%s subsystem=%s', evt.key, evt.subsystem
    )


async def unifi_controller(
    host: str,
    username: str,
    password: str,
    port: int,
    site: str,
    session: aiohttp.ClientSession,
    sslcontext: SSLContext | None,
    callback: Callable[[WebsocketSignal, dict[str, Any] | WebsocketState], None],
) -> Controller | None:
    """Set up UniFi controller and verify credentials."""
    controller = Controller(
        host,
        username=username,
        password=password,
        port=port,
        site=site,
        websession=session,
        sslcontext=sslcontext,
        callback=callback,
    )
    controller.messages.subscribe(message_callback)
    controller.events.subscribe(event_callback)
    try:
        async with async_timeout.timeout(10):
            await controller.check_unifi_os()
            await controller.login()
        return controller
    except aiounifi.LoginRequired:
        logger.warning("Connected to UniFi at %s but couldn't log in", host)
    except aiounifi.Unauthorized:
        logger.warning("Connected to UniFi at %s but not registered", host)
    except (asyncio.TimeoutError, aiounifi.RequestError):
        logger.exception("Error connecting to the UniFi controller at %s", host)
    except aiounifi.AiounifiException:
        logger.exception("Unknown UniFi communication error occurred")
    return None


async def main(
    host: str,
    username: str,
    password: str,
    port: int,
    site: str,
) -> None:
    """CLI method for library."""
    logger.info("Starting aioUniFi")
    websession = aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    )
    sslcontext = create_default_context()
    sslcontext.check_hostname = False
    sslcontext.verify_mode = CERT_NONE
    logger.debug('Initializing unifi_controller()')
    controller = await unifi_controller(
        host=host,
        username=username,
        password=password,
        port=port,
        site=site,
        session=websession,
        sslcontext=sslcontext,
        callback=signalling_callback,
    )
    if not controller:
        logger.error("Couldn't connect to UniFi controller")
        await websession.close()
        return
    logger.debug('Initializing')
    await controller.initialize()
    logger.debug('Getting sites')
    await controller.sites()
    logger.debug('Getting site description')
    await controller.site_description()
    logger.debug('Starting websocket')
    controller.start_websocket()
    logger.debug('Loop on websocket...')
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        controller.stop_websocket()
        await websession.close()


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='UniFi controller websocket data dumper.'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument(
        "-p", "--port", type=int, default=8443,
        help='Port number (default: 8443)'
    )
    p.add_argument(
        "-s", "--site", type=str, default="default",
        help='Site name (default: default)'
    )
    p.add_argument("host", type=str)
    p.add_argument("username", type=str)
    p.add_argument("password", type=str)
    args = p.parse_args(argv)
    return args


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


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    # set logging level
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose == 1:
        set_log_info()
    logger.info(
        'Connecting to %s:%s as %s (site: %s)',
        args.host, args.port, args.username, args.site
    )
    try:
        asyncio.run(
            main(
                host=args.host,
                username=args.username,
                password=args.password,
                port=args.port,
                site=args.site,
            )
        )
    except KeyboardInterrupt:
        pass
