#!/usr/bin/python

import sys
import asyncore
import logging

from irc import Bot
from listener import Listener

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

bot = Bot('localhost')
listener = Listener()

def parse(line):
    if line.startswith('@'):
        target, line = line[1:].split(' ', 1)
    else:
        target = bot.config['channel']

    bot.irc_command('PRIVMSG', target, line)

listener.add(parse)

try:
    bot.run()
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc_command('QUIT', 'Bye :)')
    sys.exit(0)
