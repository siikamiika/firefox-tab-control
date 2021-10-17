#!/usr/bin/python3 -u

import json
import sys
import struct
import os
import time
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
            if message['type'] == 'results':
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

    _COLORS = [
        (255, 0,   0),   (255, 255, 0),   (0,   234, 255),
        (170, 0,   255), (255, 127, 0),   (191, 255, 0),
        (0,   149, 255), (255, 0,   170), (255, 212, 0),
        (106, 255, 0),   (0,   64,  255), (237, 185, 185),
        (185, 215, 237), (231, 233, 185), (220, 185, 237),
        (185, 237, 224), (143, 35,  35),  (35,  98,  143),
        (143, 106, 35),  (107, 35,  143), (79,  143, 35),
    ]

    def __init__(self, commander):
        self._commander = commander

        self._browser_window_map = {}
        self._update_all_windows()
        self._commander.command('subscribe_new_window', cb=self._on_new_window)
        self._commander.command('subscribe_close_window', cb=self._on_close_window)

    def _update_all_windows(self):
        def update_window_map(data):
            for window in data['results']:
                self._identify_window(window['id'])
        self._commander.command('get_windows', cb=update_window_map)

    def _on_new_window(self, data):
        time.sleep(0.5)
        window = data['results']
        self._identify_window(window['id'])

    def _on_close_window(self, data):
        window = data['results']
        if window['id'] in self._browser_window_map:
            del self._browser_window_map[window['id']]

    def _identify_window(self, window_id, cb=None):
        def set_title_identifier():
            self._commander.command(
                'identify_window',
                args={'windowId': window_id, 'on': True},
                cb=find_title_identifier
            )
        def find_title_identifier(data):
            identifier = data['results']['identifier']
            con_id = self._sway_get_con_id_for_title_identifier(identifier)
            if con_id is not None:
                self._browser_window_map[window_id] = {'con_id': con_id}
            cleanup()
        def cleanup():
            self._commander.command(
                'identify_window',
                args={'windowId': window_id, 'on': False},
                cb=cb or (lambda r: None)
            )
        set_title_identifier()

    def _select_tab(self, tabs):
        for tab in tabs:
            win_id = tab['windowId']
            if win_id not in self._browser_window_map:
                self._identify_window(win_id, lambda r: self._select_tab(tabs))
                return

        p = subprocess.Popen(os.getenv('DMENU'), stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)

        workspace_by_window_id = self._sway_get_firefox_workspaces_by_window_id()

        def tab_sort_key(tab):
            win_id = tab['windowId']
            return workspace_by_window_id[win_id], win_id

        input_lines = []
        win_counter = 0
        prev_win_id = None
        for tab in sorted(tabs, key=tab_sort_key):
            win_id = tab['windowId']
            ws_id = workspace_by_window_id[win_id]
            if win_id != prev_win_id:
                win_counter += 1
                prev_win_id = win_id
            sound = '[sound] ' if tab['audible'] else ''
            title = tab['title']
            url = tab['url']
            tab_id = tab['id']
            color = self._COLORS[win_counter % 21]
            win_counter_colored = self._ansi_bg_colored(f'{win_counter: >2}', *color)

            line = f'{ws_id}  {win_counter_colored} {sound}{title} ({url})\t\t\t\t\t\t\t\t\t\t{tab_id}'
            input_lines.append(line)

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
                focus_tab(selected_tab)
        def focus_tab(selected_tab):
            self._sway_focus_firefox_window(selected_tab['windowId'])
            self._commander.command(
                'focus_tab',
                args={'tab': selected_tab}
            )
        get_tabs()


    def _sway_focus_firefox_window(self, window_id):
        if window_id in self._browser_window_map:
            con_id = self._browser_window_map[window_id]['con_id']
            subprocess.run(['swaymsg', f'[con_id={con_id}]', 'focus'], stdout=subprocess.DEVNULL)

    def _sway_get_con_id_for_title_identifier(self, identifier):
        stack = [self._sway_get_tree()]
        while stack:
            node = stack.pop()
            if (name := node.get('name')) and identifier in name:
                return node['id']
            for key in ['nodes', 'floating_nodes']:
                if nodes := node.get(key):
                    stack += nodes
        return None

    def _sway_get_firefox_workspaces_by_window_id(self):
        stack = [self._sway_get_tree()]
        window_id_by_con_id = {
            c['con_id']: w
            for w, c in self._browser_window_map.items()
        }
        workspace_by_window_id = {}
        workspace_num = None
        while stack:
            node = stack.pop()
            if node['id'] in window_id_by_con_id:
                win_id = window_id_by_con_id[node['id']]
                workspace_by_window_id[win_id] = workspace_num
                continue
            if node['type'] == 'workspace':
                workspace_num = node.get('num')
            for key in ['nodes', 'floating_nodes']:
                if nodes := node.get(key):
                    stack += nodes
        return workspace_by_window_id

    def _sway_get_tree(self):
        p = subprocess.run(['swaymsg', '-t', 'get_tree'], stdout=subprocess.PIPE)
        return json.loads(p.stdout)

    def _ansi_bg_colored(self, text, r, g, b):
        return "\033[48;2;{};{};{};38;2;0;0;0m {} \033[00m".format(r, g, b, text)



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
