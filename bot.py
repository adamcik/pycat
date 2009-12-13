#!/usr/bin/python

import sys
import asyncore
import logging

from irc import Bot

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

bot = Bot('localhost')

try:
    bot.run()
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc_command('QUIT', 'Bye :)')
    sys.exit(0)
