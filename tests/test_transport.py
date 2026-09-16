import unittest
from unittest.mock import Mock

from src.transport import SocketReader


class ReaderTests(unittest.TestCase):
    def test_fragmented_headers_preserve_following_bytes(self):
        connection = Mock()
        connection.recv.side_effect = [b"GET / HTTP/1.1\r", b"\nHost: local\r\n\r", b"\nbody"]
        reader = SocketReader(connection)
        self.assertEqual(reader.read_until(b"\r\n\r\n"), b"GET / HTTP/1.1\r\nHost: local\r\n\r\n")
        self.assertEqual(reader.buffer, b"body")

    def test_partial_disconnect_is_an_error(self):
        connection = Mock()
        connection.recv.side_effect = [b"GET", b""]
        with self.assertRaises(ValueError):
            SocketReader(connection).read_until(b"\r\n\r\n")

    def test_oversized_header_is_rejected(self):
        connection = Mock()
        connection.recv.return_value = b"x" * 20
        with self.assertRaises(ValueError):
            SocketReader(connection).read_until(b"\r\n\r\n", limit=16)

    def test_header_limit_does_not_count_buffered_body(self):
        connection = Mock()
        connection.recv.return_value = b"head\r\n\r\n" + b"body" * 20
        reader = SocketReader(connection)
        self.assertEqual(reader.read_until(b"\r\n\r\n", limit=8), b"head\r\n\r\n")
        self.assertEqual(len(reader.buffer), 80)
