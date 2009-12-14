#! /usr/bin/python

import sys
import asyncore
import logging

from irc import Bot
from listener import Listener

# FIXME figure out async subprocess
# FIXME use optparse and/or configreader
# FIXME reconncet on disconnect

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

channel = '#adamcik-test'
nicks= set()
bot = Bot('localhost')
listener = Listener()

def parse(line):
    if line.startswith('@'): # FIXME: ValueError on split
        target, message = line[1:].split(' ', 1)
    else:
        target = channel
        message =  line

    # FIXME avoid sending msg on fail
    if line.startswith('@') and target not in nicks:
        target = channel
        message = line

    # FIXME parse commands from users?
    bot.irc.privmsg(target, message)

def join(prefix, command, args):
    bot.irc.join(channel)

listener.add(parse)

# FIXME queue events to run after register?
bot.add('CONNECT', join)

try:
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc.quit('Bye :)')
    sys.exit(0)
