#! /usr/bin/python
# Copyright (c) 2010 Thomas Kongevold Adamcik
# Released under MIT license, see COPYING file

USAGE = 'Usage: %prog server[:port][,server[:port]] nickname channel [options]'

VERSION = 'pycat - http://github.com/adamcik/pycat'

EPILOG = '''
Examples:
  Connect to irc.efnet.net, with nick cat, name 'Majo nes', script /foo/bar:
    %prog irc.efnet.net cat efnet --realname='Majo Nes' --script=/foo/bar
  Use multiple fallbacks on IRCnet, nick cat, channel pycat
    %prog irc.ifi.uio.no,irc.hitos.no,irc.pvv.org:6668 cat '#pycat'
  Connect to localhost, listen on port 12345 on all interfaces:
    %prog localhost cat '#pycat' --listen=12345
  Connect to irc.mynet.prv with port and password, nick cat, channel pycat
    %prog irc.mynet.prv:7777/secretpw cat '#pycat'
  Connect to irc.freenode.net, listen on port 8000 on a specific interface:
    %prog irc.freenode.net cat '#pycat' --listen=example.com:8000
'''

import logging
import os
import re
import select
import signal
import socket
import subprocess
import time

from optparse import OptionParser, IndentedHelpFormatter

from ircbot import SingleServerIRCBot, ServerConnectionError, \
        parse_channel_modes, is_channel, nm_to_n as get_nick

def decode(string):
    '''Force strings into unicode string objects'''

    if isinstance(string, unicode) or string is None:
        return string

    try:
        string = string.decode('utf-8')
    except UnicodeDecodeError:
        string = string.decode('iso-8859-1')
    return string

def encode(string):
    '''Encode (unicode) strings as utf-8'''

    if isinstance(string, unicode):
        return string.encode('utf-8')

    return string

def readable(string):
    '''Convert a string to readable format for logging'''

    new_string = ''

    for s in string:
        if len(s) == 1 and ord(s) < 32:
            new_string += r'\x%02X' % ord(s)
        else:
            new_string += s

    return new_string

def strip_unprintable(string):
    '''
    Removes standard unprintable sequences from the text.
    Regexes retrived from AnyEvent::IRC::Util on CPAN
    '''

    regexes = ('\x1B\[.*?[\x00-\x1F\x40-\x7E]', # ECMA-48
               '\x03\d\d?(?:,\d\d?)?', # IRC colors
               '[\x03\x16\x02\x1f\x0f]') # Other unprintables

    return re.sub('|'.join(regexes), '', string)

def dequote(string):
    '''
    Removes matching single or double quotes.
    '''

    if (string[0] == string[-1]) and string.startswith(("'", '"')):
        return string[1:-1]
    return string

class PyCat(SingleServerIRCBot):
    def __init__(self, server_list, nick, real, channel,
                 listen_addr=None, script=None, deop=True, opfirst=True):

        SingleServerIRCBot.__init__(self, server_list, nick, real,
                                    reconnection_interval=30)

        self.channel = decode(channel)
        self.script = map(decode, script or [])
        self.listen_addr = listen_addr
        self.deop = deop
        self.opfirst = opfirst

        self.match = '^!'
        self.match_timer = 0
        self.script_modified = 0

        self.dispatchers = {}
        self.irc_socket = None

        self.target_nick = nick

        self.send_timer = 0
        self.send_buffer = []
        self.recv_buffers = {}

        self.setup_logging()
        self.setup_throttling()
        self.setup_listener()

        self.running = False

    ## Init helpers ##
    def setup_listener(self):
        if not self.listen_addr:
            logging.debug('No listener, stopping listener setup')
            return

        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setblocking(0)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(self.listen_addr)
            listener.listen(5)
        except socket.gaierror, e:
            logging.error('Could not setup listener: %s', e)
            return

        logging.info('Listener set up on %s:%s' % self.listen_addr)
        self.dispatchers[listener] = self.handle_listener

    def setup_logging(self):
        def debug_logger(conn, event):
            line = decode(event.arguments()[0])
            logging.debug(readable(line))
        self.connection.add_global_handler('all_raw_messages', debug_logger)

    def setup_throttling(self):
        self.send_raw = self.connection.send_raw
        self.connection.send_raw = self.send_buffer.append

    def remove_throttling(self):
        self.connection.send_raw = self.send_raw

    ## Event loop and cleanup code ##
    def start(self):
        if not self._connect():
            self._connected_checker()

        self.running = True

        while self.running:
            sockets = self.dispatchers.keys()

            for sock in select.select(sockets, [], [], 0.2)[0]:
                self.dispatchers[sock](sock)

            self.handle_timeout()

    def stop(self):
        self.remove_throttling()

        if self.connection.is_connected():
            self.connection.disconnect('...')

        for sock in self.dispatchers.keys():
            sock.close()
            del self.dispatchers[sock]

    ## CTCP version reply ##
    def get_version():
        return VERSION
    get_version = staticmethod(get_version)

    ##  Event loop handlers ##

    # IRC handlers
    def handle_irc(self, sock):
        self.ircobj.process_data([sock])

    def handle_timeout(self):
        self.handle_send_buffer()
        self.handle_check_config()
        self.ircobj.process_timeout()

    def handle_send_buffer(self):
        if not self.send_buffer:
            return

        if self.send_timer < time.time():
            self.send_timer = time.time()

        while self.send_timer < time.time() + 10 and self.send_buffer:
            self.send_timer += 2

            string = self.send_buffer.pop(0)
            logging.debug(readable(decode(string)))
            self.send_raw(string)

    # Listener handlers
    def handle_listener(self, sock):
        conn, addr = sock.accept()
        logging.debug('%s connected', addr[0])

        if self.connection.is_connected():
            self.dispatchers[conn] = lambda s: self.handle_reciver(s, addr[0])
        else:
            logging.warning('%s disconnected as irc is down', addr[0])
            conn.close()

    def handle_reciver(self, sock, peer):
        try:
            data = sock.recv(4096)
        except socket.error, e:
            data = ''
            logging.error('%s %s', peer, e)

        for line in self.process_data(sock, data):
            logging.debug('%s %s', peer, readable(line))

            targets, message = self.parse_targets(line)
            targets = targets or [self.channel]

            if not message:
                continue

            logging.info("%s saying '%s' to %s", peer, message,
                u', '.join(targets))
            self.send_message(message, targets)

        if len(data) == 0:
            logging.debug('%s disconnected', peer)

    # Process handlers
    def handle_stdout(self, sock, target, source):
        data = sock.read(4096)

        if target == self.channel:
            default = self.channel
        else:
            default = source

        for line in self.process_data(sock, data):
            targets, message = self.parse_targets(line)
            targets = targets or [default]

            logging.info("%s saying '%s' to %s", self.script[0],
                readable(message), ', '.join(targets))
            self.send_message(message, targets)

    def handle_stderr(self, sock):
        data = sock.read(4096)

        for line in self.process_data(sock, data):
            logging.error('%s %s', self.script[0], line)

    def handle_check_config(self):
        if not self.script or self.match_timer > time.time():
            return

        self.match_timer = time.time() + 5

        try:
            last_modified = os.stat(self.script[0]).st_mtime
        except OSError, e:
            logging.debug('Could not stat %s: %s', self.script[0], e)
            return

        if self.script_modified == last_modified:
            return

        time_since_change = time.time() - last_modified

        if time_since_change < 2:
            time.sleep(2 - time_since_change)

        if self.start_process(['--config'], self.handle_config):
            self.script_modified = last_modified

    def handle_config(self, sock):
        data = sock.read(4096)

        for line in self.process_data(sock, data):
            # XXX use shlex or other suitable scheme to parse this with respect
            #     to leading and trailing whitespace and "' handling
            match = re.match('^(?P<key>\w+)\s*=\s*(?P<value>.+)', line)

            if not match:
                logging.error("Invalid reply from %s: '%s'", self.script[0], line)
                continue

            key, value = match.groups()

            if key == 'match': # If this grows a dispatcher table may be better
                self.match = value
                logging.info("Setting match regexp to '%s'", value)
            else:
                logging.warning("Unknown config key: %s = '%s'", key, value)

    def handle_hanging_process(self, process):
        if process.poll() is None:
            logging.error('%s pid:%s taking to long, sending SIGTERM',
                self.script[0], process.pid)
            os.kill(process.pid, signal.SIGTERM)

    ## Event loop helper methods ##
    def start_process(self, args, handler):
        args = list(self.script + args)

        logging.debug('Starting: %s', ' '.join(args))
        args = map(encode, args)

        try:
            process = subprocess.Popen(args, bufsize=4096,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError, e:
            logging.error('Could not start process: %s', e)
            return False

        self.dispatchers[process.stdout] = handler
        self.dispatchers[process.stderr] = self.handle_stderr

        self.connection.execute_delayed(30, self.handle_hanging_process, [process])

        return True

    def process_data(self, sock, data):
        if sock not in self.recv_buffers:
            self.recv_buffers[sock] = u''

        self.recv_buffers[sock] += decode(data)

        while '\n' in self.recv_buffers[sock]:
            line, trailing = self.recv_buffers[sock].split('\n', 1)
            self.recv_buffers[sock] = trailing

            if line:
                yield line

        if len(data) == 0:
            line = self.recv_buffers[sock]

            del self.recv_buffers[sock]
            del self.dispatchers[sock]
            sock.close()

            if line:
                yield line

    def parse_targets(self, line):
        if encode(self.channel) not in self.channels:
            return [], line

        allowed_targets = self.channels[encode(self.channel)].users()
        allowed_targets = map(decode, allowed_targets)
        allowed_targets.append(self.channel)

        targets = []
        parts = line.split(' ')

        if '@' in parts[0] or '#' in parts[0]:
            valid = lambda s: s[0] in '#@'
            strip = lambda s: s.lstrip('@')
            allowed = lambda s: s in allowed_targets

            targets = parts.pop(0).split(',')
            targets = filter(valid, targets)
            targets = map(strip, targets)
            targets = filter(allowed, targets)

        return targets, ' '.join(parts)

    def send_message(self, message, targets):
        encoded_targets = map(encode, targets)
        encoded_message = encode(message)

        if message.startswith('/me '):
            for target in encoded_targets:
                self.connection.action(target, encoded_message[len('/me '):])
        elif message.startswith('/notice '):
            for target in encoded_targets:
                self.connection.notice(target, encoded_message[len('/notice '):])
        else:
            self.connection.privmsg_many(map(encode, targets), encoded_message)

    ## IRC event handlers ##

    # Initial events
    def on_welcome(self, conn, event):
        conn.join(encode(self.channel))

    def on_nicknameinuse(self, conn, event):
        target = self.target_nick
        tried = decode(event.arguments()[0])
        alternate = tried + '_'

        if alternate != decode(conn.get_nickname()):
            logging.warning('Changing nick to %s', alternate)
            conn.nick(encode(alternate))

        if tried == target:
            logging.warning('Trying to take back %s in 5 minutes', target)
            take_back_inuse_nick = lambda: conn.nick(encode(target))
            self.connection.execute_delayed(60*5, take_back_inuse_nick)

    def on_join(self, conn, event):
        nick = conn.get_nickname()
        joiner = get_nick(event.source())

        if joiner == nick:
            logging.info('%s joined %s', decode(nick), self.channel)
        elif len(self.channels[encode(self.channel)].users()) == 1:
            if not self.opfirst:
                return
            elif self.deop:
                mode = '+o-o+v %s %s %s' % (joiner, nick, nick)
            else:
                mode = '+o %s' % joiner
            conn.mode(encode(self.channel), mode)

    # Regular events
    def on_pubmsg(self, conn, event):
        if not self.script:
            return

        nick = decode(conn.get_nickname())
        target = decode(event.target())
        source= decode(get_nick(event.source()))
        message = decode(event.arguments()[0])
        message = strip_unprintable(message)

        # Can be replaced with string.Template.safe_substitute, but requires 2.4
        match = re.sub(r'(?<!\$)\$nick', nick, self.match or '')
        match = re.sub(r'\$\$nick', '$nick', match)

        try:
            match = re.compile(match, re.UNICODE)
        except re.error, e:
            logging.error('Problem with match expression: %s', e)
            return

        if match and not match.search(message):
            return

        self.start_process([nick, target, source, message],
            lambda s: self.handle_stdout(s, target, source))

    def on_privmsg(self, conn, event):
        nick = decode(conn.get_nickname())
        source = decode(get_nick(event.source()))

        if source != nick:
            self.on_pubmsg(conn, event)

    def on_mode(self, conn, event):
        if decode(event.target()) != self.channel:
            return

        if not self.deop:
            return

        nick = conn.get_nickname()
        modes = parse_channel_modes(' '.join(event.arguments()))

        if ['+', 'o', nick] in modes:
            logging.info('%s was oped, Voicing and deoping', decode(nick))
            conn.mode(encode(self.channel), '+v-o %s %s' % (nick, nick))

    def on_invite(self, conn, event):
        if decode(event.arguments()[0]) == self.channel:
            nick = decode(get_nick(event.source()))
            logging.info('Joining %s due to invite from %s',
                self.channel, nick)
            conn.join(encode(self.channel))

    # Error events
    def on_erroneusnickname(self, conn, event):
        nick = decode(event.arguments()[0])
        logging.critical("Invalid nickname '%s', stopping bot.", nick)
        self.running = False

    def on_badchanmask(self, conn, event):
        channel = decode(event.arguments()[0])
        logging.critical("Invalid channel '%s', stopping bot.", channel)
        self.running = False

    def on_disconnect(self, conn, event):
        message = decode(event.arguments()[0])
        server = decode(event.source())
        logging.warning('Disconnected from %s: %s', server, message)

        if self.irc_socket in self.dispatchers:
            del self.dispatchers[self.irc_socket]

        self.send_buffer = []
        self.connection.send_raw = self.send_buffer.append

    ## Custom connect code that overrides irclib ##
    def _connect(self):
        server = self.server_list[0][0]
        port = self.server_list[0][1]
        password = self.server_list[0][2]

        logging.info('Trying to connect to %s:%s', server, port)

        try:
            self.connect(server, port, self._nickname, password,
                         ircname=self._realname)
        except ServerConnectionError:
            logging.error('Failed to connect to %s:%s', server, port)
            return False

        self.irc_socket = self.connection.socket
        self.dispatchers[self.irc_socket] = self.handle_irc

        # Use TCP keepalive, see 'man tcp' for details about values:
        self.irc_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
        self.irc_socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 150)
        self.irc_socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 30)
        self.irc_socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 5)

        return True

class CustomHelpFormater(IndentedHelpFormatter):
    def format_epilog(self, epilog):
        if epilog:
            return self.parser.expand_prog_name(epilog) + '\n'
        return ''

def optparse():
    parser = OptionParser(usage=USAGE, version=VERSION,
        epilog=EPILOG, formatter=CustomHelpFormater())
    parser.add_option('-d', '--debug',  action='store_const',
        dest='debug', const=logging.DEBUG, help='set log-level to debug')
    parser.add_option('--no-deop', action='store_false',
        dest='deop', default=True, help='prevent bot from deoping itself')
    parser.add_option('--op-first', action='store_false', dest='opfirst',
        default=True, help='op first user to join channel if bot is alone')
    parser.add_option('--listen', metavar='[addr]:port',
        help='address to bind listener to')
    parser.add_option('--realname', metavar='name',
        help='realname to provide to IRC server')
    parser.add_option('--script', metavar='path',
        help='script to send messages to')
    parser.add_option('--args', metavar='arg', default=[],
        help='extra arugments to send script', action='append')

    return parser

def parse_host_port_password(string, default='host'):
    password = None
    if '/' in string:
        string, password = string.split('/', 1)
        password = dequote(password)
    if ':' in string:
        host, port = string.split(':', 1)
    elif default == 'port':
        host, port = '', string
    else:
        host, port = string, ''

    if port and port.isdigit():
        return (host, int(port), password)
    elif port:
        return (host, -1, password)
    else:
        return (host, '', password)

def main():
    parser = optparse()
    (options, args) = parser.parse_args()

    if len(args) != 3:
        parser.print_help()
        return

    logging.basicConfig(level=options.debug or logging.INFO,
        format="[%(asctime)s] %(message)s")

    servers, nickname, channel = args

    if not is_channel(channel):
        channel = '#' + channel

    server_list = []
    listen = None

    # regex from http://stackoverflow.com/a/16710842
    for addr in re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', servers):
        host, port, password = parse_host_port_password(addr)

        if port == -1:
            parser.error('server argument got an invalid port number')
        else:
            server_list.append((host, port or 6667, password))

    if options.listen:
        host, port, password = parse_host_port_password(options.listen, 'port')

        if port == -1:
            parser.error('--listen got an invalid port number')
        else:
            listen = (host or '', port)

    if options.script:
        script = [options.script] + options.args
    else:
        script = []

    pycat = PyCat(server_list, nickname, options.realname or nickname,
        channel, listen, script, options.deop, options.opfirst)

    try:
        pycat.start()
    except KeyboardInterrupt:
        pass

    pycat.stop()

if __name__ == '__main__':
    main()
