import asynchat
import asyncore
import logging
import socket

logger = logging.getLogger('listener')

class Reciver(asynchat.async_chat):
    def __init__(self, server, (conn, addr)):
        asynchat.async_chat.__init__(self, conn)

        self.set_terminator('\n')
        self.server = server
        self.addr = addr
        self.buffer = ''

    def collect_incoming_data(self, data):
        self.buffer += data

    def found_terminator(self):
        line, self.buffer = self.buffer, ''

        try:
            line = line.decode('utf-8')
        except UnicodeDecodeError:
            line = line.decode('iso-8859-1')

        logger.debug('Listener (%s:%s): %s', self.addr[0], self.addr[1], line)

        for handler in self.server.handlers:
            handler(line)

class Listener(asyncore.dispatcher):
    def __init__(self, port=12345):
        asyncore.dispatcher.__init__(self)

        self.port = port
        self.handlers = []

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', self.port))
        self.listen(5)

    def handle_accept(self):
        Reciver(self, self.accept())

    def add_handler(self, handler):
        self.handlers.append(handler)
