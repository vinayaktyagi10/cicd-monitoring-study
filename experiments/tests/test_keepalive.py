import http.server
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import exp6_overhead as e6


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    connections = 0

    def setup(self):
        super().setup()
        Handler.connections += 1

    def do_GET(self):
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def serve():
    Handler.connections = 0
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/health"


def test_keepalive_client_reuses_one_connection():
    srv, url = serve()
    try:
        client = e6.KeepAliveClient(url)
        results = [client.request() for _ in range(50)]
        client.close()
    finally:
        srv.shutdown()
    assert all(st == 200 for st, _ in results)
    assert Handler.connections == 1


class ClosingHandler(Handler):
    def do_GET(self):
        self.close_connection = True
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


def test_keepalive_client_honours_connection_close():
    Handler.connections = 0
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ClosingHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = e6.KeepAliveClient(f"http://127.0.0.1:{srv.server_address[1]}/health")
        results = [client.request() for _ in range(3)]
        client.close()
    finally:
        srv.shutdown()
    assert all(st == 200 for st, _ in results)
    assert Handler.connections == 3


def test_keepalive_client_reports_refused_connection_as_status_zero():
    srv, url = serve()
    srv.shutdown()
    srv.server_close()
    client = e6.KeepAliveClient(url, timeout=1)
    assert client.request()[0] == 0
    assert client.conn is None


def test_per_request_client_opens_new_connection_each_time():
    srv, url = serve()
    try:
        results = [e6.one_request(url) for _ in range(5)]
    finally:
        srv.shutdown()
    assert all(st == 200 for st, _ in results)
    assert Handler.connections == 5
