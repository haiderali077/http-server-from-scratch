import unittest
import socket
from unittest.mock import patch
from src.proxy import response_header, response_body
from src.transport import SocketReader
from src.proxy import response_chunks
from src.http_request import HTTPRequest


class BytesSocket:
    def __init__(self, data):
        self.data = data
    def recv(self, size):
        result, self.data = self.data[:size], self.data[size:]
        return result
    def settimeout(self, timeout):
        pass


class UpstreamProtocolTests(unittest.TestCase):
    def test_total_header_deadline(self):
        reader = SocketReader(BytesSocket(b"HTTP/1.1 100 Continue\r\n\r\n"))
        with patch("src.proxy.time.monotonic", side_effect=[0, 0, 0, 0, 2, 2, 2]):
            with self.assertRaises(socket.timeout):
                response_header(reader, 1)

    def decode(self, raw, method="GET"):
        reader = SocketReader(BytesSocket(raw))
        status, headers = response_header(reader)
        request = HTTPRequest(method, "/", "", "HTTP/1.1", {})
        return status, headers, response_body(reader, request, status, headers)

    def test_fixed_chunked_and_close_delimited(self):
        for framing, body in [(b"Content-Length: 3\r\n", b"abc"), (b"Transfer-Encoding: chunked\r\n", b"3\r\nabc\r\n0\r\n\r\n"), (b"", b"abc")]:
            self.assertEqual(self.decode(b"HTTP/1.1 200 OK\r\n" + framing + b"\r\n" + body)[2], b"abc")

    def test_bodyless_and_informational(self):
        self.assertEqual(self.decode(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 204 Empty\r\n\r\n")[2], b"")
        self.assertEqual(self.decode(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n", "HEAD")[2], b"")

    def test_reject_ambiguous_or_bad_headers(self):
        for fields in [b"Content-Length: 1\r\nContent-Length: 1\r\n", b"Content-Length: 1\r\nTransfer-Encoding: chunked\r\n", b"Bad Name: x\r\n", b"Transfer-Encoding: gzip\r\n"]:
            with self.assertRaises(ValueError):
                self.decode(b"HTTP/1.1 200 OK\r\n" + fields + b"\r\nx")

    def test_cookie_fields_remain_separate(self):
        _, fields, _ = self.decode(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nSet-Cookie: a=1\r\nSet-Cookie: b=2\r\n\r\n")
        self.assertEqual(fields["set-cookie"], ["a=1", "b=2"])

    def test_chunk_payloads_are_bounded(self):
        body = b"x" * 100000
        reader = SocketReader(BytesSocket(b"186a0\r\n" + body + b"\r\n0\r\n\r\n"))
        request = HTTPRequest("GET", "/", "", "HTTP/1.1", {})
        chunks = list(response_chunks(reader, request, 200, {"transfer-encoding": "chunked"}))
        self.assertEqual(b"".join(chunks), body)
        self.assertLessEqual(max(map(len, chunks)), 16384)
