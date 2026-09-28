import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


@pytest.fixture(params=["thread", "pool"])
def live_server(request):
    """Start the real server on a free port, in both concurrency modes."""
    server_socket = server.create_server_socket("127.0.0.1", 0)
    host, port = server_socket.getsockname()
    stop = threading.Event()
    thread = threading.Thread(
        target=server.serve_forever,
        args=(server_socket, request.param, 4, stop),
        daemon=True,
    )
    thread.start()
    yield host, port
    stop.set()
    thread.join(timeout=2)
    server_socket.close()


def send_raw(address, request_bytes, chunk_delay=None, timeout=5):
    """
    Send raw bytes to the server and return (status_code, headers, body).

    If chunk_delay is set, request_bytes must be a list of byte chunks that are
    sent one by one with a pause in between (to simulate partial TCP reads).
    """
    with socket.create_connection(address, timeout=timeout) as sock:
        if chunk_delay is None:
            sock.sendall(request_bytes)
        else:
            for chunk in request_bytes:
                sock.sendall(chunk)
                time.sleep(chunk_delay)

        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data

    head, _, body = response.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    status_code = int(lines[0].split()[1])
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status_code, headers, body, lines[0]


def get(address, path, method="GET"):
    request = f"{method} {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode()
    return send_raw(address, request)
