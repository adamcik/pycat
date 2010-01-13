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
irclib >= 0.4.7 required for IPv6 support.

Running
-------

By default pyCAT will not listen or pass messages to any scripts. This
functionality is strictly opt-in.

    pycat irc.example.com pycat #pycat

Will start the bot without the listener or message parsing enabled. For
more details on how to run pycat execute `pycat --help`.

Listen:
To enable the listen feature start pycat with --listen address:port and
the bot will listen for messages on the specified interface and port.
Messages that start with /me or /notice will be converted to CTCP ACTIONs
and NOTICE commands.

    pycat server pycat #pycat --listen :12345 &
    echo "Hello world" | nc localhost 12345

Will bind port 12345 on all interfaces. Sending messages can easily be achieved
with netcat. Messages starting with @ will be interpreted as messages intended
for the given nick. If the user is not in the same channel as the bot the message
will be discarded.

Script:
Starting pycat with --script path instructs the bot to execute the file found at
path with:

    path $NICK $CHANNEL $SENDER $MESSAGE

Any data written back to STDOUT will be sent to the channel. See example.sh for
a simple hello world script.

License
-------

pyCAT is released under the MIT license, see COPYING.

Inspiration
-----------

There is no hiding the fact that this project is inspired by irccat
(http://github.com/RJ/irccat).
