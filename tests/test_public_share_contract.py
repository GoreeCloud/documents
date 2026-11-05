"""Public-share HTTP security contract on a disposable loopback Documents service.

A share is a read-only capability for selected presentation fields, never an
owner API credential. No real documents or external network endpoints are used.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from goreedocs.server import Service, Store


class PublicShareContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "temporary.sqlite3")
        self.owner_token = "local-fixture-only-" + "abcdefghij" * 4
        self.server = Service(("127.0.0.1", 0), self.store, self.owner_token)
        self.addCleanup(self.server.server_close)
        runner = threading.Thread(target=self.server.serve_forever, daemon=True)
        runner.start()
        self.addCleanup(self.server.shutdown)
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.document = self.store.create({
            "title": "Fixture: private memo",
            "body": "# Example\nSynthetic content only.",
            "folder": "Confidential/Test",
            "format": "gcdoc",
        })
        self.share = self.store.share(self.document["id"], 24)

    def get(self, path, authorization=None):
        headers = {}
        if authorization is not None:
            headers["Authorization"] = authorization
        request = Request(self.base + path, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.load(response), response.headers
        except HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def test_public_capability_exposes_only_minimal_read_fields(self):
        status, public, headers = self.get("/api/public/" + self.share["token"])
        self.assertEqual(status, 200)
        self.assertEqual(
            set(public), {"title", "body", "updated_at", "expires_at"}
        )
        self.assertEqual(public["title"], "Fixture: private memo")
        self.assertEqual(public["body"], "# Example\nSynthetic content only.")
        for private_field in ("id", "folder", "version", "favorite", "deleted_at"):
            self.assertNotIn(private_field, public)
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_public_capability_is_not_owner_authentication(self):
        identifier = self.document["id"]
        for path in (
            "/api/documents",
            "/api/documents/" + identifier,
            "/api/documents/" + identifier + "/revisions",
            "/api/documents/" + identifier + "/export?format=md",
            "/api/overview",
        ):
            with self.subTest(path=path):
                code, payload, _ = self.get(path)
                self.assertEqual(code, 401)
                self.assertIn("error", payload)
                code, _, _ = self.get(
                    path, "Bearer " + self.share["token"]
                )
                self.assertEqual(code, 401)

        code, owner_document, _ = self.get(
            "/api/documents/" + identifier, "Bearer " + self.owner_token
        )
        self.assertEqual(code, 200)
        self.assertEqual(owner_document["id"], identifier)
        self.assertEqual(owner_document["folder"], "Confidential/Test")

    def test_revoked_expired_and_invalid_public_tokens_are_denied(self):
        token = self.share["token"]
        code, _, _ = self.get("/api/public/not-a-valid-token")
        self.assertEqual(code, 404)
        self.store.revoke(token)
        code, _, _ = self.get("/api/public/" + token)
        self.assertEqual(code, 404)

        later = self.store.share(self.document["id"], 24)["token"]
        # Expire the disposable test fixture directly in its isolated database.
        with self.store.db() as connection:
            connection.execute(
                "UPDATE shares SET expires_at=? WHERE revoked_at IS NULL",
                ("2000-01-01T00:00:00+00:00",)
            )
        code, _, _ = self.get("/api/public/" + later)
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
