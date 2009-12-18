import asynchat
import logging
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
        if args[0].startswith('CTCP_'):
            ctcp = args[0][len('CTCP_'):]
            args = ['PRIVMSG', args[1], '\001%s %s\001' % (ctcp, args[2])]

        self.sender(' '.join(args[:-1]) + ' :' + args[-1])

class Bot(asynchat.async_chat):
    # FIXME take in external config
    config = {
        'nick': 'pycat',
        'username': 'pycat',
        'hostname': '.',
        'servername': '.',
        'realname': 'pycat',
        'channel': '#foo',
        'rate': 1,
    }

    def __init__(self, server, port=6667):
        asynchat.async_chat.__init__(self)

        self.server = server
        self.port = port

        self.buffer = ''
        self.handlers = {}
        self.last_send = time.time()

        self.irc = IRC(self.sender)

        self.set_terminator("\r\n")

        self.add('PING', self.irc_pong)
        self.add('INVITE', self.irc_invite)
        self.add('376', self.irc_join)
        self.add('433', self.irc_nick_collision)

        self.reconnect()

    def reconnect(self):
        self.discard_buffers()

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((self.server, self.port))

    # FIXME rename and fix signature. decorator?
    def add(self, command, handler):
        if command not in self.handlers:
            self.handlers[command] = []

        self.handlers[command].append(handler)

    def handle_connect(self):
        logger.info('Connected to server')

        self.irc.nick(self.config['nick'])
        self.irc.user(self.config['username'],
                      self.config['hostname'],
                      self.config['servername'],
                      self.config['realname'])

    def handle_close(self):
        self.reconnect()

    def irc_pong(self, nick=None, user=None, host=None, command=None, args=None):
        self.irc.pong(args[0])

    def irc_nick_collision(self, nick=None, user=None, host=None, command=None, args=None):
        self.irc.nick(args[1] + '_')

    def irc_join(self, nick=None, user=None, host=None, command=None, args=None):
        self.irc.join(self.config['channel'])

    def irc_invite(self, nick=None, user=None, host=None, command=None, args=None):
        if args[0] == self.config['channel']:
            self.irc.join(self.config['channel'])

    # FIXME move to IRCMessage class?
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

        try:
            line = line.decode('utf-8')
        except UnicodeDecodeError:
            line = line.decode('iso-8859-1')

        logger.debug('Recieved: %s', line)

        kwargs = self.parse_line(line)

        for handler in self.handlers.get(kwargs['command'], []):
            handler(**kwargs)

    def sender(self, line):
        logger.debug('Sending: %s', line)

        sleep = time.time() - self.last_send

        if sleep < self.config['rate']:
            time.sleep(self.config['rate'] - sleep)

        self.push(line.encode('utf-8') + self.get_terminator())
        self.last_send = time.time()
