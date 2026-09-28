import socket
import time


HOST = "127.0.0.1"
PORT = 8080


def main():
    request_parts = [
        b"GET /ind",
        b"ex.html HT",
        b"TP/1.0\r\n",
        b"Host: localhost\r\n",
        b"Connection: close\r\n",
        b"\r\n",
    ]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((HOST, PORT))

        for part in request_parts:
            client_socket.sendall(part)
            time.sleep(0.4)

        response = b""
        while True:
            chunk = client_socket.recv(1024)
            if not chunk:
                break
            response += chunk

    print(response.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
