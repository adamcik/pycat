import asynchat
import logging
import re
import socket
import time

logger = logging.getLogger('irc')

class IRC(object):
    max_per_second = 1

    def __init__(self, bot):
        self.bot = bot
        self.last_send = time.time()

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

        line = ' '.join(args[:-1]) + ' :' + args[-1]

        sleep = time.time() - self.last_send

        if sleep < self.max_per_second:
            time.sleep(self.max_per_second - sleep)

        logger.debug('Sending: %s', line)

        self.bot.push(line.encode('utf-8') + self.bot.get_terminator())
        self.last_send = time.time()

class Bot(asynchat.async_chat):
    # FIXME take in external config
    config = {
        'nick': 'pycat',
        'username': 'pycat',
        'hostname': socket.getfqdn(),
        'servername': socket.getfqdn(),
        'realname': 'pycat',
    }

    def __init__(self, server, port=6667):
        asynchat.async_chat.__init__(self)

        self.server = server
        self.port = port

        self.buffer = ''
        self.handlers = {}
        self.channels = {}
        self.current_nick = self.config['nick']

        self.irc = IRC(self)

        self.set_terminator("\r\n")

        self.add('PING', self.irc_pong)
        self.add('433', self.irc_nick_collision)

        self.add('JOIN', self.irc_nicks_in_channel)
        self.add('PART', self.irc_nicks_in_channel)
        self.add('QUIT', self.irc_nicks_in_channel)
        self.add('353', self.irc_nicks_in_channel)

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

    def handle_command(self, prefix, command, args):
        for handler in self.handlers.get(command, []):
            handler(prefix, command, args)

    def handle_connect(self):
        logger.info('Connected to server')

        self.irc.nick(self.config['nick'])
        self.irc.user(self.config['username'],
                      self.config['hostname'],
                      self.config['servername'],
                      self.config['realname'])

    def handle_close(self):
        self.reconnect()

    def known_target(self, target):
        if target and target[0] in '#&':
            return target in self.channels

        for nicks in self.channels.values():
            if target in nicks:
                return True

        return False

    def irc_pong(self, prefix, command, args):
        self.irc.pong(args[0])


    def irc_nick_collision(self, prefix, command, args):
        self.current_nick = args[1] + '_'
        self.irc.nick(self.current_nick)

    def irc_nicks_in_channel(self, prefix, command, args):
        # FIXME valueerrors...
        # FIXME clear on part

        nick = prefix.split('!')[0]

        if command == 'PART':
            channel = args[0]

            if nick == self.current_nick:
                del self.channels[channel]
            else:
                self.channels[channel].remove(nick)
        elif command == 'QUIT':
            for nicks in self.channels.values():
                if nick in nicks:
                    nicks.remove(nick)
        else:
            if command == 'JOIN':
                channel = args[0]
                nicks = [nick]
            else:
                channel = args[-2]
                nicks = args[-1].split()

            if channel not in self.channels:
                self.channels[channel] = set()

            for nick in nicks:
                self.channels[channel].add(nick)

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

        return prefix, command, args

    def collect_incoming_data(self, data):
        self.buffer += data

    def found_terminator(self):
        line, self.buffer = self.buffer, ''

        try:
            line = line.decode('utf-8')
        except UnicodeDecodeError:
            line = line.decode('iso-8859-1')

        logger.debug('Recieved: %s', line)

        prefix, command, args = self.parse_line(line)

        self.handle_command(prefix, command, args)
