#! /usr/bin/python

import logging
import re
import select
import socket
import subprocess
import time

from ircbot import SingleServerIRCBot, nm_to_n as get_nick, parse_channel_modes

# FIXME use optparse and/or configreader and/or sys.args

LOG_FORMAT = "[%(name)7s %(asctime)s] %(message)s"
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

class PyCatBot(SingleServerIRCBot):
    def __init__(self, server_list, nick, real, channel, script):
        SingleServerIRCBot.__init__(self, server_list, nick, real)

        self.channel = channel
        self.script = script

        self.recivers = []
        self.processes = []
        self.buffers = {}
        self.send_buffer = []
        self.loggers = {}

        self.listener = None

        self.last_send = time.time()
        self.last_recv = time.time()
        self.send_frequency = 2
        self.send_scheduled = False

        self.setup_logging()
        self.setup_throttling()

    def setup_logging(self):
        self.loggers['irc'] = logging.getLogger('irc')
        self.loggers['process'] = logging.getLogger('process')
        self.loggers['reciver'] = logging.getLogger('reciver')

        def logger(conn, event):
            args = map(self.decode, event.arguments())
            self.loggers['irc'].debug(' '.join(args))

        self.connection.add_global_handler('all_raw_messages', logger)

    def setup_throttling(self):
        orignial_send_raw = self.connection.send_raw

        def send_raw(string):
            self.loggers['irc'].debug(string.decode('utf-8'))
            self.last_send = time.time()
            orignial_send_raw(string)

        def handle_send_buffer():
            since_last = time.time() - self.last_send

            if since_last < self.send_frequency:
                delay = self.send_frequency - since_last
                self.send_scheduled = True
                self.connection.execute_delayed(delay, handle_send_buffer)
                return

            string = self.send_buffer.pop(0)

            send_raw(string)

            if self.send_buffer:
                self.send_scheduled = True
                self.connection.execute_delayed(self.send_frequency,
                    handle_send_buffer)
            else:
                self.send_scheduled = False

        def throttling(string):
            if not re.match('^(PRIVMSG|NOTICE)', string):
                send_raw(string)
                return

            self.send_buffer.append(string)

            if not self.send_scheduled:
                handle_send_buffer()

        self.connection.send_raw = throttling

    def on_welcome(self, conn, event):
        conn.join(self.channel)

        self.start_listener()

    def on_disconnect(self, conn, event):
        self.stop_listener()

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
        channel = event.target()
        nick = get_nick(event.source())
        message = self.decode(event.arguments()[0])

        p = subprocess.Popen([self.script, channel, nick, message],
            bufsize=1024, stdout=subprocess.PIPE)

        self.processes.append(p.stdout)

    def start(self):
        self._connect()

        while 1:
            sockets = self.processes + self.recivers

            if self.listener:
                sockets.append(self.listener)

            if self.connection.socket:
                sockets.append(self.connection.socket)

            self.process_sockets(sockets)

    def stop(self):
        if self.connection.is_connected():
            self.connection.disconnect('Bye :)')

        self.stop_listener()

        for sock in self.recivers + self.processes:
            sock.close()

    def process_sockets(self, sockets):
        for sock in select.select(sockets, [], [], 0.2)[0]:
            if sock in self.recivers:
                self.handle_reciver(sock)
            elif sock is self.listener:
                self.handle_listener(sock)
            elif sock in self.processes:
                self.handle_process(sock)
            else:
                self.handle_irc(sock)

        self.handle_timeout()

    def handle_reciver(self, sock):
        peer = sock.getpeername()[0]
        debug = self.loggers['reciver'].debug

        reader = lambda: sock.recv(4096)
        plain_logger = lambda m: debug('%s %s', peer, m)
        close_logger = lambda: debug('%s disconnected', peer)

        self.handle_generic(sock, reader, self.recivers, plain_logger,
            close_logger)

    def handle_process(self, sock):
        reader = lambda: sock.read(4096)
        plain_logger = lambda m: self.loggers['process'].debug(m)

        self.handle_generic(sock, reader, self.processes, plain_logger)

    def handle_generic(self, sock, reader, sockets, plain_logger=None,
            close_logger=None):

        if sock not in self.buffers:
            self.buffers[sock] = u''

        data = reader()

        if len(data) == 0:
            if close_logger:
                close_logger()
            sockets.remove(sock)
            sock.close()
        else:
            self.buffers[sock] += self.decode(data)

        while '\n' in self.buffers[sock]:
            message, trailing = self.buffers[sock].split('\n', 1)
            self.buffers[sock] = trailing

            if plain_logger:
                plain_logger(message)
            self.send_message(message)

        if len(data) == 0:
            del self.buffers[sock]

    def send_message(self, message):
        message = message.encode('utf-8')

        if not message.strip() or not self.connection.is_connected():
            return
        elif message.startswith('/me '):
            self.connection.action(self.channel, message[len('/me '):])
        elif message.startswith('/notice '):
            self.connection.notice(self.channel, message[len('/notice '):])
        else:
            self.connection.privmsg(self.channel, message)

    def handle_listener(self, sock):
        conn, addr = sock.accept()
        self.loggers['reciver'].debug('%s connected', addr[0])
        self.recivers.append(conn)

    def handle_irc(self, sock):
        self.ircobj.process_data([sock])
        self.last_recv = time.time()

    def handle_timeout(self):
        self.ircobj.process_timeout()
        self.check_connection()

    def start_listener(self, addr=('', 12345)):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setblocking(0)
        listener.bind(addr)
        listener.listen(5)

        self.listener = listener

    def stop_listener(self):
        if self.listener:
            self.listener.close()
            self.listener = None

    def check_connection(self):
        if self.last_recv > self.last_send:
            last = self.last_recv
        else:
            last = self.last_send

        if time.time() - last > 300:
            self.connection.version()

    def decode(self, data):
        try:
            data = data.decode('utf-8')
        except UnicodeDecodeError:
            data = data.decode('iso-8859-1')
        return data

pycat = PyCatBot([('localhost', 6667)], 'pycat', 'pycat', '#pycat', './test.sh')

try:
    pycat.start()
except KeyboardInterrupt:
    pass

pycat.stop()
