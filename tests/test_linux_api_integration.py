"""End-to-end native Linux client transport checks against a real loopback service.

No GTK display or external network required. This verifies the exact calls made
by the native UI use authenticated document CRUD and optimistic versions.
"""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from goreedocs import cli
from goreedocs.linux import DesktopAPI
from goreedocs.server import Service, Store


class DesktopAPIIntegrationTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = Store(Path(temp.name) / "documents.sqlite3")
        self.token = "local-preview-test-" + "x" * 40
        server = Service(("127.0.0.1", 0), store, self.token)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.url = "http://127.0.0.1:" + str(server.server_address[1])

    def test_native_transport_document_lifecycle(self):
        with patch.dict(os.environ, {
            "GOREEDOCS_URL": self.url,
            "GOREEDOCS_TOKEN": "wrong-environment-token",
        }):
            app = DesktopAPI(lambda path, method="GET", payload=None:
                             cli.call(path, method, payload, token=self.token))
            self.assertEqual(app.list()["total"], 0)
            created = app.create()
            self.assertEqual(created["title"], "Untitled document")
            self.assertEqual(created["format"], "gcdoc")
            self.assertEqual(created["version"], 1)

            ident = created["id"]
            self.assertEqual(app.read(ident)["body"], "")
            saved = app.save(ident, created["version"],
                             "Family Notes", "Family/Records", "# Private ✨")
            self.assertEqual(saved["version"], 2)
            self.assertEqual(saved["body"], "# Private ✨")
            self.assertEqual(app.read(ident)["folder"], "Family/Records")
            found = app.list("Family", offset=0, limit=10)
            self.assertEqual(found["total"], 1)
            self.assertEqual(found["documents"][0]["id"], ident)
            with self.assertRaisesRegex(ValueError, "Version conflict"):
                app.save(ident, 1, "Overwrite", "", "not allowed")
            self.assertEqual(app.read(ident)["title"], "Family Notes")
            self.assertEqual(os.environ["GOREEDOCS_TOKEN"], "wrong-environment-token")

    def test_invalid_gui_session_token_cannot_read_owner_data(self):
        with patch.dict(os.environ, {"GOREEDOCS_URL": self.url,
                                     "GOREEDOCS_TOKEN": self.token}):
            app = DesktopAPI(lambda path, method="GET", payload=None:
                             cli.call(path, method, payload, token="invalid-session"))
            with self.assertRaisesRegex(ValueError, "Authorization required"):
                app.list()


if __name__ == "__main__":
    unittest.main()
