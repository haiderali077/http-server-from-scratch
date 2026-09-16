"""Deterministic raw upstream replies for proxy failure tests."""
import socketserver
import threading
import time


class RawUpstream:
    def __init__(self, reply, delay=0):
        self.reply, self.delay = reply, delay
    def __enter__(self):
        owner = self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(2)
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        return
                    data += chunk
                time.sleep(owner.delay)
                try:
                    self.request.sendall(owner.reply)
                except OSError:
                    pass
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self
    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
