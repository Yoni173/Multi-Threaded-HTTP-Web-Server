# Multi-Threaded HTTP/1.0 Web Server

A multi-threaded static HTTP/1.0 web server built from scratch in Python using only low-level TCP sockets.

Built as a Computer Networks programming assignment. It uses only Python's standard `socket` library — **no** Flask, FastAPI, Django, `http.server`, `socketserver`, or any other high-level web framework.

## Features

- Raw TCP sockets: `socket(AF_INET, SOCK_STREAM)`, `bind()`, `listen()`, `accept()`
- One `threading.Thread` per client connection
- Manual reading of the TCP stream in a loop until `\r\n\r\n` (max header size: 8192 bytes)
- Manual parsing of the HTTP request line
- `GET` only; HTTP/1.0 responses with `Content-Length`, `Content-Type` (via `mimetypes`) and `Connection: close`
- Static file serving from `www/`, with `/` mapped to `/index.html`
- Allowed subdirectories: `pages`, `css`, `images`, `docs`, `assets` (anything else → `403`)
- Directory traversal protection:
  - blocks `..` and URL-encoded `..` (`%2e%2e`)
  - blocks double-encoded traversal (`%252e%252e`)
  - rejects backslashes
  - final resolved-path check that the file stays inside `www/`
- Status codes: `200`, `400`, `403`, `404`, `405`, `500`

## Project structure

```
.
├── server.py               # The web server
├── partial_read_test.py    # Sends a request in small delayed chunks
└── www/                    # Static site root
    ├── index.html
    ├── pages/about.html
    ├── css/style.css
    ├── images/logo.svg
    ├── docs/info.txt
    └── assets/data.json
```

## How to run

Requires Python 3 (standard library only).

```bash
python server.py
```

Then open <http://127.0.0.1:8080/> in a browser. Stop the server with `Ctrl+C`.

## Testing with curl

With the server running, in another terminal:

```bash
curl -v http://localhost:8080/index.html
curl -v http://localhost:8080/pages/about.html
curl -v http://localhost:8080/no-such-file.html
curl -v http://localhost:8080/private/file.txt
curl --path-as-is -v http://localhost:8080/../../etc/passwd
curl --path-as-is -v "http://localhost:8080/%2e%2e/%2e%2e/etc/passwd"
curl -v -X POST http://localhost:8080/index.html
```

> On Windows PowerShell, use `curl.exe` instead of `curl`.

| Request                         | Expected result          |
|---------------------------------|--------------------------|
| `/index.html`                   | `200 OK`                 |
| `/pages/about.html`             | `200 OK`                 |
| `/no-such-file.html`            | `404 Not Found`          |
| `/private/file.txt`             | `403 Forbidden`          |
| `/../../etc/passwd`             | `403 Forbidden`          |
| `/%2e%2e/%2e%2e/etc/passwd`     | `403 Forbidden`          |
| `POST /index.html`              | `405 Method Not Allowed` |

## Partial `recv()` test

`partial_read_test.py` sends a single HTTP request in several small pieces with short delays between them, demonstrating that the server keeps reading until it receives the full header terminator.

```bash
python server.py            # terminal 1
python partial_read_test.py # terminal 2
```

You should see a `200 OK` response printed.

## How it works

**Socket lifecycle.** The server creates a TCP socket, binds it to `127.0.0.1:8080`, listens for incoming connections, accepts each client, sends one HTTP response, and closes that client connection.

**Why TCP requires reading in a loop.** TCP is a byte stream with no message boundaries. A request may arrive in one `recv()` call or in many smaller pieces, so the server reads repeatedly until it has the complete headers.

**What `\r\n\r\n` means.** HTTP header lines end with CRLF (`\r\n`). A blank line marks the end of the headers, so `\r\n\r\n` means "end of HTTP headers".

**Request line parsing.** The first line is split into method, path and version — e.g. `GET /index.html HTTP/1.0` → `method=GET`, `path=/index.html`, `version=HTTP/1.0`.

**Content-Length and Content-Type.** `Content-Length` tells the client exactly how many bytes are in the body; `Content-Type` tells the browser what kind of file it is receiving (`text/html`, `text/css`, `image/svg+xml`, `application/json`, …).

**Directory traversal prevention.** The server URL-decodes the path (repeatedly, to catch double encoding), rejects `..` and backslashes, blocks unknown subdirectories, resolves the final filesystem path, and verifies it is still inside `www/`.

**Concurrency.** The main thread keeps accepting new connections while each client is handled in its own thread, so one slow client doesn't block others.
