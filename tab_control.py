#!/usr/bin/python3 -u

import json
import sys
import struct
from subprocess import run, PIPE
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
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


def get_current_i3_container(node=None):
    if not node:
        node = run(['i3-msg', '-t', 'get_tree'], stdout=PIPE).stdout
        node = json.loads(node)
    if node['focused']:
        return node
    else:
        for subnode in node['nodes']:
            current = get_current_i3_container(subnode)
            if current:
                return current


def focus_i3_container(container):
    run(['i3-msg', f'[con_id="{container["id"]}"]', 'focus'], stdout=PIPE)


class FocusState(object):

    def __init__(self, first_container=None, first_tab=None, first_url=None, first_title=None):
        self.first_container = first_container
        self.first_tab = first_tab
        self.first_url = first_url
        self.first_title = first_title
        self.toggled_tab = None

    def active(self):
        return bool(self.first_url or self.first_title) and self._is_toggled_tab()

    def _not_from_firefox(self):
        return (
            self.first_container and
            self.first_container['window_properties']['class'] != 'Firefox')

    def toggle_off(self):
        if self._not_from_firefox():
            focus_i3_container(self.first_container)
        else:
            send_message({'command': 'focus_tab', 'data': self.first_tab})
        self.first_url, self.first_title = None, None

    def toggle_on(self, tabs):
        for tab in tabs:
            if self.first_url in tab['url'] and self.first_title in tab['title']:
                self.toggled_tab = tab
                break
        if not self.toggled_tab:
            self.first_url, self.first_title = None, None
        else:
            send_message({'command': 'focus_tab', 'data': self.toggled_tab})

    def set_current_state(self, url, title, tab, container):
        self.current_url = url
        self.current_title = title
        self.current_tab = tab
        self.current_container = container

    def _is_toggled_tab(self):
        return (
            (self.current_url == self.first_url and self.current_title == self.first_title) and
            (self.current_container and
             self.current_container['window_properties']['class'] == 'Firefox') and
            (self.current_tab['id'] == self.toggled_tab['id']))


class FirefoxMessagingHost(object):

    def __init__(self):
        self.focus_state = FocusState()


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
        send_message({'command': 'get_focused_window'})
        focused_window = get_message()
        send_message({'command': 'get_tabs'})
        tabs = get_message()

        if not url and not title:
            selected_tab = self._select_tab_dmenu(tabs)
            send_message({'command': 'focus_tab', 'data': selected_tab})
        else:
            current_tab = next((tab for tab in tabs if tab['active'] and focused_window['id'] == tab['windowId']), None)
            current_container = get_current_i3_container()
            url, title = url or '', title or ''
            self.focus_state.set_current_state(url, title, current_tab, current_container)

            if not self.focus_state.active():
                self.focus_state = FocusState(current_container, current_tab, url, title)
                self.focus_state.toggle_on(tabs)
            else:
                self.focus_state.toggle_off()


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
