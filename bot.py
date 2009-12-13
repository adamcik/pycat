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
        target, line = line[1:].split(' ', 1)
    else:
        target = bot.config['channel']

    bot.irc_command('PRIVMSG', target, line)

def update_nicks(prefix, command, args):
    if command == 'JOIN':
        nicks.add(prefix.split('!')[0])
    elif command in ['QUIT', 'PART']:
        nicks.remove(prefix.split('!')[0])
    else:
        for nick in args[-1].split():
            nicks.add(nick)

def join(prefix, command, args):
    bot.irc_command('JOIN', channel)

listener.add(parse)

bot.add('CONNECT', join)
bot.add('JOIN', update_nicks)
bot.add('PART', update_nicks)
bot.add('QUIT', update_nicks)
bot.add('353', update_nicks)

try:
    bot.run()
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc_command('QUIT', 'Bye :)')
    sys.exit(0)
