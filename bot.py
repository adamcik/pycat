#! /usr/bin/python

import asyncore
import logging
import subprocess
import sys

from irc import Bot
from listener import Listener

# FIXME figure out async subprocess
# FIXME use optparse and/or configreader
# FIXME reconncet on disconnect

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

channels = ['#adamcik-test', '#foo', '#baz']
bot = Bot('localhost')
listener = Listener()

def listen_parser(line):
    if not line.strip():
        return

    if line[0] in '@#':
        parts  = line.split(' ', 1)
        targets = set(parts[0].split(','))
        message = ' '.join(parts[1:])
    else:
        targets = set([channels[0]])
        message = line

    if not message.strip():
        return

    if '#*' in targets:
        targets.remove('#*')
        for target in channels:
            targets.add(target)

    for target in targets:
        if target.startswith('@'):
            target = target[1:]

        if bot.known_target(target):
            if message.startswith('/me '):
                bot.irc.ctcp_action(target, message[len('/me '):])
            else:
                bot.irc.privmsg(target, message)

def privmsg_parser(prefix, command, args):
    user = prefix.split('!')[0]
    target, message = args

    if not message[0] in '!?':
        if target == bot.current_nick:
            bot.irc.privmsg(user, "I don't understand what you want.")

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

    if target == bot.current_nick:
        for line in response.split('\n'):
            if line.strip():
                bot.irc.privmsg(user, line)
    else:
        for line in response.split('\n'):
            if line.strip():
                bot.irc.privmsg(target, line)

def connect_join(prefix, command, args):
    for channel in channels:
        bot.irc.join(channel)

def invite_rejoin(prefix, command, args):
    if args[-1] in channels:
        bot.irc.join(args[-1])

listener.add(listen_parser)

bot.add('376', connect_join)
bot.add('INVITE', invite_rejoin)
bot.add('PRIVMSG', privmsg_parser)

try:
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc.quit('Bye :)')
    sys.exit(0)
