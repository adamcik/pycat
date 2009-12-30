import asynchat
import logging
import os
import pwd
import re
import socket
import time

logger = logging.getLogger('irc')

# FIXME irc message class that does parsing and building of messages
# FIXME class should also fix encoding

class IRC(object):
    def __init__(self, sender):
        self.sender = sender

    def __getattr__(self, key):
        key = key.upper()

        def wrapper(*args):
            self._command(key, *args)

        wrapper.__name__ = key
        return wrapper

    def _command(self, *args):
        if args[0].startswith('CTCP_NOTICE_'):
            ctcp = args[0][len('CTCP_NOTICE_'):]
            args = ['NOTICE', args[1], '\001%s %s\001' % (ctcp, args[2])]
        elif args[0].startswith('CTCP_'):
            ctcp = args[0][len('CTCP_'):]
            args = ['PRIVMSG', args[1], '\001%s %s\001' % (ctcp, args[2])]

        self.sender(' '.join(args[:-1]) + ' :' + args[-1])

class Bot(asynchat.async_chat):
    messages_per_second = 1

    def __init__(self, addr, nick, name, channel):
        asynchat.async_chat.__init__(self)

        self.addr = addr
        self.nick = nick
        self.name = name
        self.channel = channel
        self.username = pwd.getpwuid(os.getuid())[0]

        self.buffer = ''
        self.handlers = {}
        self.reconnect_wait = 0
        self.last_send = time.time()

        self.irc = IRC(self.sender)

        self.set_terminator("\r\n")

        self.add_handler('PING', self.irc_pong)
        self.add_handler('INVITE', self.irc_invite)
        self.add_handler('376', self.irc_join)
        self.add_handler('433', self.irc_nick_collision)

        self.reconnect()

    def reconnect(self):
        '''Handle clearing buffers and connection to server'''

        self.discard_buffers()
        self.del_channel()

        if self.reconnect_wait:
            time.sleep(self.reconnect_wait)

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect(self.addr)

        self.reconnect_wait = 30

    def add_handler(self, event, handler):
        event = event.upper()

        if event not in self.handlers:
            self.handlers[event] = []

        self.handlers[event].append(handler)

    def handle_connect(self):
        logger.info('Connected to server')

        self.irc.nick(self.nick)
        self.irc.user(self.username, '.', '.', self.name)

    def handle_close(self):
        logger.info('Disconnected from server')

        self.reconnect()

    def irc_pong(self, nick=None, user=None, host=None, command=None, args=None):
        self.irc.pong(args[0])

    def irc_nick_collision(self, nick=None, user=None, host=None, command=None, args=None):
        self.irc.nick(args[1] + '_')

    def irc_join(self, nick=None, user=None, host=None, command=None, args=None):
        self.irc.join(self.channel)

    def irc_invite(self, nick=None, user=None, host=None, command=None, args=None):
        if args[0] == self.channel:
            self.irc.join(self.channel)

    def parse_line(self, line):
        prefix = ''

        if line.startswith(':'):
            prefix, line = re.split(' +', line[1:],  1)

        if ' :' in line:
            line, trailing = re.split(' +:', line, 1)
            args = re.split(' +', line)
            args.append(trailing)
        else:
            args = re.split(' +', line)

        command = args.pop(0)

        if command == 'PRIVMSG' and args[1][0] == args[1][-1] == '\001':
            parts = re.split(' ', args[1][1:-1])
            command = 'CTCP_' + parts.pop(0)
            args[1] = ' '.join(parts)

        if prefix and '!' in prefix:
            nick, rest = prefix.split('!', 1)
            user, host = rest.split('@', 1)
        elif prefix:
            nick, user, host = None, None, prefix
        else:
            nick, user, host = None, None, None

        return {
            'nick': nick,
            'user': user,
            'host': host,
            'command': command,
            'args': args,
        }

    def collect_incoming_data(self, data):
        self.buffer += data

    def found_terminator(self):
        line, self.buffer = self.buffer, ''
        line = self.decode(line)

        logger.debug('Recieved: %s', line)

        kwargs = self.parse_line(line)

        for handler in self.handlers.get(kwargs['command'], []):
            handler(**kwargs)

    def decode(self, line):
        try:
            return line.decode('utf-8')
        except UnicodeDecodeError:
            return line.decode('iso-8859-1')

    def encode(self, line):
        if type(line) is unicode:
            return line.encode('utf-8')
        return line

    def throttle(self):
        sleep = time.time() - self.last_send

        if sleep < self.messages_per_second:
            time.sleep(self.messages_per_second - sleep)

        self.last_send = time.time()

    def sender(self, line):
        self.throttle()

        logger.debug('Sending: %s', line)
        self.push(self.encode(line) + self.get_terminator())
        return len(line)
