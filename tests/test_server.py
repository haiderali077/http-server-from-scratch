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
import time
import unittest
from unittest.mock import Mock, patch

from src.http_request import parse_request, parse_request_target
from src.http_response import build_response, error_response, format_http_date
from src.static_files import DEFAULT_DOCUMENT_ROOT, PathOutsideDocumentRoot, resolve_filename, serve_file
from src.webserver import handle_connection, main, run_server


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RequestTests(unittest.TestCase):
    def test_parse_request_and_case_insensitive_headers(self):
        request = parse_request(
            "GET /nested/ HTTP/1.1\r\nHost: localhost:6789\r\n"
            "IF-MODIFIED-SINCE: Tue, 01 Jan 2030 00:00:00 GMT\r\n\r\n"
        )
        self.assertEqual((request.method, request.path, request.version),
                         ("GET", "/nested/", "HTTP/1.1"))
        self.assertEqual(request.query, "")
        self.assertEqual(request.headers["host"], "localhost:6789")
        self.assertEqual(request.headers["if-modified-since"],
                         "Tue, 01 Jan 2030 00:00:00 GMT")

    def test_duplicate_host_header_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_request("GET / HTTP/1.1\r\nHost: first\r\nhost: second\r\n\r\n")

    def test_empty_or_missing_path_is_rejected(self):
        for message in ("", "\r\n", "GET"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                parse_request(message)

    def test_version_and_http11_host_are_required(self):
        for message in ("GET /", "GET / HTTP/1.1\r\n\r\n", "GET / HTTP/2.0\r\nHost: local\r\n\r\n"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                parse_request(message)

    def test_query_is_separate_from_the_path(self):
        request = parse_request(
            "GET /nested/index.html?download=1&theme=dark HTTP/1.1\r\nHost: local\r\n\r\n"
        )
        self.assertEqual(request.path, "/nested/index.html")
        self.assertEqual(request.query, "download=1&theme=dark")

    def test_path_is_percent_decoded_once_and_query_remains_raw(self):
        path, query = parse_request_target("/caf%C3%A9.html?label=caf%C3%A9")
        self.assertEqual(path, "/café.html")
        self.assertEqual(query, "label=caf%C3%A9")

    def test_plus_is_literal_in_a_path_and_only_first_question_mark_splits(self):
        path, query = parse_request_target("/a+b.html?first=yes?second=yes")
        self.assertEqual(path, "/a+b.html")
        self.assertEqual(query, "first=yes?second=yes")

    def test_invalid_percent_sequences_are_rejected(self):
        for target in ("/file%", "/file%2", "/file%ZZ", "/file?value=%no"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "percent"):
                parse_request_target(target)

    def test_invalid_utf8_percent_encoded_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            parse_request_target("/%FF.html")


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
        self.document_root = Path(self.directory.name).resolve()
        os.chdir(self.directory.name)
        Path("index.html").write_text("hello café", encoding="utf-8")
        Path("page.htm").write_text("page", encoding="utf-8")
        Path("café.html").write_text("encoded path", encoding="utf-8")
        Path("nested").mkdir()
        Path("nested/index.html").write_text("nested", encoding="utf-8")
        Path("test.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff")
        os.utime("index.html", (1600000000, 1600000000))

    def request(self, path="/", headers="", method="GET"):
        return parse_request("{} {} HTTP/1.1\r\nHost: local\r\n{}\r\n".format(method, path, headers))

    def serve(self, request):
        return serve_file(request, self.document_root)

    def test_root_directory_and_extension_fallback_routes(self):
        for path, expected in (("/", "hello café"), ("/index", "hello café"),
                               ("/page", "page"), ("/nested", "nested"),
                               ("/nested/", "nested")):
            with self.subTest(path=path):
                response = self.serve(self.request(path))
                self.assertEqual(response.status, 200)
                self.assertEqual(response.body, expected.encode("utf-8"))
                self.assertEqual(response.headers["Content-Type"], "text/html")

    def test_binary_file_bytes_are_preserved(self):
        response = self.serve(self.request("/test.png"))
        self.assertEqual(response.body, Path("test.png").read_bytes())
        self.assertEqual(response.headers["Content-Type"], "image/png")

    def test_existing_errors_and_allow_header(self):
        self.assertEqual(self.serve(self.request("/missing.html")).status, 404)
        self.assertEqual(self.serve(self.request("/missing.txt")).status, 415)
        response = self.serve(self.request(method="POST"))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.headers["Allow"], "GET")

    def test_query_does_not_change_static_file_lookup(self):
        response = self.serve(self.request("/café.html?download=1"))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"encoded path")

    def test_parent_directory_paths_are_forbidden_after_percent_decoding(self):
        outside_file = self.document_root.parent / "private.txt"
        outside_file.write_text("private", encoding="utf-8")
        self.addCleanup(outside_file.unlink)
        for path in ("/../private.txt", "/nested/../../private.txt", "/%2e%2e/private.txt"):
            with self.subTest(path=path):
                response = self.serve(self.request(path))
                self.assertEqual(response.status, 403)
                self.assertNotIn(b"private", response.body)

    def test_external_symlink_is_forbidden_but_internal_one_is_served(self):
        outside_file = self.document_root.parent / "private.html"
        outside_file.write_text("private", encoding="utf-8")
        self.addCleanup(outside_file.unlink)
        external_link = self.document_root / "external.html"
        external_link.symlink_to(outside_file)
        self.addCleanup(external_link.unlink)
        Path("real.html").write_text("public", encoding="utf-8")
        Path("internal.html").symlink_to("real.html")

        self.assertEqual(self.serve(self.request("/external.html")).status, 403)
        response = self.serve(self.request("/internal.html"))
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"public")

    def test_resolver_reports_an_escape_before_file_access(self):
        with self.assertRaises(PathOutsideDocumentRoot):
            resolve_filename("/../private.txt", self.document_root)

    def test_conditional_get_returns_not_modified(self):
        date = format_http_date(1600000000)
        response = self.serve(self.request(headers="If-Modified-Since: " + date))
        self.assertEqual(response.status, 304)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.headers["Last-Modified"], date)

    def test_old_or_invalid_cache_date_returns_content(self):
        for date in (format_http_date(1500000000), "invalid date"):
            with self.subTest(date=date):
                response = self.serve(self.request(headers="If-Modified-Since: " + date))
                self.assertEqual(response.status, 200)
                self.assertEqual(response.body, "hello café".encode("utf-8"))

    def test_file_access_error_builds_normal_404_response(self):
        with patch("src.static_files.open", side_effect=PermissionError("denied")):
            response = self.serve(self.request())
        self.assertEqual(response.status, 404)
        self.assertEqual(int(response.headers["Content-Length"]), len(response.body))

    def test_real_socket_round_trip_and_close(self):
        server, client = socket.socketpair()
        client.settimeout(2)
        worker_errors = []

        def worker():
            try:
                handle_connection(server, self.document_root)
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
        connection.recv.side_effect = [b"GET", b""]
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
        connection.recv.return_value = b"POST / HTTP/1.1\r\nHost: local\r\n\r\n"
        connection.send.side_effect = BrokenPipeError("disconnected")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            handle_connection(connection)
        self.assertEqual(connection.send.call_count, 1)
        connection.close.assert_called_once_with()


class DocumentRootTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.original_directory = os.getcwd()
        self.addCleanup(os.chdir, self.original_directory)
        self.base = Path(self.directory.name).resolve()
        self.public = self.base / "public"
        self.public.mkdir()
        (self.public / "index.html").write_text("custom root", encoding="utf-8")
        (self.public / "page.htm").write_text("custom page", encoding="utf-8")
        (self.public / "nested").mkdir()
        (self.public / "nested/index.html").write_text("custom nested", encoding="utf-8")
        self.launch_directory = self.base / "launch"
        self.launch_directory.mkdir()
        (self.launch_directory / "index.html").write_text("wrong root", encoding="utf-8")

    def test_default_root_ignores_working_directory(self):
        os.chdir(self.launch_directory)
        response = serve_file(parse_request("GET / HTTP/1.1\r\nHost: local\r\n\r\n"))
        self.assertEqual(response.status, 200)
        self.assertEqual(DEFAULT_DOCUMENT_ROOT, PROJECT_ROOT / "src")
        self.assertEqual(response.body,
                         (PROJECT_ROOT / "src/index.html").read_text(encoding="utf-8").encode("utf-8"))

    def test_custom_root_and_fallbacks_ignore_working_directory(self):
        os.chdir(self.launch_directory)
        for route, expected in (("/", b"custom root"), ("/page", b"custom page"),
                                ("/nested", b"custom nested"), ("/nested/", b"custom nested")):
            with self.subTest(route=route):
                response = serve_file(parse_request("GET {} HTTP/1.1\r\nHost: local\r\n\r\n".format(route)), self.public)
                self.assertEqual(response.status, 200)
                self.assertEqual(response.body, expected)

    def test_server_resolves_relative_root_before_dispatch(self):
        os.chdir(self.base)
        connection = Mock()
        with patch("src.webserver.socket.socket") as factory, \
                patch("src.webserver.handle_connection") as handle, \
                contextlib.redirect_stdout(io.StringIO()):
            listener = factory.return_value.__enter__.return_value
            listener.accept.side_effect = [(connection, ("127.0.0.1", 1234)), KeyboardInterrupt]
            with self.assertRaises(KeyboardInterrupt):
                run_server(8080, "public")
        handle.assert_called_once_with(connection, self.public)

    def test_missing_root_or_file_root_is_rejected_before_socket_creation(self):
        for root in (self.base / "missing", self.public / "index.html"):
            with self.subTest(root=root), patch("src.webserver.socket.socket") as factory:
                with self.assertRaisesRegex(ValueError, "existing directory"):
                    run_server(8080, root)
                factory.assert_not_called()


class CLITests(unittest.TestCase):
    def test_script_and_module_entry_points(self):
        for arguments in (("src/webserver.py", "-h"), ("-m", "src.webserver", "-h")):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable] + list(arguments), cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertIn(b"webserver.py [-p <port number>] [-d <document root>]", result.stdout)

    def test_short_and_long_document_root_options(self):
        for option in ("-d", "--document-root"):
            with self.subTest(option=option), patch("src.webserver.run_server") as run:
                main(["-p", "8080", option, "public"])
                run.assert_called_once_with(8080, Path("public"))

    def test_invalid_root_exits_with_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "src/webserver.py"),
                 "--document-root", str(Path(directory) / "missing")],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"Document root must be an existing directory", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)

    def test_tcp_launch_from_another_directory_with_default_and_custom_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            public = base / "public"
            public.mkdir()
            (public / "index.html").write_text("custom TCP response", encoding="utf-8")
            launch = base / "launch"
            launch.mkdir()
            default_body = (PROJECT_ROOT / "src/index.html").read_text(encoding="utf-8").encode("utf-8")
            for arguments, expected in (([], default_body),
                                        (["--document-root", "../public"], b"custom TCP response")):
                with self.subTest(arguments=arguments):
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", 0))
                        port = probe.getsockname()[1]
                    process = subprocess.Popen(
                        [sys.executable, str(PROJECT_ROOT / "src/webserver.py"),
                         "-p", str(port)] + arguments,
                        cwd=str(launch), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    )
                    try:
                        client = None
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline and process.poll() is None:
                            try:
                                client = socket.create_connection(("127.0.0.1", port), timeout=1)
                                break
                            except OSError:
                                time.sleep(0.02)
                        self.assertIsNotNone(client, "Server did not start")
                        with client:
                            client.settimeout(2)
                            client.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                            wire = b""
                            while True:
                                chunk = client.recv(4096)
                                if not chunk:
                                    break
                                wire += chunk
                        headers, body = wire.split(b"\r\n\r\n", 1)
                        self.assertTrue(headers.startswith(b"HTTP/1.1 200 OK\r\n"))
                        self.assertEqual(body, expected)
                    finally:
                        process.terminate()
                        process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
