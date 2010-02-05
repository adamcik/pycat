pyCAT
=====

A simplified irccat 'clone'.

Main features of pyCAT are:

1) Listen on a given port and relay messages to an IRC channel.

2) Send messages in channel to an external script for parsing, passing output
   back to channel.

Dependencies
------------

pyCAT requires Python and irclib.py (http://python-irclib.sourceforge.net/).

Usage
-----

    Usage: pycat.py server[:port][,server[:port]] nickname channel [options]
    
    Options:
      --version             show program's version number and exit
      -h, --help            show this help message and exit
      -d, --debug           set log-level to debug
      --no-deop             prevent bot from deoping itself
      --listen=[addr]:port  address to bind listener to
      --realname=name       realname to provide to IRC server
      --script=path         script to send messages to
      --args=arg            extra arugments to send script
    
    Examples:
      Connect to irc.efnet.net, with nick cat, name 'Majo nes', script /foo/bar:
        pycat.py irc.efnet.net cat efnet --realname='Majo Nes' --script=/foo/bar
      Use multiple fallbacks on IRCnet, nick cat, channel pycat
        pycat.py irc.ifi.uio.no,irc.hitos.no,irc.pvv.org:6668 cat '#pycat'
      Connect to localhost, listen on port 12345 on all interfaces:
        pycat.py localhost cat '#pycat' --listen=12345
      Connect to irc.freenode.net, listen on port 8000 on a specific interface:
        pycat.py irc.freenode.net cat '#pycat' --listen=example.com:8000

Running
-------

By default pyCAT will not listen or pass messages to any scripts. This
functionality is strictly opt-in.

    pycat irc.example.com pycat #pycat

Will start the bot without the listener or message parsing enabled. For
more details on how to run pycat execute `pycat --help`.

**Listen**:
To enable the listen feature start pycat with --listen address:port and
the bot will listen for messages on the specified interface and port.
Messages that start with /me or /notice will be converted to CTCP ACTIONs
and NOTICE commands.

    pycat server pycat #pycat --listen 12345 &
    echo "Hello world" | nc localhost 12345

Will bind port 12345 on all interfaces. Sending messages can easily be achieved
with netcat. Messages starting with @ or # will be interpreted as messages
intended for the given nick or channel. If the user is not in the same channel
as the bot the message will be discarded.

    pycat server pycat #pycat --listen 12345 &
    echo "@foo Hello foo" | nc 12345
    echo "@foo,@bar,#pycat Hello all" | nc 12345

**Script**:
Starting pycat with --script path instructs the bot to execute the file found at
path with:

    pycat $NICK $TARGET $SOURCE $MESSAGE

Any data written back to STDOUT will be sent to the same place the message
originates from. Normally only messages that start with ! will be sent to the
script. When the bot starts or when the script is modified it will be called
with `--config nick`. The script should reply with `key = value` config
settings.  Currently only `match = regexp` is supported, this setting modifies
which messages are sent to the script. See example.sh for simple hello world
script.

License
-------

pyCAT is released under the MIT license, see COPYING.

Inspiration
-----------

There is no hiding the fact that this project is inspired by irccat
(http://github.com/RJ/irccat).
