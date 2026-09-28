import mimetypes
import socket
import threading
from pathlib import Path
from urllib.parse import unquote


HOST = "127.0.0.1"
PORT = 8080
MAX_HEADER_SIZE = 8192
RECV_SIZE = 1024

BASE_DIR = Path(__file__).parent.resolve()
WWW_DIR = (BASE_DIR / "www").resolve()
ALLOWED_SUBDIRECTORIES = {"pages", "css", "images", "docs", "assets"}

STATUS_MESSAGES = {
    200: "OK",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}


class HTTPError(Exception):
    """Small exception used to stop request processing with an HTTP status."""

    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(STATUS_MESSAGES[status_code])


def read_request_headers(client_socket):
    """
    Read bytes from the TCP stream until the HTTP header terminator is found.

    TCP does not preserve application message boundaries, so one recv() call may
    contain a partial request, exactly one request, or more data than expected.
    """
    data = b""

    while b"\r\n\r\n" not in data:
        chunk = client_socket.recv(RECV_SIZE)
        if not chunk:
            break

        data += chunk
        if len(data) > MAX_HEADER_SIZE:
            raise HTTPError(400)

    if b"\r\n\r\n" not in data:
        raise HTTPError(400)

    header_bytes = data.split(b"\r\n\r\n", 1)[0]
    return header_bytes.decode("iso-8859-1")


def parse_request_line(header_text):
    """Extract method, path, and version from the first HTTP header line."""
    lines = header_text.split("\r\n")
    if not lines or not lines[0].strip():
        raise HTTPError(400)

    parts = lines[0].split()
    if len(parts) != 3:
        raise HTTPError(400)

    method, path, version = parts
    if not version.startswith("HTTP/1."):
        raise HTTPError(400)

    return method, path, version


def resolve_requested_file(request_path):
    """
    Convert a URL path into a local file path under www/.

    This function blocks directory traversal and blocks unknown subdirectories.
    """
    path_without_query = request_path.split("?", 1)[0].split("#", 1)[0]
    if path_without_query == "/":
        path_without_query = "/index.html"

    if not path_without_query.startswith("/"):
        raise HTTPError(400)

    try:
        decoded_path = path_without_query
        for _ in range(3):
            next_decoded_path = unquote(decoded_path, errors="strict")
            if next_decoded_path == decoded_path:
                break
            decoded_path = next_decoded_path
    except UnicodeDecodeError:
        raise HTTPError(400)

    # Block plain and URL-decoded traversal. The repeated decoding above also
    # blocks double-encoded traversal such as %252e%252e. Backslashes are
    # rejected because they can act as path separators on Windows.
    if ".." in decoded_path or "\\" in decoded_path:
        raise HTTPError(403)

    relative_path = decoded_path.lstrip("/")
    if not relative_path:
        relative_path = "index.html"

    first_part = relative_path.split("/", 1)[0]
    uses_subdirectory = "/" in relative_path
    if uses_subdirectory and first_part not in ALLOWED_SUBDIRECTORIES:
        raise HTTPError(403)

    requested_file = (WWW_DIR / relative_path).resolve()

    # Final safety check: the resolved path must still be inside www/.
    try:
        requested_file.relative_to(WWW_DIR)
    except ValueError:
        raise HTTPError(403)

    if not requested_file.is_file():
        raise HTTPError(404)

    return requested_file


def build_response(status_code, body=b"", content_type="text/plain; charset=utf-8"):
    """Create an HTTP/1.0 response with required headers and raw body bytes."""
    reason = STATUS_MESSAGES[status_code]
    header_lines = [
        f"HTTP/1.0 {status_code} {reason}",
        f"Content-Length: {len(body)}",
        f"Content-Type: {content_type}",
        "Connection: close",
    ]

    if status_code == 405:
        header_lines.append("Allow: GET")

    headers = "\r\n".join(header_lines).encode("iso-8859-1") + b"\r\n\r\n"
    return headers + body


def build_file_response(file_path):
    """Read a static file and build a 200 OK response for it."""
    body = file_path.read_bytes()
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "application/octet-stream"

    return build_response(200, body, content_type)


def build_error_response(status_code):
    """Build a simple text response for an error status."""
    reason = STATUS_MESSAGES[status_code]
    body = f"{status_code} {reason}\n".encode("utf-8")
    return build_response(status_code, body)


def handle_client(client_socket, client_address):
    """
    Handle one client connection.

    Each accepted connection runs in its own thread. The with-statement closes
    the client socket after the response is sent.
    """
    with client_socket:
        client_socket.settimeout(10)

        try:
            header_text = read_request_headers(client_socket)
            method, path, version = parse_request_line(header_text)
            print(f"{client_address[0]}:{client_address[1]} {method} {path} {version}")

            if method != "GET":
                raise HTTPError(405)

            requested_file = resolve_requested_file(path)
            response = build_file_response(requested_file)

        except HTTPError as error:
            response = build_error_response(error.status_code)
        except Exception as error:
            print(f"Internal server error for {client_address}: {error}")
            response = build_error_response(500)

        client_socket.sendall(response)


def run_server():
    """Create the listening TCP socket and accept clients forever."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # bind() chooses the local IP address and port for this server process.
        server_socket.bind((HOST, PORT))

        # listen() marks the socket as a passive socket that can accept clients.
        server_socket.listen()
        print(f"Serving http://{HOST}:{PORT}/ from {WWW_DIR}")
        print("Press Ctrl+C to stop the server.")

        while True:
            # accept() waits for a new TCP connection and returns a new socket
            # used only for that client.
            client_socket, client_address = server_socket.accept()

            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True,
            )
            thread.start()


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nServer stopped.")
