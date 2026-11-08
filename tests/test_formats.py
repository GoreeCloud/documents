"""Native document format, browse filters, and API compatibility regressions."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from goreedocs.server import MAX_JSON, Problem, Store, ROOT


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

    def test_native_export_respects_its_own_import_size_limit(self):
        # Markdown can fit within MAX_BODY while JSON escaping doubles its size.
        escaped_body = "\\" * 600_000
        original = self.db.create({"title": "Large escaped text", "body": escaped_body,
                                   "format": "gcdoc"})
        with self.assertRaises(Problem) as error:
            self.db.export(original["id"], "gcdoc")
        self.assertEqual(error.exception.status, 413)
        self.assertIn("export Markdown", error.exception.message)

        markdown = self.db.export(original["id"], "md")
        self.assertEqual(markdown["content"], escaped_body)
        self.assertEqual(self.db.get(original["id"])["body"], escaped_body)

        small_body = 'A \\"quoted\\" path \\\\ notes\\n' * 30
        small = self.db.create({"title": "Small escaped text", "body": small_body,
                                "format": "gcdoc"})
        native = self.db.export(small["id"], "gcdoc")
        self.assertLessEqual(len(native["content"].encode("utf-8")), MAX_JSON)
        imported = self.db.import_file({"filename": native["filename"],
                                        "content": native["content"]})
        self.assertEqual(imported["body"], small_body)

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

    def test_folder_filter_treats_wildcards_as_literal_path_characters(self):
        cases = [
            ("Finance%", "percent root", "Finance%"),
            ("Finance%/2026", "percent descendant", "Finance%"),
            ("FinanceQ", "regular root", "FinanceQ"),
            ("FinanceQ/2026", "regular descendant", "FinanceQ"),
            ("Team_2026", "underscore root", "Team_2026"),
            ("Team_2026/Notes", "underscore descendant", "Team_2026"),
            ("TeamX2026", "similar root", "TeamX2026"),
            ("TeamX2026/Notes", "similar descendant", "TeamX2026"),
            ("Policies", "policy root", "Policies"),
            ("Policies/Legal", "policy descendant", "Policies"),
            ("PoliciesArchive", "different prefix", "PoliciesArchive"),
        ]
        for folder, title, _ in cases:
            self.db.create({"title": title, "body": "test", "folder": folder})

        expected = {
            "Finance%": {"percent root", "percent descendant"},
            "FinanceQ": {"regular root", "regular descendant"},
            "Team_2026": {"underscore root", "underscore descendant"},
            "TeamX2026": {"similar root", "similar descendant"},
            "Policies": {"policy root", "policy descendant"},
            "PoliciesArchive": {"different prefix"},
        }
        for folder, titles in expected.items():
            with self.subTest(folder=folder):
                found = self.db.search(folder=folder, limit=50)
                self.assertEqual(found["total"], len(titles))
                self.assertEqual({doc["title"] for doc in found["documents"]}, titles)
                self.assertFalse(found["has_more"])

        self.assertEqual(self.db.search(folder="Finance%/2026")["total"], 1)
        self.assertEqual(self.db.search(folder="Team_2026/Notes")["total"], 1)
        self.assertEqual(self.db.search(folder="missing%")["total"], 0)

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

    def test_browser_native_export_requires_consent_for_markdown_fallback(self):
        script = (ROOT / "web/app.js").read_text()
        self.assertIn('if (e.status !== 413 || current.format !== "gcdoc") throw e;', script)
        self.assertIn('const approved = confirm(', script)
        self.assertIn('folder metadata is not included', script)
        self.assertIn('if (!approved) { status("Download canceled; document unchanged"); return; }', script)
        self.assertIn('"/export?format=md"', script)
        self.assertIn('if (!current || dirty || saving)', script)

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
