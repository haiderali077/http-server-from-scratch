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
    from .transport import BodyStream, SocketReader, send_response
    from .workers import BoundedPool
    from .application import Application
    from .events import Events
    from .reactor import run_reactor
else:
    from http_request import HTTPError, parse_request
    from http_response import error_response
    from limits import Limits, Timeouts
    from static_files import DEFAULT_DOCUMENT_ROOT, serve_file
    from transport import BodyStream, SocketReader, send_response
    from workers import BoundedPool
    from application import Application
    from events import Events
    from reactor import run_reactor


USAGE = "webserver.py [-p <port number>] [-d <document root>]"


def handle_connection(connection, document_root=DEFAULT_DOCUMENT_ROOT, limits=Limits(), timeouts=Timeouts(),
                      max_requests=100, stop_event=None, application=None, events=None, *,
                      reader=None, request_number=0, park=False):
    """Own one accepted socket: receive, dispatch, send, and close."""
    response_started = False
    waiting_for_idle = False
    reader = reader or SocketReader(connection)
    parked = False
    application = application or Application(document_root)
    events = events or Events()
    request = response = None
    started = time.monotonic()

    def record(status, outcome, upstream=None):
        if upstream is None and response is not None:
            upstream = response.upstream_seconds
            streamed = getattr(response.body, "duration", None)
            if upstream is not None and streamed is not None:
                upstream += streamed
        events.emit("access", method=request.method if request else None, path=request.path if request else None,
                    status=status, duration_seconds=round(time.monotonic() - started, 6),
                    upstream_seconds=upstream, outcome=outcome)
    try:
        for number in range(request_number, max_requests):
            request = response = None
            started = time.monotonic()
            response_started = False
            if number and not reader.buffer:
                waiting_for_idle = True
                connection.settimeout(timeouts.idle)
                data = connection.recv(4096)
                if not data:
                    return
                reader.buffer.extend(data)
                waiting_for_idle = False
                started = time.monotonic()
            header = reader.read_until(b"\r\n\r\n", limits.header_bytes, timeout=timeouts.header)
            if not header:
                return
            request = parse_request(header.decode("iso-8859-1"), limits.body_bytes)
            if application.is_proxy(request):
                chunks = (reader.iter_chunked(limits.body_bytes, timeouts.body) if "transfer-encoding" in request.headers
                          else reader.iter_exact(int(request.headers.get("content-length", "0")), limits.body_bytes, timeouts.body))
                body = BodyStream(chunks)
            elif "transfer-encoding" in request.headers:
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
            if isinstance(body, BodyStream) and not body.complete:
                keep_alive = False
            response.headers["Connection"] = "keep-alive" if keep_alive else "close"
            response_started = True
            connection.settimeout(timeouts.write)
            send_response(connection, response, suppress_body=request.method == "HEAD")
            record(response.status, "complete")
            if not keep_alive:
                return
            if park:
                parked = True
                return reader, number + 1
    except HTTPError as error:
        events.emit("error", message=str(error), status=error.status, response_started=response_started)
        record(response.status if response_started and response else error.status, "incomplete" if response_started else "error",
               getattr(error, "upstream_seconds", None))
        if response_started:
            return
        response = error_response(error.status)
        try:
            connection.settimeout(timeouts.write)
            send_response(connection, response)
        except OSError:
            pass
    except socket.timeout:
        if not waiting_for_idle:
            events.emit("error", message="Socket deadline exceeded", response_started=response_started)
            record(response.status if response_started and response else 408, "incomplete" if response_started else "error")
        if not response_started and not waiting_for_idle:
            try:
                connection.settimeout(timeouts.write)
                send_response(connection, error_response(408))
            except OSError:
                pass
    except (OSError, ValueError) as error:
        events.emit("error", message=str(error), response_started=response_started)
        record(response.status if response_started and response else None, "incomplete")
        # A failed connection cannot reliably receive a file error response.
        print("Connection error: {}".format(error), file=sys.stderr)
    except Exception as error:
        events.emit("error", message=str(error), response_started=response_started)
        record(response.status if response_started and response else 500, "incomplete" if response_started else "error")
        print("Handler error: {}".format(error), file=sys.stderr)
        if not response_started:
            try:
                send_response(connection, error_response(500))
            except OSError:
                pass
    finally:
        if not parked:
            try:
                connection.close()
            except OSError:
                pass


def run_server(port, document_root=DEFAULT_DOCUMENT_ROOT, workers=8, queue_size=16, *,
               host="127.0.0.1", limits=Limits(), timeouts=Timeouts(), max_requests=100,
               shutdown_timeout=2.0, stop_event=None, upstream=None, proxy_options=None, access_log=None, error_log=None,
               cache_bytes=8388608, mode="threads", max_connections=256):
    """Accept clients into a bounded pool; reject excess work instead of queuing forever."""
    # Resolve a relative CLI path once, before accepting any connections.
    document_root = Path(document_root).resolve()
    if not document_root.is_dir():
        raise ValueError("Document root must be an existing directory: {}".format(document_root))
    if min(limits) < 1 or min(timeouts) <= 0 or max_requests < 1 or shutdown_timeout < 0:
        raise ValueError("Limits, deadlines, and request counts must be positive")
    if mode not in ("threads", "selectors") or max_connections < 1:
        raise ValueError("Invalid connection mode or capacity")
    stop_event = stop_event or threading.Event()
    application = Application(document_root, upstream, proxy_options, cache_bytes)
    connections = set()
    lock = threading.Lock()

    def worker(connection):
        try:
            handle_connection(connection, document_root, limits, timeouts,
                              max_requests, stop_event, application, events)
        finally:
            with lock:
                connections.discard(connection)

    with application, Events(access_log, error_log) as events, BoundedPool(workers, queue_size) as pool, socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(max(1, workers + queue_size))
        listener.settimeout(0.2)
        print("Server is running on port", listener.getsockname()[1], flush=True)
        print("Document root:", document_root)
        if mode == "selectors":
            def exchange(connection, reader, number):
                return handle_connection(connection, document_root, limits, timeouts, max_requests,
                                         stop_event, application, events, reader=reader,
                                         request_number=number, park=True)
            run_reactor(listener, pool, exchange, stop_event, timeouts, shutdown_timeout, max_connections)
            return
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
    parser.add_argument("--upstream-connect-timeout", type=float, default=2.0)
    parser.add_argument("--upstream-response-timeout", type=float, default=10.0)
    parser.add_argument("--upstream-pool-size", type=int, default=0)
    parser.add_argument("--access-log", type=Path)
    parser.add_argument("--error-log", type=Path)
    parser.add_argument("--cache-bytes", type=int, default=8388608)
    parser.add_argument("--mode", choices=("threads", "selectors"), default="threads")
    parser.add_argument("--max-connections", type=int, default=256)
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
                   upstream=args.upstream, proxy_options={"connect_timeout": args.upstream_connect_timeout,
                                                        "response_timeout": args.upstream_response_timeout,
                                                        "pool_size": args.upstream_pool_size},
                   access_log=args.access_log, error_log=args.error_log, cache_bytes=args.cache_bytes,
                   mode=args.mode, max_connections=args.max_connections)
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    main(sys.argv[1:])
