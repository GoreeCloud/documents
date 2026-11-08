"""Loopback HTTP integration contract for an isolated restored Documents snapshot.

All databases and bearer credentials are disposable test fixtures.
No production database, network binding, or user material is accessed.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from goreedocs.recovery import backup_database, restore_database
from goreedocs.server import Service, Store


class RecoveryHTTPIntegrationTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source_path = self.base / "original.sqlite3"
        self.source = Store(self.source_path)
        self.doc = self.source.create({
            "title": "Synthetic confidential fixture",
            "body": "# Example private document",
            "folder": "Private/Tests",
            "format": "gcdoc",
        })
        self.share = self.source.share(self.doc["id"], 24)
        self.owner = "test-only-owner-" + "a" * 40

    def serve(self, store, owner):
        server = Service(("127.0.0.1", 0), store, owner)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:" + str(server.server_port)

    def request(self, address, owner=None):
        headers = {} if owner is None else {"Authorization": "Bearer " + owner}
        try:
            with urlopen(Request(address, headers=headers), timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_restore_retains_owner_document_but_invalidates_old_public_link(self):
        snapshot = self.base / "backup.sqlite3"
        restored_path = self.base / "isolated.sqlite3"
        backup_database(self.source_path, snapshot)
        restore_database(snapshot, restored_path)

        original_url = self.serve(self.source, self.owner)
        new_owner = "test-only-restored-owner-" + "b" * 40
        restored_url = self.serve(Store(restored_path), new_owner)
        link_path = "/api/public/" + self.share["token"]

        status, source_public = self.request(original_url + link_path)
        self.assertEqual(status, 200)
        self.assertEqual(source_public["body"], "# Example private document")

        status, response = self.request(restored_url + link_path)
        self.assertEqual(status, 404)
        self.assertIn("error", response)

        doc_path = "/api/documents/" + self.doc["id"]
        status, _ = self.request(restored_url + doc_path)
        self.assertEqual(status, 401)
        status, _ = self.request(restored_url + doc_path, self.owner)
        self.assertEqual(status, 401)

        status, recovered = self.request(restored_url + doc_path, new_owner)
        self.assertEqual(status, 200)
        self.assertEqual(recovered["body"], "# Example private document")
        self.assertEqual(recovered["folder"], "Private/Tests")

        # The isolated restore must not change the original database or link.
        status, source_public = self.request(original_url + link_path)
        self.assertEqual(status, 200)
        self.assertEqual(source_public["title"], "Synthetic confidential fixture")
        self.assertNotIn("id", source_public)


if __name__ == "__main__":
    unittest.main()
