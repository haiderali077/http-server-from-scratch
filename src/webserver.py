"""CLI entry point and socket transport for the sequential HTTP server."""

import getopt
from pathlib import Path
import socket
import sys

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


def handle_connection(connection, document_root=DEFAULT_DOCUMENT_ROOT, limits=Limits(), timeouts=Timeouts()):
    """Own one accepted socket: receive, dispatch, send, and close."""
    response_started = False
    waiting_for_idle = False
    reader = SocketReader(connection)
    application = Application(document_root)
    try:
        for number in range(100):
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
                          number < 99)
            response = application.dispatch(request)
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


def run_server(port, document_root=DEFAULT_DOCUMENT_ROOT, workers=8, queue_size=16):
    """Accept clients into a bounded pool; reject excess work instead of queuing forever."""
    # Resolve a relative CLI path once, before accepting any connections.
    document_root = Path(document_root).resolve()
    if not document_root.is_dir():
        raise ValueError("Document root must be an existing directory: {}".format(document_root))

    with BoundedPool(workers, queue_size) as pool, socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("", port))
        listener.listen(max(1, workers + queue_size))
        print("Server is running on port", port)
        print("Document root:", document_root)
        while True:
            print("The server is ready to receive data....")
            connection, address = listener.accept()
            if not pool.submit(handle_connection, connection, document_root):
                try:
                    connection.settimeout(0.1)
                    send_response(connection, error_response(503))
                except OSError:
                    pass
                finally:
                    connection.close()


def main(argv):
    port = 6789
    document_root = DEFAULT_DOCUMENT_ROOT
    try:
        opts, args = getopt.getopt(argv, "hp:d:", ["port=", "document-root="])
        for opt, arg in opts:
            if opt == "-h":
                print(USAGE)
                print("Default document root:", DEFAULT_DOCUMENT_ROOT)
                return
            if opt in ("-p", "--port"):
                port = int(arg)
            elif opt in ("-d", "--document-root"):
                document_root = Path(arg)
    except (getopt.GetoptError, ValueError) as error:
        print(error, file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    try:
        run_server(port, document_root)
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
