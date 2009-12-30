#! /usr/bin/python

import asyncore
import logging
import subprocess
import sys

from irc import Bot
from listener import Listener

# FIXME figure out async subprocess
# FIXME use optparse and/or configreader

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

CHANNEL = '#foo'

bot = Bot(('localhost', 6667), 'pycat', 'pycat', CHANNEL)
listener = Listener()

def listen_parser(line):
    if not line.strip():
        return

    if line.startswith('/me '):
        bot.irc.ctcp_action(CHANNEL, line[len('/me '):])
    elif line.startswith('/notice '):
        bot.irc.notice(CHANNEL, line[len('/notice '):])
    else:
        bot.irc.privmsg(CHANNEL, line)

def msg_parser(nick=None, user=None, host=None, command=None, args=None):
    target, message = args

    if not message[0] in '!?':
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

    for line in response.split('\n'):
        if line.strip():
            bot.irc.privmsg(CHANNEL, line)

def invite_rejoin(nick=None, user=None, host=None, command=None, args=None):
    bot.irc.join(args[-1])

listener.add_handler(listen_parser)

bot.add_handler('INVITE', invite_rejoin)
bot.add_handler('PRIVMSG', msg_parser)

try:
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc.quit('Bye :)')
    sys.exit(0)
