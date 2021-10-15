#!/usr/bin/python3 -u

import json
import sys
import struct
import os
import contextlib
import socketserver
from subprocess import run, PIPE


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
    run(['swaymsg', f'[app_id="firefoxdeveloperedition" title="^{patt} "]', 'focus'], stdout=PIPE)


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


class TabFocusServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):

    def server_bind(self):
        os.fchmod(self.socket.fileno(), 0o600)
        super().server_bind()

    def set_firefox_messaging_host(self, messaging_host):
        self.messaging_host = messaging_host


class TabFocusRequestHandler(socketserver.StreamRequestHandler):

    def handle(self):
        # don't read or write anything, just do the thing
        self.server.messaging_host.focus_tab()


def main():
    socket_path = f'/run/user/{os.getuid()}/firefox_tab_control.sock'
    with contextlib.suppress(FileNotFoundError):
        os.remove(socket_path)
    server = TabFocusServer(socket_path, TabFocusRequestHandler)
    server.set_firefox_messaging_host(FirefoxMessagingHost())
    server.serve_forever()

if __name__ == '__main__':
    main()
