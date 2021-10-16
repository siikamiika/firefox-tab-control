#!/usr/bin/python3 -u

import json
import sys
import struct
import os
import contextlib
import socketserver
import threading
import traceback
import uuid
from subprocess import run, PIPE


class FirefoxStandardStreamCommander:
    def __init__(self, input_stream, output_stream):
        self._input_stream = input_stream
        self._output_stream = output_stream
        self._seq = 0
        self._listeners = {}
        threading.Thread(target=self._handle_messages).start()


    def command(self, command, args=None, cb=None):
        seq = self._seq
        self._seq += 1
        self._listeners[seq] = cb or (lambda m: None)
        self._send_message({'id': seq, 'command': command, 'args': args or {}})


    def _handle_messages(self):
        while True:
            message = self._get_message()
            threading.Thread(target=self._handle_message, args=(message,)).start()


    def _handle_message(self, message):
        try:
            self._listeners[message['id']](message)
        except Exception as e:
            run(['notify-send', 'firefox-tab-control exception', traceback.format_exc()])
        finally:
            del self._listeners[message['id']]


    def _get_message(self):
        raw_length = self._input_stream.read(4)
        if not raw_length:
            sys.exit(0)
        message_length = struct.unpack('@I', raw_length)[0]
        message = self._input_stream.read(message_length).decode('utf-8')
        return json.loads(message)


    def _send_message(self, message_content):
        encoded_content = json.dumps(message_content).encode('utf-8')
        encoded_length = struct.pack('@I', len(encoded_content))
        self._output_stream.write(encoded_length)
        self._output_stream.write(encoded_content)
        self._output_stream.flush()


class FirefoxTabController(object):

    def __init__(self, commander):
        self._commander = commander

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
        try:
            tab_id = int(selected_tab.split(' ')[0])
            return next((tab for tab in tabs if tab['id'] == tab_id), None)
        except ValueError:
            return None


    def focus_tab(self):
        # TODO async
        selected_tab = None
        random_prefix = None
        def on_tabs(data):
            nonlocal selected_tab, random_prefix
            tabs = data['results']
            selected_tab = self._select_tab(tabs)
            if selected_tab:
                random_prefix = uuid.uuid4().hex
                self._commander.command(
                    'focus_tab',
                    args={
                        'windowId': selected_tab['windowId'],
                        'tabId': selected_tab['id'],
                        'randomPrefix': random_prefix
                    },
                    cb=on_focused
                )
        def on_focused(data):
            if data['results']['ok']:
                window_id = selected_tab['windowId']
                self._sway_focus_firefox_window(window_id, random_prefix)
                self._commander.command(
                    'notify_window_focused',
                    args={'id': data['id'],'windowId': window_id}
                )
        self._commander.command('get_tabs', cb=on_tabs)


    def _sway_focus_firefox_window(self, firefox_window_id, random_prefix):
        # hack
        patt = f'{random_prefix}:{firefox_window_id}'
        run(['swaymsg', f'[app_id="firefoxdeveloperedition" title="{patt} "]', 'focus'], stdout=PIPE)


class TabFocusServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):

    def server_bind(self):
        os.fchmod(self.socket.fileno(), 0o600)
        super().server_bind()

    def set_firefox_tab_controller(self, tab_controller):
        self.tab_controller = tab_controller


class TabFocusRequestHandler(socketserver.StreamRequestHandler):

    def handle(self):
        # don't read or write anything, just do the thing
        self.server.tab_controller.focus_tab()


def main():
    socket_path = f'/run/user/{os.getuid()}/firefox_tab_control.sock'
    with contextlib.suppress(FileNotFoundError):
        os.remove(socket_path)
    commander = FirefoxStandardStreamCommander(sys.stdin.buffer, sys.stdout.buffer)
    server = TabFocusServer(socket_path, TabFocusRequestHandler)
    server.set_firefox_tab_controller(FirefoxTabController(commander))
    server.serve_forever()

if __name__ == '__main__':
    main()
