import unittest
from unittest.mock import Mock
from src.transport import SocketReader, send_response
from src.http_response import chunked_response


class ChunkTests(unittest.TestCase):
    def test_fragmented_chunks_preserve_next_request(self):
        connection = Mock()
        connection.recv.side_effect = [b"3\r", b"\nabc\r\n2\r\nde\r\n0\r\n\r\nNEXT"]
        reader = SocketReader(connection)
        self.assertEqual(reader.read_chunked(), b"abcde")
        self.assertEqual(reader.buffer, b"NEXT")

    def test_decoded_limit_and_bad_sizes_are_rejected(self):
        for wire, limit in ((b"6\r\nabcdef\r\n0\r\n\r\n", 5), (b"no\r\n", 100)):
            connection = Mock()
            connection.recv.return_value = wire
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                SocketReader(connection).read_chunked(limit)

    def test_response_chunks_have_terminal_marker_and_no_length(self):
        connection = Mock()
        response = chunked_response(iter([b"abc", b"de"]))
        send_response(connection, response)
        wire = b"".join(call.args[0] for call in connection.sendall.call_args_list)
        self.assertNotIn(b"Content-Length", wire)
        self.assertTrue(wire.endswith(b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n"))
