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

channels = ['#adamcik-test']
bot = Bot('localhost')
listener = Listener()

def listen_parser(line):
    if line.startswith('@'): # FIXME: ValueError on split
        target, message = line[1:].split(' ', 1)
    elif line.startswith('#') or line.startswith('&'):
        target, message = line.split(' ', 1)
    else:
        target = channels[0]
        message = line

    if bot.known_target(target):
        bot.irc.privmsg(target, message)

def msg_parser(prefix, command, args):
    user = prefix.split('!')[0]
    target, message = args

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

def join(prefix, command, args):
    for channel in channels:
        bot.irc.join(channel)

def invite_rejoin(prefix, command, args):
    if args[-1] in channels:
        bot.irc.join(args[-1])

listener.add(listen_parser)

# FIXME queue events to run after register?
bot.add('CONNECT', join)
bot.add('INVITE', invite_rejoin)
bot.add('PRIVMSG', msg_parser)

try:
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc.quit('Bye :)')
    sys.exit(0)
