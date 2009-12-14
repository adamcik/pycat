import asynchat
import logging
import re
import socket

class IRC(object):
    def __init__(self, bot):
        self.bot = bot

    # FIXME add translation table /msg -> /privmsg etc.

    def __getattr__(self, key):
        def wrapper(*args):
            self.bot.irc_command(key.upper(), *args)
        wrapper.__name__ = key.upper()
        return wrapper

class Bot(asynchat.async_chat):
    # FIXME take in external config
    config = {
        'nick': 'pycat',
        'username': 'pycat',
        'hostname': socket.getfqdn(),
        'servername': socket.getfqdn(),
        'realname': 'pycat',
    }

    logger = logging.getLogger('irc')

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
        self.add('CONNECT', self.irc_register)
        self.add('433', self.irc_nick_collision)
        self.add('PRIVMSG', self.irc_message)

        self.add('JOIN', self.irc_nicks_in_channel)
        self.add('PART', self.irc_nicks_in_channel)
        self.add('QUIT', self.irc_nicks_in_channel)
        self.add('353', self.irc_nicks_in_channel)

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
        self.logger.info('Connected to server')

        self.handle_command(self.server, 'CONNECT', '')

    def irc_pong(self, prefix, command, args):
        self.irc_command('PONG', args[0])

    def irc_register(self, prefix, command, args):
        self.irc_command('NICK', self.config['nick'])
        self.irc_command('USER', self.config['username'],
                           self.config['hostname'],
                           self.config['servername'],
                           self.config['realname'])

    def irc_nick_collision(self, prefix, command, args):
        self.current_nick = args[1] + '_'
        self.irc_command('NICK', self.current_nick)

    def irc_nicks_in_channel(self, prefix, command, args):
        # FIXME valueerrors...

        if command in ['QUIT', 'PART']:
            channel = args[0]
            nick = prefix.split('!')[0]

            self.channels[channel].remove(nick)
        else:
            if command == 'JOIN':
                channel = args[0]
                nicks = [prefix.split('!')[0]]
            else:
                channel = args[-2]
                nicks = args[-1].split()

            if channel not in self.channels:
                self.channels[channel] = set()

            for nick in nicks:
                self.channels[channel].add(nick)

    # FIXME don't auto reply messages
    def irc_message(self, prefix, command, args):
        user = prefix.split('!')[0]
        target, message = args

        if target == self.current_nick:
            self.irc_command('PRIVMSG', user, message)
        else:
            self.irc_command('PRIVMSG', target, message)

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

        return prefix, command, args

    def collect_incoming_data(self, data):
        self.buffer += data

    def found_terminator(self):
        line, self.buffer = self.buffer, ''

        try:
            line = line.decode('utf-8')
        except UnicodeDecodeError:
            line = line.decode('iso-8859-1')

        self.logger.debug('Recieved: %s', line)

        prefix, command, args = self.parse_line(line)

        self.handle_command(prefix, command, args)

    def irc_command(self, *args):
        line = ' '.join(args[:-1]) + ' :' + args[-1]
        line = line.encode('utf-8')

        self.logger.debug('Sending: %s', line)

        self.push(line + self.get_terminator())
