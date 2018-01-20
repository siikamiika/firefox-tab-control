#!/usr/bin/python3 -u

import json
import sys
import struct
from subprocess import run, PIPE
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from os.path import expanduser


class FirefoxMessagingHost(object):

    def __init__(self):
        self.last_url = None
        self.last_title = None
        self.last_tab_id = -1
        self.original_tab_id = -1


    def _get_message(self):
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length:
            sys.exit(0)
        message_length = struct.unpack('@I', raw_length)[0]
        message = sys.stdin.buffer.read(message_length).decode('utf-8')
        return json.loads(message)


    def _send_message(self, message_content):
        encoded_content = json.dumps(message_content).encode('utf-8')
        encoded_length = struct.pack('@I', len(encoded_content))
        sys.stdout.buffer.write(encoded_length)
        sys.stdout.buffer.write(encoded_content)
        sys.stdout.buffer.flush()


    def _select_tab_dmenu(self, tabs):
        input_lines = []

        for tab in tabs:
            tab_id = tab['id']
            sound = '[sound] ' if tab['audible'] else ''
            title = tab['title']
            url = tab['url']
            input_lines.append(f'{tab_id} {sound}{title} ({url})')

        cmd = ['dmenu', '-i', '-l', '10', '-fn', 'Source Han Sans-10']
        dmenu_input = '\n'.join(input_lines).encode('utf-8')
        selected_tab = run(cmd, input=dmenu_input, stdout=PIPE).stdout
        selected_tab = int(selected_tab.split(b' ')[0])

        return next((tab for tab in tabs if tab['id'] == selected_tab), None)


    def focus_tab(self, url=None, title=None):
        self._send_message({'command': 'get_focused_window'})
        focused_window = self._get_message()
        self._send_message({'command': 'get_tabs'})
        tabs = self._get_message()
        selected_tab = None
        current_tab = next((tab for tab in tabs if tab['active'] and focused_window['id'] == tab['windowId']), None)

        if current_tab['id'] != self.last_tab_id:
            self.last_url = None
            self.last_title = None

        if not url and not title:
            selected_tab = self._select_tab_dmenu(tabs)
            if selected_tab:
                self.last_url = None
                self.last_title = None
        else:
            url, title = url or '', title or ''

            if url == self.last_url and title == self.last_title:
                selected_tab = next((tab for tab in tabs if tab['id'] == self.original_tab_id), None)
                self.last_url = None
                self.last_title = None
            else:
                self.last_url = url
                self.last_title = title
                self.original_tab_id = current_tab['id']

                for tab in tabs:
                    if url in tab['url'] and title in tab['title']:
                        selected_tab = tab
                        break

        self.last_tab_id = current_tab['id']

        if selected_tab:
            self._send_message({'command': 'focus_tab', 'data': selected_tab})
            self.last_tab_id = selected_tab['id']


class TabFocusServer(HTTPServer):

    def set_auth(self, auth):
        self.auth = auth

    def set_firefox_messaging_host(self, messaging_host):
        self.messaging_host = messaging_host


class TabFocusRequestHandler(BaseHTTPRequestHandler):

    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def respond_ok(self, data=b'', content_type='text/html; charset=utf-8', age=0):
        self.send_response(200)
        self.send_header('Cache-Control', 'public, max-age={}'.format(age))
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    def respond_notfound(self, data='404'.encode()):
        self.send_response(404)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get('auth').strip().encode('utf-8') != self.server.auth:
            return self.respond_notfound()

        url = urlparse(self.path)
        query = parse_qs(url.query)

        url_query = query.get('url')
        if url_query: url_query = url_query[0]
        title = query.get('title')
        if title: title = title[0]

        if url.path == '/focus_tab':
            self.server.messaging_host.focus_tab(url=url_query, title=title)
            self.respond_ok()
        else:
            self.respond_notfound()


def main():
    with open(expanduser('~/.firefox-tab-control'), 'rb') as f:
        auth = f.read().strip()
    messaging_host = FirefoxMessagingHost()
    server = TabFocusServer(('127.0.0.1', 9882), TabFocusRequestHandler)
    server.set_auth(auth)
    server.set_firefox_messaging_host(messaging_host)
    server.serve_forever()

if __name__ == '__main__':
    main()
