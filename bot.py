#!/usr/bin/python

import sys
import asyncore
import logging

from irc import Bot
from listener import Listener

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

channel = '#adamcik-test'
nicks= set()
bot = Bot('localhost')
listener = Listener()

def parse(line):
    if line.startswith('@'):
        target, message = line[1:].split(' ', 1)
    else:
        target = channel
        message =  line

    if line.startswith('@') and target not in nicks:
        target = channel
        message = line

    bot.irc.privmsg(target, message)

def join(prefix, command, args):
    bot.irc.join(channel)

listener.add(parse)

bot.add('CONNECT', join)

try:
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc.quit('Bye :)')
    sys.exit(0)
