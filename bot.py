#!/usr/bin/python

import asynchat
import asyncore
import re
import socket

class Bot(asynchat.async_chat):
    config = {
        'nick': 'adamcik-bot',
        'username': 'adamcik',
        'hostname': socket.getfqdn(),
        'servername': socket.getfqdn(),
        'realname': 'adamcik',
        'channel': '#adamcik-test',
    }

    def __init__(self, server, port=6667):
        asynchat.async_chat.__init__(self)

        self.server = server
        self.port = port

        self.buffer = ''
        self.handlers = {}
        self.set_terminator("\r\n")

        self.add('PING', self.ping_handler)

    def run(self):
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((self.server, self.port))

        asyncore.loop()

    def add(self, command, handler):
        if command not in self.handlers:
            self.handlers[command] = []

        self.handlers[command].append(handler)

    def ping_handler(self, prefix, command, args):
        self.write('PONG', args[0])

    def handle_command(self, prefix, command, args):
        for handler in self.handlers.get(command, []):
            handler(prefix, command, args)

    def handle_connect(self):
        self.write('NICK', self.config['nick'])
        self.write('USER', '%(username)s %(hostname)s %(servername)s :%(realname)s' % self.config)
        self.write('JOIN', self.config['channel'])

    def collect_incoming_data(self, data):
        self.buffer += data

    def found_terminator(self):
        line, self.buffer = self.buffer, ''

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

        self.handle_command(prefix, command, args)

    def write(self, *args):
        self.push(' '.join(args) + '\r\n')

    replies = {
        '200': 'RPL_TRACELINK',
        '201': 'RPL_TRACECONNECTING',
        '202': 'RPL_TRACEHANDSHAKE',
        '203': 'RPL_TRACEUNKNOWN',
        '204': 'RPL_TRACEOPERATOR',
        '205': 'RPL_TRACEUSER',
        '206': 'RPL_TRACESERVER',
        '208': 'RPL_TRACENEWTYPE',
        '211': 'RPL_STATSLINKINFO',
        '212': 'RPL_STATSCOMMANDS',
        '213': 'RPL_STATSCLINE',
        '214': 'RPL_STATSNLINE',
        '215': 'RPL_STATSILINE',
        '216': 'RPL_STATSKLINE',
        '218': 'RPL_STATSYLINE',
        '219': 'RPL_ENDOFSTATS',
        '221': 'RPL_UMODEIS',
        '241': 'RPL_STATSLLINE',
        '242': 'RPL_STATSUPTIME',
        '243': 'RPL_STATSOLINE',
        '244': 'RPL_STATSHLINE',
        '251': 'RPL_LUSERCLIENT',
        '252': 'RPL_LUSEROP',
        '253': 'RPL_LUSERUNKNOWN',
        '254': 'RPL_LUSERCHANNELS',
        '255': 'RPL_LUSERME',
        '256': 'RPL_ADMINME',
        '257': 'RPL_ADMINLOC1',
        '258': 'RPL_ADMINLOC2',
        '259': 'RPL_ADMINEMAIL',
        '261': 'RPL_TRACELOG',
        '300': 'RPL_NONE',
        '301': 'RPL_AWAY',
        '302': 'RPL_USERHOST',
        '303': 'RPL_ISON',
        '305': 'RPL_UNAWAY',
        '306': 'RPL_NOWAWAY',
        '311': 'RPL_WHOISUSER',
        '312': 'RPL_WHOISSERVER',
        '313': 'RPL_WHOISOPERATOR',
        '314': 'RPL_WHOWASUSER',
        '315': 'RPL_ENDOFWHO',
        '317': 'RPL_WHOISIDLE',
        '318': 'RPL_ENDOFWHOIS',
        '319': 'RPL_WHOISCHANNELS',
        '321': 'RPL_LISTSTART',
        '322': 'RPL_LIST',
        '323': 'RPL_LISTEND',
        '324': 'RPL_CHANNELMODEIS',
        '331': 'RPL_NOTOPIC',
        '332': 'RPL_TOPIC',
        '341': 'RPL_INVITING',
        '342': 'RPL_SUMMONING',
        '351': 'RPL_VERSION',
        '352': 'RPL_WHOREPLY',
        '353': 'RPL_NAMREPLY',
        '364': 'RPL_LINKS',
        '365': 'RPL_ENDOFLINKS',
        '366': 'RPL_ENDOFNAMES',
        '367': 'RPL_BANLIST',
        '368': 'RPL_ENDOFBANLIST',
        '369': 'RPL_ENDOFWHOWAS',
        '371': 'RPL_INFO',
        '372': 'RPL_MOTD',
        '374': 'RPL_ENDOFINFO',
        '375': 'RPL_MOTDSTART',
        '376': 'RPL_ENDOFMOTD',
        '381': 'RPL_YOUREOPER',
        '382': 'RPL_REHASHING',
        '391': 'RPL_TIME',
        '392': 'RPL_USERSSTART',
        '393': 'RPL_USERS',
        '394': 'RPL_ENDOFUSERS',
        '395': 'RPL_NOUSERS',
        '401': 'ERR_NOSUCHNICK',
        '402': 'ERR_NOSUCHSERVER',
        '403': 'ERR_NOSUCHCHANNEL',
        '404': 'ERR_CANNOTSENDTOCHAN',
        '405': 'ERR_TOOMANYCHANNELS',
        '406': 'ERR_WASNOSUCHNICK',
        '407': 'ERR_TOOMANYTARGETS',
        '409': 'ERR_NOORIGIN',
        '411': 'ERR_NORECIPIENT',
        '412': 'ERR_NOTEXTTOSEND',
        '413': 'ERR_NOTOPLEVEL',
        '414': 'ERR_WILDTOPLEVEL',
        '421': 'ERR_UNKNOWNCOMMAND',
        '422': 'ERR_NOMOTD',
        '423': 'ERR_NOADMININFO',
        '424': 'ERR_FILEERROR',
        '431': 'ERR_NONICKNAMEGIVEN',
        '432': 'ERR_ERRONEUSNICKNAME',
        '433': 'ERR_NICKNAMEINUSE',
        '436': 'ERR_NICKCOLLISION',
        '441': 'ERR_USERNOTINCHANNEL',
        '442': 'ERR_NOTONCHANNEL',
        '443': 'ERR_USERONCHANNEL',
        '444': 'ERR_NOLOGIN',
        '445': 'ERR_SUMMONDISABLED',
        '446': 'ERR_USERSDISABLED',
        '451': 'ERR_NOTREGISTERED',
        '461': 'ERR_NEEDMOREPARAMS',
        '462': 'ERR_ALREADYREGISTRED',
        '463': 'ERR_NOPERMFORHOST',
        '464': 'ERR_PASSWDMISMATCH',
        '465': 'ERR_YOUREBANNEDCREEP',
        '467': 'ERR_KEYSET',
        '471': 'ERR_CHANNELISFULL',
        '472': 'ERR_UNKNOWNMODE',
        '473': 'ERR_INVITEONLYCHAN',
        '474': 'ERR_BANNEDFROMCHAN',
        '475': 'ERR_BADCHANNELKEY',
        '481': 'ERR_NOPRIVILEGES',
        '482': 'ERR_CHANOPRIVSNEEDED',
        '483': 'ERR_CANTKILLSERVER',
        '491': 'ERR_NOOPERHOST',
        '501': 'ERR_UMODEUNKNOWNFLAG',
        '502': 'ERR_USERSDONTMATCH',
    }


#Bot('localhost').run()
Bot('irc.ifi.uio.no').run()
