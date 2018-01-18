#!/usr/bin/python3 -u

import json
import sys
import struct
from subprocess import run, call, PIPE
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


# call(['notify-send', '-t', '60000', str(tabs[0])])
def focus_tab(url=None, title=None):
    send_message({'command': 'get_tabs'})
    tabs = get_message()

    if not url and not title:
        selected_tab = run(['dmenu', '-i', '-l', '10', '-fn', 'Source Han Sans-10'],
            input='\n'.join([f'{tab["id"]} {tab["title"]} ({tab["url"]})' for tab in tabs]).encode('utf-8'),
            stdout=PIPE,
        ).stdout
        selected_tab = int(selected_tab.split(b' ')[0])
        selected_tab = next((tab for tab in tabs if tab['id'] == selected_tab), None)
    else:
        url, title = url or '', title or ''
        selected_tab = None
        for tab in tabs:
            if url in tab['url'] and title in tab['title']:
                selected_tab = tab
                break

    if selected_tab:
        send_message({'command': 'focus_tab', 'data': selected_tab})


class TabFocusServer(HTTPServer):

    def set_auth(self, auth):
        self.auth = auth


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
            focus_tab(url=url_query, title=title)
            self.respond_ok()
        else:
            self.respond_notfound()


def main():
    with open(expanduser('~/.firefox-tab-control'), 'rb') as f:
        auth = f.read().strip()
    server = TabFocusServer(('127.0.0.1', 9882), TabFocusRequestHandler)
    server.set_auth(auth)
    server.serve_forever()

if __name__ == '__main__':
    main()
