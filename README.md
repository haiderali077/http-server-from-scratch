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
- **Error Handling**: Returns proper HTTP status codes (200, 304, 404, 405, 415)
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

## Project Structure

```
src/
├── webserver.py          # Core HTTP server implementation
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

- Python 3.6+
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

### Access the Server

Once running, navigate to:
- `http://localhost:6789` - Main page
- `http://localhost:6789/test.html` - Test page
- `http://localhost:6789/nested/` - Nested directory

### Command-Line Options

```bash
python src/webserver.py -h              # Display help
python src/webserver.py -p <port>       # Specify custom port
```

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
- **404 Not Found**: Missing resource handling
- **405 Method Not Allowed**: Invalid HTTP method rejection
- **415 Unsupported Media Type**: File type filtering

### Security Features
- Path traversal attack prevention (`..` removal)
- Whitelist-based file type validation
- Method validation (GET-only by design)

## Testing

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
