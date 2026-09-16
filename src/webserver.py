"""CLI entry point and socket transport for the sequential HTTP server."""

import argparse
from pathlib import Path
import signal
import socket
import sys
import threading
import time

if __package__:
    from .http_request import HTTPError, parse_request
    from .http_response import error_response
    from .limits import Limits, Timeouts
    from .static_files import DEFAULT_DOCUMENT_ROOT, serve_file
    from .transport import SocketReader, send_response
    from .workers import BoundedPool
    from .application import Application
else:
    from http_request import HTTPError, parse_request
    from http_response import error_response
    from limits import Limits, Timeouts
    from static_files import DEFAULT_DOCUMENT_ROOT, serve_file
    from transport import SocketReader, send_response
    from workers import BoundedPool
    from application import Application


USAGE = "webserver.py [-p <port number>] [-d <document root>]"


def handle_connection(connection, document_root=DEFAULT_DOCUMENT_ROOT, limits=Limits(), timeouts=Timeouts(),
                      max_requests=100, stop_event=None, application=None):
    """Own one accepted socket: receive, dispatch, send, and close."""
    response_started = False
    waiting_for_idle = False
    reader = SocketReader(connection)
    application = application or Application(document_root)
    try:
        for number in range(max_requests):
            response_started = False
            if number and not reader.buffer:
                waiting_for_idle = True
                connection.settimeout(timeouts.idle)
                data = connection.recv(4096)
                if not data:
                    return
                reader.buffer.extend(data)
                waiting_for_idle = False
            header = reader.read_until(b"\r\n\r\n", limits.header_bytes, timeout=timeouts.header)
            if not header:
                return
            request = parse_request(header.decode("iso-8859-1"), limits.body_bytes)
            if "transfer-encoding" in request.headers:
                body = reader.read_chunked(limits.body_bytes, timeouts.body)
            else:
                body = reader.read_exact(int(request.headers.get("content-length", "0")),
                                         limits.body_bytes, timeouts.body)
            request = request._replace(body=body)
            connection_tokens = {value.strip().lower() for value in request.headers.get("connection", "").split(",")}
            keep_alive = (request.version == "HTTP/1.1" and
                          "close" not in connection_tokens and
                          number < max_requests - 1 and not (stop_event and stop_event.is_set()))
            try:
                peer = connection.getpeername()
            except (OSError, AttributeError):
                peer = None
            response = application.dispatch(request, peer)
            response.headers["Connection"] = "keep-alive" if keep_alive else "close"
            response_started = True
            connection.settimeout(timeouts.write)
            send_response(connection, response, suppress_body=request.method == "HEAD")
            if not keep_alive:
                return
    except HTTPError as error:
        response = error_response(error.status)
        try:
            connection.settimeout(timeouts.write)
            send_response(connection, response)
        except OSError:
            pass
    except socket.timeout:
        if not response_started and not waiting_for_idle:
            try:
                connection.settimeout(timeouts.write)
                send_response(connection, error_response(408))
            except OSError:
                pass
    except (OSError, ValueError) as error:
        # A failed connection cannot reliably receive a file error response.
        print("Connection error: {}".format(error), file=sys.stderr)
    except Exception as error:
        print("Handler error: {}".format(error), file=sys.stderr)
        if not response_started:
            try:
                send_response(connection, error_response(500))
            except OSError:
                pass
    finally:
        try:
            connection.close()
        except OSError:
            pass


def run_server(port, document_root=DEFAULT_DOCUMENT_ROOT, workers=8, queue_size=16, *,
               host="127.0.0.1", limits=Limits(), timeouts=Timeouts(), max_requests=100,
               shutdown_timeout=2.0, stop_event=None, upstream=None):
    """Accept clients into a bounded pool; reject excess work instead of queuing forever."""
    # Resolve a relative CLI path once, before accepting any connections.
    document_root = Path(document_root).resolve()
    if not document_root.is_dir():
        raise ValueError("Document root must be an existing directory: {}".format(document_root))
    if min(limits) < 1 or min(timeouts) <= 0 or max_requests < 1 or shutdown_timeout < 0:
        raise ValueError("Limits, deadlines, and request counts must be positive")
    stop_event = stop_event or threading.Event()
    application = Application(document_root, upstream)
    connections = set()
    lock = threading.Lock()

    def worker(connection):
        try:
            handle_connection(connection, document_root, limits, timeouts,
                              max_requests, stop_event, application)
        finally:
            with lock:
                connections.discard(connection)

    with BoundedPool(workers, queue_size) as pool, socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(max(1, workers + queue_size))
        listener.settimeout(0.2)
        print("Server is running on port", listener.getsockname()[1], flush=True)
        print("Document root:", document_root)
        try:
            while not stop_event.is_set():
                try:
                    connection, address = listener.accept()
                except socket.timeout:
                    continue
                with lock:
                    connections.add(connection)
                if not pool.submit(worker, connection):
                    with lock:
                        connections.discard(connection)
                    try:
                        connection.settimeout(0.1)
                        send_response(connection, error_response(503))
                    except OSError:
                        pass
                    finally:
                        connection.close()
        finally:
            stop_event.set()
            deadline = time.monotonic() + shutdown_timeout
            while time.monotonic() < deadline:
                with lock:
                    if not connections:
                        break
                time.sleep(0.02)
            with lock:
                remaining = list(connections)
            for connection in remaining:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()


def main(argv):
    parser = argparse.ArgumentParser(description="Raw-socket HTTP/1.1 server")
    parser.add_argument("-p", "--port", type=int, default=6789)
    parser.add_argument("-d", "--document-root", type=Path, default=DEFAULT_DOCUMENT_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--upstream", help="HTTP backend origin for /api/*")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--queue-size", type=int, default=16)
    parser.add_argument("--max-headers", type=int, default=32768)
    parser.add_argument("--max-body", type=int, default=1048576)
    parser.add_argument("--max-requests", type=int, default=100)
    parser.add_argument("--shutdown-timeout", type=float, default=2.0)
    for name, default in zip(("header", "body", "write", "idle"), Timeouts()):
        parser.add_argument(f"--{name}-timeout", type=float, default=default)
    args = parser.parse_args(argv)
    stop = threading.Event()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, lambda unused, frame: stop.set())
    try:
        run_server(args.port, args.document_root, args.workers, args.queue_size, host=args.host,
                   limits=Limits(args.max_headers, args.max_body),
                   timeouts=Timeouts(args.header_timeout, args.body_timeout, args.write_timeout, args.idle_timeout),
                   max_requests=args.max_requests, shutdown_timeout=args.shutdown_timeout, stop_event=stop,
                   upstream=args.upstream)
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    main(sys.argv[1:])
