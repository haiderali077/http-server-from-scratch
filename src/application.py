"""Application decisions are independent of the socket lifecycle."""
if __package__:
    from .http_response import build_response, error_response
    from .static_files import serve_file
else:
    from http_response import build_response, error_response
    from static_files import serve_file


class Application:
    def __init__(self, document_root):
        self.document_root = document_root

    def dispatch(self, request):
        if request.path == "/echo":
            if request.method != "POST":
                return error_response(405, {"Allow": "POST"})
            return build_response(200, request.body, {"Content-Type": "application/octet-stream"})
        return serve_file(request, self.document_root)
