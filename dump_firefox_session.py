#!/usr/bin/env python
# LZ4 logic taken from: https://gist.github.com/Tblue/62ff47bef7f894e92ed5
#       Copyright (c) 2015, Tilman Blumenbach

import json
import sys

try:
    import lz4.block
except ImportError:
    sys.stderr.write('Please "pip install lz4"\n')
    raise SystemExit(1)


class MozLz4aError(Exception):
    pass


class InvalidHeader(MozLz4aError):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


def decompress(file_obj):
    if file_obj.read(8) != b"mozLz40\0":
        raise InvalidHeader("Invalid magic number")
    return lz4.block.decompress(file_obj.read())


def dump_session_js(fpath):
    with open(fpath, 'r') as fh:
        sess = json.loads(fh.read())
    for window in sess['windows']:
        print('=== WINDOW: %s (%s)===' % (window.get('title', 'NO TITLE'), window['selected']))
        if 'closedAt' in window:
            continue
        for tab in window['tabs']:
            if 'closedAt' in tab:
                continue
            print(str(tab['index']) + ' ' + tab['entries'][-1]['url'])


def dump_session_jsonlz4(fpath):
    with open(fpath, "rb") as in_file:
        data = decompress(in_file)
    sess = json.loads(data)
    for window in sess['windows']:
        print('=== WINDOW: %s (%s)===' % (window.get('title', 'NO TITLE'), window['selected']))
        if 'closedAt' in window:
            continue
        for tab in window['tabs']:
            if 'closedAt' in tab:
                continue
            print(str(tab['index']) + ' ' + tab['entries'][-1]['url'])


if __name__ == "__main__":
    if len(sys.argv) < 1:
        sys.stderr.write(
            "USAGE: dump_firefox_session.py /path/to/sessionstore.js\n"
        )
        raise SystemExit(1)
    fpath = sys.argv[1]
    if fpath.endswith('.js'):
        dump_session_js(sys.argv[1])
    elif fpath.endswith('.jsonlz4'):
        dump_session_jsonlz4(fpath)
    else:
        raise SystemExit('Unknown file extension.')
