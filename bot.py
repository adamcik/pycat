#! /usr/bin/python

import logging
import re
import select
import socket
import subprocess
import sys
import time

from ircbot import SingleServerIRCBot, nm_to_n as get_nick, parse_channel_modes

LOG_FORMAT = "[%(name)7s %(asctime)s] %(message)s"
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

class PyCatBot(SingleServerIRCBot):
    def __init__(self, server_list, nick, real, channel, listen_addr=None, script=None):
        SingleServerIRCBot.__init__(self, server_list, nick, real)

        self.channel = channel
        self.script = script
        self.listen_addr = tuple(listen_addr)

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
        self.setup_listener()

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

            if not self.send_buffer:
                return
            elif since_last < self.send_frequency:
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

    def setup_listener(self):
        if not self.listen_addr:
            return

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setblocking(0)
        listener.bind(self.listen_addr)
        listener.listen(5)

        self.listener = listener

    def on_welcome(self, conn, event):
        conn.join(self.channel)

    def on_disconnect(self, conn, event):
        self.send_buffer = []

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
        if not self.script:
            return

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

        self.listener.close()

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
        if not message.strip():
            return
        elif self.channel not in self.channels:
            self.loggers['irc'].debug('Discarding message: %s', message)
            return
        else:
            message = message.encode('utf-8')

        if message.startswith('/me '):
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

    def decode(self, data):
        try:
            data = data.decode('utf-8')
        except UnicodeDecodeError:
            data = data.decode('iso-8859-1')
        return data

def main():
    if len(sys.argv) != 7:
        usage()

    raw_servers, listen, nick, real, channel, script = sys.argv[1:]
    servers = []

    for addr in raw_servers.split(','):
        if ':' in addr:
            servers.append(addr.split(':', 1))
        else:
            servers.append([addr, 6667])

    listen = listen.split(':', 1)
    listen[1] = int(listen[1])

    pycat = PyCatBot(servers, nick, real, channel, listen, script)

    try:
        pycat.start()
    except KeyboardInterrupt:
        pass

    pycat.stop()

def usage():
    print '%s server[:port][,server2[:port]] [interface]:port nick realname channel script' % sys.argv[0]
    sys.exit(0)

if __name__ == '__main__':
    main()
