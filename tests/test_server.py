"""Regression tests for the boundaries introduced by the server refactor."""

import contextlib
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from src.http_request import parse_request
from src.http_response import build_response, error_response, format_http_date
from src.static_files import serve_file
from src.webserver import handle_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RequestTests(unittest.TestCase):
    def test_parse_request_and_case_insensitive_headers(self):
        request = parse_request(
            "GET /nested/ HTTP/1.1\r\nHost: localhost:6789\r\n"
            "IF-MODIFIED-SINCE: Tue, 01 Jan 2030 00:00:00 GMT\r\n\r\n"
        )
        self.assertEqual((request.method, request.path, request.version),
                         ("GET", "/nested/", "HTTP/1.1"))
        self.assertEqual(request.headers["host"], "localhost:6789")
        self.assertEqual(request.headers["if-modified-since"],
                         "Tue, 01 Jan 2030 00:00:00 GMT")

    def test_duplicate_header_uses_first_value_and_body_is_not_headers(self):
        request = parse_request(
            "GET / HTTP/1.1\r\nHost: first\r\nhost: second\r\n\r\nFake: body"
        )
        self.assertEqual(request.headers, {"host": "first"})

    def test_empty_or_missing_path_is_rejected(self):
        for message in ("", "\r\n", "GET"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                parse_request(message)

    def test_existing_method_and_path_only_subset_is_preserved(self):
        request = parse_request("GET /")
        self.assertEqual(request.version, "")
        self.assertEqual(request.path, "/")


class ResponseTests(unittest.TestCase):
    def test_serialized_response_uses_byte_length_and_header_terminator(self):
        body = "café".encode("utf-8")
        response = build_response(200, body, {"Content-Type": "text/html"})
        wire = response.header_bytes() + response.body
        headers, received_body = wire.split(b"\r\n\r\n", 1)
        self.assertTrue(headers.startswith(b"HTTP/1.1 200 OK\r\n"))
        self.assertIn(b"Content-Length: 5", headers)
        self.assertIn(b"Connection: close", headers)
        self.assertEqual(received_body, body)

    def test_not_modified_is_bodyless(self):
        response = build_response(304, b"discarded", {"Last-Modified": "example"})
        self.assertEqual(response.body, b"")
        self.assertNotIn("Content-Length", response.headers)
        self.assertIn(b"HTTP/1.1 304 Not Modified", response.header_bytes())

    def test_error_responses_have_consistent_framing(self):
        for status in (404, 405, 415):
            with self.subTest(status=status):
                response = error_response(status)
                self.assertEqual(response.status, status)
                self.assertEqual(int(response.headers["Content-Length"]), len(response.body))
                self.assertEqual(response.headers["Content-Type"], "text/html")
                self.assertIn(str(status).encode(), response.body)


class StaticFileTests(unittest.TestCase):
    def setUp(self):
        self.original_directory = os.getcwd()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.original_directory)
        os.chdir(self.directory.name)
        Path("index.html").write_text("hello café", encoding="utf-8")
        Path("page.htm").write_text("page", encoding="utf-8")
        Path("nested").mkdir()
        Path("nested/index.html").write_text("nested", encoding="utf-8")
        Path("test.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
        os.utime("index.html", (1600000000, 1600000000))

    def request(self, path="/", headers="", method="GET"):
        return parse_request("{} {} HTTP/1.1\r\n{}\r\n".format(method, path, headers))

    def test_root_directory_and_extension_fallback_routes(self):
        for path, expected in (("/", "hello café"), ("/index", "hello café"),
                               ("/page", "page"), ("/nested", "nested"),
                               ("/nested/", "nested")):
            with self.subTest(path=path):
                response = serve_file(self.request(path))
                self.assertEqual(response.status, 200)
                self.assertEqual(response.body, expected.encode("utf-8"))
                self.assertEqual(response.headers["Content-Type"], "text/html")

    def test_binary_file_bytes_are_preserved(self):
        response = serve_file(self.request("/test.png"))
        self.assertEqual(response.body, Path("test.png").read_bytes())
        self.assertEqual(response.headers["Content-Type"], "image/png")

    def test_existing_errors_and_allow_header(self):
        self.assertEqual(serve_file(self.request("/missing.html")).status, 404)
        self.assertEqual(serve_file(self.request("/missing.txt")).status, 415)
        response = serve_file(self.request(method="POST"))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.headers["Allow"], "GET")

    def test_conditional_get_returns_not_modified(self):
        date = format_http_date(1600000000)
        response = serve_file(self.request(headers="If-Modified-Since: " + date))
        self.assertEqual(response.status, 304)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.headers["Last-Modified"], date)

    def test_old_or_invalid_cache_date_returns_content(self):
        for date in (format_http_date(1500000000), "invalid date"):
            with self.subTest(date=date):
                response = serve_file(self.request(headers="If-Modified-Since: " + date))
                self.assertEqual(response.status, 200)
                self.assertEqual(response.body, "hello café".encode("utf-8"))

    def test_file_access_error_builds_normal_404_response(self):
        with patch("src.static_files.open", side_effect=PermissionError("denied")):
            response = serve_file(self.request())
        self.assertEqual(response.status, 404)
        self.assertEqual(int(response.headers["Content-Length"]), len(response.body))

    def test_real_socket_round_trip_and_close(self):
        server, client = socket.socketpair()
        client.settimeout(2)
        worker_errors = []

        def worker():
            try:
                handle_connection(server)
            except Exception as error:
                worker_errors.append(error)

        thread = threading.Thread(target=worker, daemon=True)
        with client, contextlib.redirect_stdout(io.StringIO()):
            thread.start()
            try:
                client.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                wire = b""
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    wire += chunk
            finally:
                client.close()
                thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(worker_errors, [])
        headers, body = wire.split(b"\r\n\r\n", 1)
        self.assertTrue(headers.startswith(b"HTTP/1.1 200 OK\r\n"))
        self.assertEqual(body, "hello café".encode("utf-8"))
        self.assertEqual(server.fileno(), -1)


class ConnectionTests(unittest.TestCase):
    def test_invalid_request_closes_without_sending(self):
        connection = Mock()
        connection.recv.return_value = b"GET"
        with contextlib.redirect_stdout(io.StringIO()):
            handle_connection(connection)
        connection.send.assert_not_called()
        connection.close.assert_called_once_with()

    def test_receive_error_closes_without_sending_file_error(self):
        connection = Mock()
        connection.recv.side_effect = ConnectionResetError("disconnected")
        with contextlib.redirect_stderr(io.StringIO()):
            handle_connection(connection)
        connection.send.assert_not_called()
        connection.close.assert_called_once_with()

    def test_send_failure_closes_without_retrying_a_404(self):
        connection = Mock()
        connection.recv.return_value = b"POST / HTTP/1.1\r\n\r\n"
        connection.send.side_effect = BrokenPipeError("disconnected")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            handle_connection(connection)
        self.assertEqual(connection.send.call_count, 1)
        connection.close.assert_called_once_with()


class CLITests(unittest.TestCase):
    def test_script_and_module_entry_points(self):
        for arguments in (("src/webserver.py", "-h"), ("-m", "src.webserver", "-h")):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable] + list(arguments), cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertIn(b"webserver.py -p <port number>", result.stdout)


if __name__ == "__main__":
    unittest.main()
