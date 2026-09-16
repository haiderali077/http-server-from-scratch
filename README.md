# Custom HTTP Web Server

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Socket.IO](https://img.shields.io/badge/Socket_Programming-010101?style=for-the-badge&logo=socket.io&logoColor=white)
![HTTP](https://img.shields.io/badge/HTTP/1.1-005C9C?style=for-the-badge&logo=http&logoColor=white)
![TCP/IP](https://img.shields.io/badge/TCP/IP-0078D4?style=for-the-badge&logo=cisco&logoColor=white)

A lightweight HTTP/1.1 web server implementation built from scratch in Python using socket programming. This project demonstrates low-level network programming and HTTP protocol implementation without relying on high-level frameworks.

## Technical Implementation

### Core Features

- **Raw Socket Programming**: Direct TCP socket implementation using Python's `socket` module
- **HTTP/1.1 Protocol Compliance**: Proper request parsing and response formatting
- **Multi-Format Support**: Serves HTML, CSS, JavaScript, JSON, and common image formats (PNG, JPG, GIF)
- **Conditional GET Requests**: Implements `If-Modified-Since` header for efficient caching (304 Not Modified responses)
- **RESTful HTTP Methods**: Validates request methods with appropriate 405 responses
- **Error Handling**: Returns proper HTTP status codes (200, 304, 403, 404, 405, 415)
- **Security**: Path traversal protection and unsupported media type filtering
- **Smart Routing**: Automatic `index.html` resolution for directory requests

### Request Processing Pipeline

1. TCP connection establishment via socket binding
2. HTTP request parsing (method, path, headers)
3. Path normalization and security validation
4. Content-Type negotiation based on file extensions
5. Conditional request handling with Last-Modified timestamps
6. Response header construction with proper MIME types
7. Binary/text file handling with appropriate encoding

### Code Architecture

The server separates four responsibilities so HTTP logic can be tested without
opening a listening socket:

```text
run_server() accepts a TCP connection
    -> handle_connection() receives request bytes and decodes them
    -> parse_request() returns an HTTPRequest
    -> serve_file() returns an HTTPResponse
    -> HTTPResponse.header_bytes() serializes the status line and headers
    -> handle_connection() sends the headers/body and closes the connection
```

- `http_request.py` parses the method, path, version, and headers. Header names
  are stored in lowercase for case-insensitive lookup. It separates query text
  from the path and percent-decodes the path once before file lookup. Query text
  remains raw for future route-specific handling. The parser performs no socket
  or file operations.
- `http_response.py` defines response data and builds common headers and HTML
  errors. Bodies are bytes, so Content-Length measures the transmitted payload.
  The serializer adds the HTTP status line, CRLF-separated headers, and the
  blank line before the body.
- `static_files.py` resolves filenames, checks supported extensions, evaluates
  conditional GET requests, reads files, and returns response data. File access
  failures become consistently formatted 404 responses.
- `webserver.py` owns the CLI and socket lifecycle. A connection is closed in a
  `finally` block. Transport failures are handled here rather than interpreted
  as missing files.

The server currently provides a GET-only, sequential service with a configurable
document root that defaults to `src/`, independently of the launch directory.
Incremental reads, strict validation, complete-write handling, and persistent
connections remain future work.

## Project Structure

```
src/
├── __init__.py           # Allows package imports and module execution
├── webserver.py          # CLI, listener, and connection handling
├── http_request.py       # Request data and parsing
├── http_response.py      # Response data, builders, and serialization
├── static_files.py       # File resolution and static responses
├── index.html            # Main landing page
├── test.html             # Demo page
├── test.js               # Client-side JavaScript
├── test.css              # Styling
├── test.json             # Sample JSON data
└── nested/
    ├── index.html        # Nested route example
    └── css.html          # Additional test page
```

## Setup & Usage

### Requirements

- Python 3.11+ on Linux or macOS
- No external dependencies (uses only standard library)

### Running the Server

**Default port (6789):**
```bash
python src/webserver.py
```

**Custom port:**
```bash
python src/webserver.py -p 8080
```

**Serve a different directory:**
```bash
python src/webserver.py -p 8080 --document-root ./public
```

The directory must already exist. Relative custom paths are resolved against the
launch directory once at startup; absolute paths can also be supplied.

### Access the Server

Once running, navigate to:
- `http://localhost:6789` - Main page
- `http://localhost:6789/test.html` - Test page
- `http://localhost:6789/nested/` - Nested directory

### Command-Line Options

```bash
python src/webserver.py -h                       # Display help
python src/webserver.py -p <port>                 # Specify custom port
python src/webserver.py -d <directory>            # Specify document root
python src/webserver.py --document-root <directory>
```

The default root comes from the location of `static_files.py`, so it remains
`src/` whether launched from the repository root, from `src/`, or from another
directory using an absolute script path. From the repository root,
`python -m src.webserver -p 8080` uses the same default root.

## Technical Highlights

### HTTP Headers Implemented
- `Date`: RFC-compliant HTTP date formatting
- `Server`: Custom server identification
- `Last-Modified`: File modification timestamps
- `Content-Type`: Dynamic MIME type detection
- `Content-Length`: Accurate payload sizing
- `Connection`: Connection management
- `Allow`: Supported methods indication

### Status Codes Handled
- **200 OK**: Successful resource retrieval
- **304 Not Modified**: Cached resource validation
- **403 Forbidden**: Resource path escapes the configured document root
- **404 Not Found**: Missing resource handling
- **405 Method Not Allowed**: Invalid HTTP method rejection
- **415 Unsupported Media Type**: File type filtering

### Security Features
- Document-root containment after path resolution, including symlink escapes
- Whitelist-based file type validation
- Method validation (GET-only by design)

## Testing

Run the automated regression tests from the repository root:

The same suite runs on Python 3.11 and 3.13 through
[GitHub Actions](.github/workflows/tests.yml) for pushes and pull requests.

```bash
python3 -m unittest discover -s tests -v
```

These cover parsing, response framing, static routes, binary content, conditional
GET, error responses, socket cleanup, a real socket round trip, document-root
selection and validation, and both CLI entry points. TCP launch tests verify
default and custom roots from an unrelated working directory. They also reject
path and symlink escapes from the document root. The tests use only the Python
standard library.

Test the server's functionality:

```bash
# Basic GET request
curl -v http://localhost:6789/

# Conditional GET (check caching)
curl -v -H "If-Modified-Since: Sat, 01 Jan 2030 00:00:00 GMT" http://localhost:6789/

# Unsupported method
curl -v -X POST http://localhost:6789/

# 404 handling
curl -v http://localhost:6789/nonexistent.html
```

## Skills Demonstrated

- **Network Programming**: TCP socket creation, binding, and connection handling
- **Protocol Implementation**: HTTP/1.1 request/response cycle
- **Systems Programming**: File I/O, binary/text handling, OS-level operations
- **Error Handling**: Comprehensive exception management and status codes
- **Security Awareness**: Input validation and attack vector mitigation
- **Code Organization**: Clean separation of concerns and helper functions

## Limitations

- Single-threaded (handles one connection at a time)
- No HTTPS/TLS support
- No POST/PUT/DELETE implementation
- Limited to local file serving (no dynamic content generation)

## Future Enhancements

- Multi-threading for concurrent connections
- SSL/TLS encryption support
- POST request handling and form processing
- WebSocket support
- Request logging and analytics
- Configuration file support

---

Built with Python's standard library to demonstrate fundamental networking concepts.
