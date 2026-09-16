"""Small standard-library demo backend; the proxy itself uses raw sockets."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoBackend(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        self.reply(200, b"ok\n" if self.path == "/health" else b"x" * 1024)

    do_HEAD = do_GET

    def do_POST(self):
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            body = bytearray()
            while True:
                size = int(self.rfile.readline(128).split(b";", 1)[0], 16)
                if not size:
                    self.rfile.readline()
                    break
                if len(body) + size > 1048576:
                    self.close_connection = True
                    self.reply(413, b"too large\n")
                    return
                body.extend(self.rfile.read(size))
                self.rfile.read(2)
            body = bytes(body)
        else:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 1048576:
                self.close_connection = True
                self.reply(413, b"too large\n")
                return
            body = self.rfile.read(size)
        self.reply(200, body)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), DemoBackend) as server:
        print(f"Demo backend on port {server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
