#! /usr/bin/python

import logging
import re
import select
import socket
import subprocess
import sys
import time

from ircbot import SingleServerIRCBot, nm_to_n as get_nick, parse_channel_modes

# FIXME figure out async subprocess
# FIXME use optparse and/or configreader

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

CHANNEL = '#foo'
PATTERN = '^[\!\?][^ ]+'

def msg_parser(nick=None, user=None, host=None, command=None, args=None):
    target, message = args

    if not re.match(PATTERN, message) or target != CHANNEL:
        return

    p = subprocess.Popen('./test.sh',
        shell=True,
        bufsize=1024,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE)

    # FIXME this will block
    response = p.communicate(input=message.encode('utf-8'))[0]

    if not response.strip():
        return

    try:
        response = response.decode('utf-8')
    except UnicodeDecodeError:
        response = response.decode('iso-8859-1')

    for line in response.split('\n'):
        if line.strip():
            bot.irc.privmsg(CHANNEL, line)

class PyCatBot(SingleServerIRCBot):
    def __init__(self, server_list, nick, real, channel):
        SingleServerIRCBot.__init__(self, server_list, nick, real)

        self.channel = channel

        self.sockets = []
        self.recivers = []
        self.buffers = {}
        self.listener = self.get_listener()

        self.last_seen = time.time()
        self.ircobj.fn_to_add_socket = self.sockets.append
        self.ircobj.fn_to_remove_socket = self.sockets.remove

        self.setup_logging()

    def setup_logging(self):
        orignial_send_raw = self.connection.send_raw

        def send_raw(string):
            logging.debug(string)
            orignial_send_raw(string)

        def logger(conn, event):
            line = u' '.join(event.arguments())
            logging.debug(line)

        self.connection.add_global_handler('all_raw_messages', logger)
        self.connection.send_raw = send_raw

    def get_listener(self, addr=('', 12345)):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setblocking(0)
        listener.bind(addr)
        listener.listen(5)

        return listener

    def on_welcome(self, conn, event):
        conn.join(self.channel)

    def on_nicknameinuse(self, conn, event):
        conn.nick(conn.get_nickname() + '_')

    def on_invite(self, conn, event):
        if event.arguments()[0] == self.channel:
            conn.join(self.channel)

    def on_mode(self, conn, event):
        if event.target() != self.channel:
            return

        nick = conn.get_nickname()
        modes = parse_channel_modes(' '.join(event.arguments()))

        if ['+', 'o', nick] in modes:
            conn.mode(self.channel, '+v-o %s %s' % (nick, nick))

    def on_pubmsg(self, conn, event):
        sender = get_nick(event.source())
        message = event.arguments()[0]

        print sender, ':',  message

    def start(self):
        self._connect()

        while 1:
            sockets = self.sockets + [self.listener] + self.recivers

            for sock in select.select(sockets, [], [], 0.2)[0]:
                if sock in self.recivers:
                    self.handle_reciver(sock)
                elif sock is self.listener:
                    self.handle_listener(sock)
                elif sock in self.sockets:
                    self.handle_irc(sock)

            self.handle_timeout()

    def stop(self):
        if self.connection.is_connected():
            self.connection.disconnect('Bye :)')

    def handle_reciver(self, sock):
        if sock not in self.buffers:
            self.buffers[sock] = u''

        data = sock.recv(512)

        if len(data) == 0:
            self.recivers.remove(sock)
            del self.buffers[sock]
            return

        self.buffers[sock] += self.decode(data)

        while '\n' in self.buffers[sock]:
            message, trailing = self.buffers[sock].split('\n', 1)
            self.buffers[sock] = trailing

            self.handle_reciver_message(message)

    def handle_reciver_message(self, message):
        message = message.encode('utf-8')

        if not message.strip() or not self.connection.is_connected():
            return
        elif message.startswith('/me '):
            self.connection.action(CHANNEL, message[len('/me '):])
        elif message.startswith('/notice '):
            self.connection.notice(CHANNEL, message[len('/notice '):])
        else:
            self.connection.privmsg(CHANNEL, message)

    def handle_listener(self, sock):
        conn, addr = sock.accept()
        self.recivers.append(conn)

    def handle_irc(self, sock):
        self.ircobj.process_data([sock])
        self.last_seen = time.time()

    def handle_timeout(self):
        self.ircobj.process_timeout()
        self.check_connection()

    def check_connection(self):
        # FIXME test if this is needed
        if time.time() - self.last_seen > 300:
            self.connection.version()

    def decode(self, data):
        try:
            data = data.decode('utf-8')
        except UnicodeDecodeError:
            data = data.decode('iso-8859-1')
        return data

pycat = PyCatBot([('localhost', 6667)], 'pycat', 'pycat', CHANNEL)

try:
    pycat.start()
except KeyboardInterrupt:
    pycat.stop()
