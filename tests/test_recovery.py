"""Recovery regression tests: WAL-safe backup, private files, and safe restore."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from goreedocs.recovery import (
    RecoveryError, backup_database, restore_database, verify_database,
)
from goreedocs.server import Store


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "live.sqlite3"
        self.store = Store(self.source)

    def test_backup_copies_complete_document_history_and_isolation(self):
        doc = self.store.create({
            "title": "Archive 🗂️", "body": "# Original\n\nPrivate text",
            "folder": "Family", "format": "gcdoc", "favorite": True,
        })
        self.store.update(doc["id"], {"body": "# Revised"}, doc["version"])
        self.store.create({"title": "Markdown", "body": "hello", "format": "md"})
        target = self.base / "archive.sqlite3"
        result = backup_database(self.source, target)
        self.assertEqual(result["documents"], 2)
        self.assertEqual(result["revisions"], 3)
        self.assertEqual(verify_database(target)["documents"], 2)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.base / "archive.sqlite3-wal").exists())
        with sqlite3.connect(target) as snapshot:
            text = snapshot.execute(
                "SELECT body FROM documents WHERE id=?", (doc["id"],)
            ).fetchone()[0]
            self.assertEqual(text, "# Revised")
            self.assertEqual(snapshot.execute(
                "SELECT count(*) FROM revisions WHERE doc_id=?", (doc["id"],)
            ).fetchone()[0], 2)
        self.store.update(doc["id"], {"body": "# After backup"}, 2)
        with sqlite3.connect(target) as snapshot:
            self.assertEqual(snapshot.execute(
                "SELECT body FROM documents WHERE id=?", (doc["id"],)
            ).fetchone()[0], "# Revised")

    def test_restore_creates_new_database_and_revokes_snapshot_shares(self):
        doc = self.store.create({"title": "Sensitive", "body": "Never publish"})
        link = self.store.share(doc["id"], 24)
        archive = self.base / "backup.sqlite3"
        backup_database(self.source, archive)
        restored = self.base / "restored.sqlite3"
        result = restore_database(archive, restored)
        self.assertTrue(result["share_links_revoked"])
        self.assertEqual(Store(restored).get(doc["id"])["body"], "Never publish")
        with sqlite3.connect(restored) as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM shares WHERE revoked_at IS NULL"
            ).fetchone()[0], 0)
        # A restore never revokes shares in the original source or backup.
        self.assertEqual(self.store.public(link["token"])["body"], "Never publish")
        with sqlite3.connect(archive) as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM shares WHERE revoked_at IS NULL"
            ).fetchone()[0], 1)

    def test_existing_destination_and_symlink_never_overwritten(self):
        doc = self.store.create({"title": "Keep", "body": "unchanged"})
        target = self.base / "must-not-overwrite.sqlite3"
        target.write_bytes(b"existing bytes")
        target.chmod(0o600)
        with self.assertRaises(RecoveryError):
            backup_database(self.source, target)
        self.assertEqual(target.read_bytes(), b"existing bytes")
        link = self.base / "symlink.sqlite3"
        link.symlink_to(target)
        with self.assertRaises(RecoveryError):
            backup_database(self.source, link)
        self.assertEqual(target.read_bytes(), b"existing bytes")
        with self.assertRaises(RecoveryError):
            restore_database(self.source, target)
        self.assertEqual(self.store.get(doc["id"])["body"], "unchanged")

    def test_invalid_source_and_public_backup_directory_rejected(self):
        bad = self.base / "bad.sqlite3"
        bad.write_bytes(b"this is not SQLite")
        bad.chmod(0o600)
        with self.assertRaises(RecoveryError):
            verify_database(bad)
        with self.assertRaises(RecoveryError):
            restore_database(bad, self.base / "should-not-exist.sqlite3")
        self.assertFalse((self.base / "should-not-exist.sqlite3").exists())
        public = self.base / "public"
        public.mkdir(mode=0o755)
        # A hardened runner may inherit umask 077; make the unsafe fixture
        # mode explicit so this test checks the backup guard, not umask.
        public.chmod(0o755)
        with self.assertRaises(RecoveryError):
            backup_database(self.source, public / "no.sqlite3")
        self.assertFalse((public / "no.sqlite3").exists())

    def test_symlinked_private_backup_destination_directory_is_rejected(self):
        self.store.create({"title": "No destination redirect", "body": "Private"})
        private = self.base / "actual-private"
        private.mkdir(mode=0o700)
        private.chmod(0o700)
        alias = self.base / "directory-link"
        alias.symlink_to(private, target_is_directory=True)

        with self.assertRaisesRegex(RecoveryError, "symbolic link"):
            backup_database(self.source, alias / "should-not-appear.sqlite3")
        with self.assertRaisesRegex(RecoveryError, "symbolic link"):
            restore_database(self.source, alias / "also-not-created.sqlite3")
        self.assertEqual(list(private.iterdir()), [])
        self.assertTrue(alias.is_symlink())
        self.assertEqual(verify_database(self.source)["documents"], 1)

    def test_source_must_be_owner_private(self):
        self.store.create({"title": "Private", "body": "text"})
        self.source.chmod(0o644)
        with self.assertRaises(RecoveryError):
            verify_database(self.source)
        with self.assertRaises(RecoveryError):
            backup_database(self.source, self.base / "blocked.sqlite3")


    def test_wal_snapshot_includes_committed_changes_with_reader_open(self):
        doc = self.store.create({"title": "WAL reader", "body": "earlier"})
        reader = sqlite3.connect(self.source)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM documents").fetchone()
            self.store.update(doc["id"], {"body": "committed while reader open"}, 1)
            self.assertTrue((self.base / "live.sqlite3-wal").exists())
            output = self.base / "wal-archive.sqlite3"
            result = backup_database(self.source, output)
            self.assertEqual(result["documents"], 1)
            with sqlite3.connect(output) as conn:
                stored = conn.execute(
                    "SELECT body FROM documents WHERE id=?", (doc["id"],)
                ).fetchone()[0]
            self.assertEqual(stored, "committed while reader open")
        finally:
            reader.close()

    def test_publication_failure_preserves_source_and_removes_temporary_files(self):
        from unittest.mock import patch

        doc = self.store.create({"title": "Do not lose", "body": "original"})
        output = self.base / "no-space.sqlite3"
        with patch("goreedocs.recovery.os.link", side_effect=OSError(28, "No space left")):
            with self.assertRaises(OSError):
                backup_database(self.source, output)
        self.assertFalse(output.exists())
        self.assertFalse(any(self.base.glob(".goreedocs-recovery-*")))
        self.assertEqual(self.store.get(doc["id"])["body"], "original")

    def test_symlink_source_database_is_rejected(self):
        self.store.create({"title": "Private", "body": "safe"})
        alias = self.base / "alias.sqlite3"
        alias.symlink_to(self.source)
        with self.assertRaises(RecoveryError):
            verify_database(alias)
        with self.assertRaises(RecoveryError):
            backup_database(alias, self.base / "from-alias.sqlite3")
        self.assertFalse((self.base / "from-alias.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
