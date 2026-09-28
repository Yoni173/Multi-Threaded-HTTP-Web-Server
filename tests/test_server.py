import socket
import threading
import time

import pytest

import server
from conftest import get, send_raw

WWW = server.WWW_DIR


# ---------------------------------------------------------------- 200 OK


@pytest.mark.parametrize(
    "path, file, content_type",
    [
        ("/index.html", "index.html", "text/html"),
        ("/pages/about.html", "pages/about.html", "text/html"),
        ("/css/style.css", "css/style.css", "text/css"),
        ("/images/logo.svg", "images/logo.svg", "image/svg+xml"),
        ("/docs/info.txt", "docs/info.txt", "text/plain"),
        ("/assets/data.json", "assets/data.json", "application/json"),
    ],
)
def test_serves_static_files(live_server, path, file, content_type):
    status, headers, body, _ = get(live_server, path)
    expected = (WWW / file).read_bytes()

    assert status == 200
    assert body == expected
    assert headers["content-length"] == str(len(expected))
    assert headers["content-type"].startswith(content_type)


def test_root_maps_to_index(live_server):
    status, _, body, _ = get(live_server, "/")
    assert status == 200
    assert body == (WWW / "index.html").read_bytes()


def test_query_string_is_ignored(live_server):
    status, _, _, _ = get(live_server, "/index.html?v=1")
    assert status == 200


def test_response_format(live_server):
    _, headers, _, status_line = get(live_server, "/index.html")
    assert status_line == "HTTP/1.0 200 OK"
    assert headers["connection"] == "close"


# ---------------------------------------------------------------- errors


def test_missing_file_returns_404(live_server):
    status, _, _, status_line = get(live_server, "/no-such-file.html")
    assert status == 404
    assert status_line == "HTTP/1.0 404 Not Found"


def test_unknown_subdirectory_returns_403(live_server):
    status, _, _, _ = get(live_server, "/private/file.txt")
    assert status == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "HEAD"])
def test_non_get_methods_return_405(live_server, method):
    status, headers, _, _ = get(live_server, "/index.html", method=method)
    assert status == 405
    assert headers["allow"] == "GET"


@pytest.mark.parametrize(
    "raw",
    [
        b"GARBAGE\r\n\r\n",
        b"GET /index.html\r\n\r\n",
        b"GET /index.html FTP/1.0\r\n\r\n",
        b"GET index.html HTTP/1.0\r\n\r\n",
    ],
)
def test_malformed_requests_return_400(live_server, raw):
    status, _, _, _ = send_raw(live_server, raw)
    assert status == 400


def test_oversized_headers_return_400(live_server):
    raw = b"GET /index.html HTTP/1.0\r\nX-Big: " + b"a" * 10_000 + b"\r\n\r\n"
    status, _, _, _ = send_raw(live_server, raw)
    assert status == 400


# ---------------------------------------------------------------- security


@pytest.mark.parametrize(
    "path",
    [
        "/../../etc/passwd",
        "/pages/../../server.py",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/%2E%2E/server.py",
        "/%252e%252e/%252e%252e/etc/passwd",
        "/pages/..%2f..%2fserver.py",
        "/..\\server.py",
        "/pages%5c..%5c..%5cserver.py",
    ],
)
def test_directory_traversal_is_blocked(live_server, path):
    status, _, body, _ = get(live_server, path)
    assert status == 403
    assert b"import socket" not in body


def test_server_source_is_not_reachable(live_server):
    status, _, _, _ = get(live_server, "/server.py")
    assert status == 404


# ---------------------------------------------------------------- TCP stream


def test_partial_reads_are_buffered(live_server):
    parts = [
        b"GET /ind",
        b"ex.html HT",
        b"TP/1.0\r\n",
        b"Host: localhost\r\n",
        b"\r\n",
    ]
    status, _, body, _ = send_raw(live_server, parts, chunk_delay=0.05)
    assert status == 200
    assert body == (WWW / "index.html").read_bytes()


def test_slow_client_does_not_block_others(live_server):
    """A client that connects and sends nothing must not stall other clients."""
    slow = socket.create_connection(live_server)
    slow.sendall(b"GET /index.html HT")  # incomplete request, left hanging
    try:
        start = time.monotonic()
        status, _, _, _ = get(live_server, "/index.html")
        assert status == 200
        assert time.monotonic() - start < 2
    finally:
        slow.close()


def test_handles_many_concurrent_clients(live_server):
    results = []
    lock = threading.Lock()

    def worker():
        status, _, _, _ = get(live_server, "/pages/about.html")
        with lock:
            results.append(status)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results == [200] * 50


# ---------------------------------------------------------------- unit tests


def test_parse_request_line():
    header = "GET /a.html HTTP/1.0\r\nHost: x"
    assert server.parse_request_line(header) == ("GET", "/a.html", "HTTP/1.0")


def test_build_response_headers():
    response = server.build_response(200, b"hello", "text/plain")
    head, _, body = response.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.0 200 OK\r\n")
    assert b"Content-Length: 5" in head
    assert body == b"hello"
