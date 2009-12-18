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

bot = Bot('localhost')
listener = Listener()

def listen_parser(line):
    if not line.strip():
        return

    if message.startswith('/me '):
        bot.irc.ctcp_action(target, message[len('/me '):])
    elif message.startswith('/notice '):
        bot.irc.notice(target, message[len('/notice '):])
    else:
        bot.irc.privmsg(target, message)

def privmsg_parser(nick=None, user=None, host=None, command=None, args=None):
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

def invite_rejoin(nick=None, user=None, host=None, command=None, args=None):
    bot.irc.join(args[-1])

listener.add(listen_parser)

bot.add('INVITE', invite_rejoin)
bot.add('PRIVMSG', privmsg_parser)

try:
    asyncore.loop()
except KeyboardInterrupt:
    bot.irc.quit('Bye :)')
    sys.exit(0)
