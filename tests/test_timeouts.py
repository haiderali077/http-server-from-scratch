import socket
import threading
import unittest
from src.limits import Timeouts
from src.webserver import handle_connection


class TimeoutTests(unittest.TestCase):
    def test_partial_header_times_out_with_408(self):
        server, client = socket.socketpair()
        worker = threading.Thread(target=handle_connection,
                                  args=(server,), kwargs={"timeouts": Timeouts(header=0.05)})
        with client:
            client.settimeout(1)
            worker.start()
            client.sendall(b"GET / HTTP/1.1\r\n")
            response = client.recv(4096)
            self.assertTrue(response.startswith(b"HTTP/1.1 408"))
        worker.join(1)
        self.assertFalse(worker.is_alive())
