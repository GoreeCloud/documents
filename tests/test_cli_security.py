"""Credential-routing regressions for the CLI and the local MCP transport."""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest
from unittest.mock import patch

from goreedocs import cli


class EndpointValidationTest(unittest.TestCase):
    def test_valid_explicit_loopback_and_tls_endpoints(self):
        for url in (
            "http://127.0.0.1:8735", "http://localhost:8735/",
            "http://[::1]:8735", "https://documents.example.org",
            "https://documents.example.org:443/",
        ):
            with self.subTest(url=url):
                self.assertEqual(cli.validate_endpoint(url), url.rstrip("/"))

    def test_rejects_confusing_authority_and_non_loopback_http(self):
        for url in (
            "http://localhost:8735@elsewhere.example",
            "http://127.0.0.1:8735@elsewhere.example",
            "http://localhost.evil.example:8735",
            "http://0.0.0.0:8735", "http://192.168.1.8:8735",
            "ftp://127.0.0.1:8735", "https://user:secret@host.example",
            "https://documents.example.org/api",
            "https://documents.example.org/?token=secret",
            "https://documents.example.org/#anchor",
            "https://documents.example.org:99999",
            "http://[::ffff:127.0.0.1]:8735",
            "http://localhost:bad",
            "http://localhost:8735\nInjected",
            "", "//localhost:8735",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    cli.validate_endpoint(url)

    def test_redirect_never_forwards_authorization_or_request(self):
        class RedirectingHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/api/"):
                    self.send_response(302)
                    self.send_header("Location", "/redirect-target")
                    self.end_headers()
                else:
                    self.server.followed.append(("GET", self.headers.get("Authorization")))
                    self.send_response(200)
                    self.end_headers()

            def do_POST(self):
                if self.path.startswith("/api/"):
                    self.send_response(307)
                    self.send_header("Location", "/redirect-target")
                    self.end_headers()
                else:
                    self.server.followed.append(("POST", self.headers.get("Authorization")))
                    self.send_response(200)
                    self.end_headers()

            def log_message(self, *_):
                pass

        server = HTTPServer(("127.0.0.1", 0), RedirectingHandler)
        server.followed = []
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        url = "http://127.0.0.1:" + str(server.server_port)
        with patch.dict(os.environ, {"GOREEDOCS_URL": url, "GOREEDOCS_TOKEN": "test-private-token"}):
            with self.assertRaisesRegex(ValueError, "redirects are not permitted"):
                cli.call("/api/documents")
            with self.assertRaisesRegex(ValueError, "redirects are not permitted"):
                cli.call("/api/documents", "POST", {"title": "never forwarded"})
        self.assertEqual(server.followed, [])


if __name__ == "__main__":
    unittest.main()
