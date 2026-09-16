"""CLI entry point and socket transport for the sequential HTTP server."""

import getopt
import socket
import sys

if __package__:
    from .http_request import parse_request
    from .static_files import serve_file
else:
    from http_request import parse_request
    from static_files import serve_file


def handle_connection(connection):
    """Own one accepted socket: receive, dispatch, send, and close."""
    try:
        # Incremental reads and full-write handling remain separate TODO items.
        message = connection.recv(1024).decode("utf-8")
        print(message)
        try:
            request = parse_request(message)
        except ValueError:
            return

        response = serve_file(request)
        connection.send(response.header_bytes())
        if response.body:
            connection.send(response.body)
    except OSError as error:
        # A failed connection cannot reliably receive a file error response.
        print("Connection error: {}".format(error), file=sys.stderr)
    finally:
        connection.close()


def run_server(port):
    """Accept connections sequentially and delegate their request lifecycle."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("", port))
        listener.listen(1)
        print("Server is running on port", port)
        while True:
            print("The server is ready to receive data....")
            connection, address = listener.accept()
            handle_connection(connection)


def main(argv):
    port = 6789
    try:
        opts, args = getopt.getopt(argv, "hp:", ["port="])
    except getopt.GetoptError:
        print("webserver.py -p <port number>")
        sys.exit(2)

    for opt, arg in opts:
        if opt == "-h":
            print("webserver.py -p <port number>")
            return
        if opt in ("-p", "--port"):
            port = int(arg)

    run_server(port)


if __name__ == "__main__":
    main(sys.argv[1:])
