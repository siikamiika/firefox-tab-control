#!/usr/bin/python3 -u

import json
import sys
import struct
from subprocess import run, PIPE
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from os.path import expanduser


def get_message():
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        sys.exit(0)
    message_length = struct.unpack('@I', raw_length)[0]
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)


def send_message(message_content):
    encoded_content = json.dumps(message_content).encode('utf-8')
    encoded_length = struct.pack('@I', len(encoded_content))
    sys.stdout.buffer.write(encoded_length)
    sys.stdout.buffer.write(encoded_content)
    sys.stdout.buffer.flush()


def sway_focus_firefox_window(firefox_window_id):
    # hack
    patt = f'focus_window_id:{firefox_window_id}'
    run(['swaymsg', f'[app_id="firefoxdeveloperedition" title="^{patt}"]', 'focus'], stdout=PIPE)


class FirefoxMessagingHost(object):

    def _select_tab(self, tabs):
        input_lines = []

        for tab in tabs:
            tab_id = tab['id']
            sound = '[sound] ' if tab['audible'] else ''
            title = tab['title']
            url = tab['url']
            input_lines.append(f'{tab_id} {sound}{title} ({url})')

        with open('/tmp/select_tab_input', 'wb') as f:
            f.write('\n'.join(input_lines).encode('utf-8'))
        run("alacritty --title=launcher -e bash -c 'cat /tmp/select_tab_input | fzf --layout=reverse > /tmp/select_tab_output'", shell=True)
        with open('/tmp/select_tab_output') as f:
            selected_tab = f.read()
        selected_tab = int(selected_tab.split(' ')[0])

        return next((tab for tab in tabs if tab['id'] == selected_tab), None)


    def focus_tab(self):
        send_message({'command': 'get_focused_window'})
        focused_window = get_message()
        send_message({'command': 'get_tabs'})
        tabs = get_message()

        selected_tab = self._select_tab(tabs)
        send_message({'command': 'focus_tab', 'data': selected_tab})
        if get_message()['ok']:
            sway_focus_firefox_window(selected_tab['windowId'])


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

        if url.path == '/focus_tab':
            self.server.messaging_host.focus_tab()
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
