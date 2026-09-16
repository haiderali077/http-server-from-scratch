"""CLI entry point and socket transport for the sequential HTTP server."""

import getopt
from pathlib import Path
import socket
import sys

if __package__:
    from .http_request import HTTPError, parse_request
    from .http_response import error_response
    from .limits import Limits
    from .static_files import DEFAULT_DOCUMENT_ROOT, serve_file
    from .transport import SocketReader, send_response
else:
    from http_request import HTTPError, parse_request
    from http_response import error_response
    from limits import Limits
    from static_files import DEFAULT_DOCUMENT_ROOT, serve_file
    from transport import SocketReader, send_response


USAGE = "webserver.py [-p <port number>] [-d <document root>]"


def handle_connection(connection, document_root=DEFAULT_DOCUMENT_ROOT, limits=Limits()):
    """Own one accepted socket: receive, dispatch, send, and close."""
    try:
        message = SocketReader(connection).read_until(b"\r\n\r\n", limits.header_bytes).decode("iso-8859-1")
        request = parse_request(message, limits.body_bytes)

        response = serve_file(request, document_root)
        send_response(connection, response)
    except HTTPError as error:
        response = error_response(error.status)
        try:
            send_response(connection, response)
        except OSError:
            pass
    except (OSError, ValueError) as error:
        # A failed connection cannot reliably receive a file error response.
        print("Connection error: {}".format(error), file=sys.stderr)
    finally:
        connection.close()


def run_server(port, document_root=DEFAULT_DOCUMENT_ROOT):
    """Accept connections sequentially and delegate their request lifecycle."""
    # Resolve a relative CLI path once, before accepting any connections.
    document_root = Path(document_root).resolve()
    if not document_root.is_dir():
        raise ValueError("Document root must be an existing directory: {}".format(document_root))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("", port))
        listener.listen(1)
        print("Server is running on port", port)
        print("Document root:", document_root)
        while True:
            print("The server is ready to receive data....")
            connection, address = listener.accept()
            handle_connection(connection, document_root)


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
