#!/usr/bin/python3 -u

import json
import sys
import struct
import os
import contextlib
import socketserver
import threading
import traceback
import subprocess


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
            subprocess.run(['notify-send', 'firefox-tab-control exception', traceback.format_exc()])
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
            input_lines.append(f'{sound}{title} ({url})\t\t\t\t\t\t\t\t\t\t{tab_id}')

        p = subprocess.Popen(os.getenv('DMENU'), stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        p.stdin.write(('\n'.join(input_lines) + '\n').encode('utf-8'))
        p.stdin.close()
        selected_tab = p.stdout.read()
        p.wait()
        try:
            tab_id = int(selected_tab.split(b'\t')[-1])
            return next((tab for tab in tabs if tab['id'] == tab_id), None)
        except ValueError:
            return None


    def focus_tab(self):
        # TODO async
        def get_tabs():
            self._commander.command('get_tabs', cb=select_tab)
        def select_tab(data):
            tabs = data['results']
            selected_tab = self._select_tab(tabs)
            if selected_tab:
                identify_window(selected_tab)
        def identify_window(selected_tab):
            self._commander.command(
                'identify_window',
                args={'windowId': selected_tab['windowId'], 'on': True},
                cb=lambda d: focus_tab(d, selected_tab)
            )
        def focus_tab(data, selected_tab):
            identifier = data['results']['identifier']
            if identifier:
                self._sway_focus_firefox_window(identifier)
                self._commander.command(
                    'identify_window',
                    args={'windowId': selected_tab['windowId'], 'on': False}
                )
                self._commander.command(
                    'focus_tab',
                    args={'tab': selected_tab}
                )
        get_tabs()


    def _sway_focus_firefox_window(self, identifier):
        # hack
        subprocess.run(['swaymsg', f'[app_id="firefoxdeveloperedition" title="{identifier} "]', 'focus'], stdout=subprocess.DEVNULL)


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
