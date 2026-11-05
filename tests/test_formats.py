"""Native document format, browse filters, and API compatibility regressions."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from goreedocs.server import Problem, Store, ROOT


class DocumentFormatTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Store(Path(self.temp.name) / "documents.db")

    def test_native_roundtrip_unicode_and_markdown_interop(self):
        original = self.db.create({"title": "Privacité ✨", "body": "# Privacy\n\nÉtat privé — 🔒",
                                   "folder": "Policies/Legal", "format": "gcdoc"})
        exported = self.db.export(original["id"])
        self.assertEqual(exported["filename"].split(".")[-1], "gcdoc")
        package = json.loads(exported["content"])
        self.assertEqual(package["kind"], "goreecloud.document")
        self.assertEqual(package["schema_version"], 1)
        self.assertEqual(package["body"], original["body"])
        imported = self.db.import_file({"filename": "legal.gcdoc", "content": exported["content"]})
        self.assertNotEqual(imported["id"], original["id"])
        self.assertEqual(imported["format"], "gcdoc")
        self.assertEqual(imported["body"], original["body"])
        self.assertEqual(imported["folder"], "Policies/Legal")
        md = self.db.export(original["id"], "md")
        self.assertEqual(md["content"], original["body"])
        md_import = self.db.import_file({"filename": "my-note.md", "content": "# Hello"})
        self.assertEqual(md_import["title"], "my-note")
        self.assertEqual(md_import["format"], "md")

    def test_android_and_python_accept_same_reference_file(self):
        reference = (ROOT / "android/app/src/test/resources/fixtures/reference-v1.gcdoc")
        content = reference.read_text(encoding="utf-8")
        imported = self.db.import_file({"filename": reference.name, "content": content})
        self.assertEqual(imported["title"], "Reference Notes ✨")
        self.assertEqual(imported["folder"], "Team/Reference")
        self.assertEqual(imported["body"], "# Interoperability\\n\\nRésumé — 🔒\\n\\n- Markdown\\n- UTF-8\\n")
        exported = self.db.export(imported["id"])
        envelope = json.loads(exported["content"])
        original = json.loads(content)
        self.assertEqual(envelope, original)

    def test_bad_native_files_rejected(self):
        for name, content in [
            ("evil.gcdoc", "{}"),
            ("evil.gcdoc", "not json"),
            ("evil.gcdoc", json.dumps({"kind":"goreecloud.document","schema_version":2,"title":"a","body":"x"})),
            ("secret.pdf", "content"),
            ("../secret.md", "# hidden"),
        ]:
            with self.subTest(name=name, content=content):
                with self.assertRaises(Problem):
                    self.db.import_file({"filename": name, "content": content})
        with self.assertRaises(Problem):
            self.db.create({"title":"no", "body":"hi", "format":"pdf"})
        with self.assertRaises(Problem):
            self.db.create({"title":"no", "body":"hi", "favorite":"yes"})

    def test_browse_sort_filter_favorites_and_pages(self):
        first = self.db.create({"title":"alpha","body":"hello","format":"md","folder":"Policies", "favorite":True})
        self.db.create({"title":"zeta","body":"world","format":"gcdoc","folder":"Notes"})
        for index in range(113):
            self.db.create({"title":"draft %03d"%index,"body":"content","folder":"Drafts"})
        start = self.db.search(sort="title",direction="asc",limit=25)
        self.assertEqual(len(start["documents"]),25)
        self.assertEqual(start["total"],115)
        self.assertTrue(start["has_more"])
        tail = self.db.search(sort="title",direction="asc",limit=25,offset=100)
        self.assertEqual(len(tail["documents"]),15)
        self.assertFalse(tail["has_more"])
        self.assertEqual(self.db.search(fmt="md")["total"],1)
        self.assertEqual(self.db.search(favorites=True)["documents"][0]["id"],first["id"])
        self.assertEqual(self.db.search(folder="Policies")["total"],1)
        self.assertEqual(self.db.search(query="WORLD")["total"],1)
        self.assertEqual(self.db.search(recent=True)["total"],115)
        self.assertEqual(self.db.overview()["total"],115)
        self.assertEqual(self.db.overview()["favorites"],1)

    def test_migration_preserves_existing_ids_and_content(self):
        with TemporaryDirectory() as temp:
            database = Path(temp) / "legacy.sqlite"
            with sqlite3.connect(database) as conn:
                conn.execute("""CREATE TABLE documents (id TEXT PRIMARY KEY,title TEXT NOT NULL,
                    body TEXT NOT NULL,folder TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT)""")
                conn.execute("""INSERT INTO documents VALUES ('00000000-0000-0000-0000-000000000001',
                    'old','original','Policies',1,'2025-01-01','2025-01-01',NULL)""")
            database.chmod(0o600)
            migrated=Store(database)
            doc=migrated.get("00000000-0000-0000-0000-000000000001")
            self.assertEqual(doc["body"],"original")
            self.assertEqual(doc["format"],"md")
            self.assertEqual(doc["favorite"],0)

    def test_private_database_mode_is_enforced(self):
        from pathlib import Path
        import os
        with TemporaryDirectory() as temp:
            base = Path(temp)
            db = base / "private.db"
            store = Store(db)
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.search()["total"],0)
            db.chmod(0o644)
            with self.assertRaises(Problem):
                Store(db)

    def test_format_badges_and_browse_controls_in_browser_source(self):
        html = (ROOT / "web/index.html").read_text()
        script = (ROOT / "web/app.js").read_text()
        css = (ROOT / "web/style.css").read_text()
        for id in ("cards", "view-grid", "view-list", "sort", "search", "folders-nav", "format-gcdoc",
                   "format-md", "load-more", "stat-total", "stat-favorites", "import", "export"):
            self.assertIn('id="' + id + '"', html)
        self.assertIn('"thumb-format "', script)
        self.assertIn("formatName(doc.format)", script)
        self.assertIn("position:absolute;top:12px;right:10px", css)
        self.assertIn("gcdocs:default-view", script)


if __name__ == "__main__":
    unittest.main()
