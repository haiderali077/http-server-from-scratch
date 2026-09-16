"""Application decisions are independent of the socket lifecycle."""
if __package__:
    from .http_response import build_response, chunked_response, error_response
    from .static_files import serve_file
    from .proxy import Proxy
else:
    from http_response import build_response, chunked_response, error_response
    from static_files import serve_file
    from proxy import Proxy


class Application:
    def __init__(self, document_root, upstream=None):
        self.document_root = document_root
        self.proxy = Proxy(upstream) if upstream else None
        self.routes = {
            "/echo": ({"POST"}, self.echo),
            "/health": ({"GET", "HEAD"}, self.health),
            "/stream": ({"GET", "HEAD"}, self.stream),
        }

    def dispatch(self, request, peer=None):
        if request.path == "/static" or request.path.startswith("/static/"):
            return serve_file(request._replace(path=request.path[7:] or "/"), self.document_root)
        if request.path == "/api" or request.path.startswith("/api/"):
            if not self.proxy:
                return error_response(503)
            return self.proxy.forward(request._replace(path=request.path[4:] or "/"), peer)
        route = self.routes.get(request.path)
        if route:
            allowed, handler = route
            if request.method not in allowed:
                return error_response(405, {"Allow": ", ".join(sorted(allowed))})
            return handler(request)
        return serve_file(request, self.document_root)

    def echo(self, request):
        return build_response(200, request.body, {"Content-Type": "application/octet-stream"})

    def health(self, request):
        return build_response(200, b"ok\n", {"Content-Type": "text/plain"})

    def stream(self, request):
        return chunked_response(iter([b"first\n", b"second\n"]), {"Content-Type": "text/plain"})
