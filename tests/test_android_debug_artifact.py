"""Synthetic tests for verified standalone Android APK extraction.

These archives contain deliberately fake APK bytes. They test transport
integrity and custody checks, not app signing or actual APK compatibility.
"""
import hashlib
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from tools import extract_android_ci_debug_apk as extractor


SOURCE = "a" * 40
PAYLOAD = b"PK\x03\x04synthetic-not-installable-apk-bytes"
SHA = hashlib.sha256(PAYLOAD).hexdigest()
NAME = f"GoreeCloud-Documents-0.1.0-dev-{SOURCE}-CI-debug.apk"


class AndroidDebugBundleTest(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix="gcdocs-bundle-")
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.private = self.base / "private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.bundle = self.base / "transport.zip"

    def transport(self, payload=PAYLOAD, checksum=SHA, archive_name=NAME):
        with ZipFile(self.bundle, "w") as bundle:
            bundle.writestr(archive_name, payload)
            bundle.writestr("SHA256SUMS.txt", f"{checksum}  {archive_name}\n")

    def extraction(self, **kw):
        return extractor.extract_bundle(
            self.bundle, self.private, kw.get("source", SOURCE),
            kw.get("sha256", SHA),
        )

    def test_verified_bundle_produces_standalone_file_with_no_overwrite(self):
        self.transport()
        result = self.extraction()
        output = Path(result["standalone_apk"])
        self.assertEqual(output.name, NAME)
        self.assertEqual(output.read_bytes(), PAYLOAD)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result["sha256"], SHA)
        self.assertFalse(result["release_signed"])
        self.assertFalse(result["drive_delivery_complete"])
        with self.assertRaises(FileExistsError):
            self.extraction()
        self.assertEqual(output.read_bytes(), PAYLOAD)

    def test_corrupted_payload_is_rejected_without_published_file(self):
        self.transport(payload=b"changed payload with original checksum")
        with self.assertRaisesRegex(extractor.InvalidDebugBundle, "SHA-256"):
            self.extraction()
        self.assertFalse((self.private / NAME).exists())
        self.assertEqual(list(self.private.iterdir()), [])

    def test_self_reported_archive_hash_is_not_independent_trust(self):
        forged = hashlib.sha256(b"modified").hexdigest()
        self.transport(payload=b"modified", checksum=forged)
        with self.assertRaisesRegex(extractor.InvalidDebugBundle, "independent CI"):
            self.extraction()
        self.assertFalse((self.private / NAME).exists())

    def test_wrong_source_commit_refused(self):
        self.transport()
        with self.assertRaisesRegex(extractor.InvalidDebugBundle, "source"):
            self.extraction(source="b" * 40)
        self.assertEqual(list(self.private.iterdir()), [])

    def test_traversal_member_and_duplicate_are_rejected(self):
        self.transport(archive_name="../evil.apk")
        with self.assertRaises(extractor.InvalidDebugBundle):
            self.extraction()
        self.assertEqual(list(self.private.iterdir()), [])
        with ZipFile(self.bundle, "w") as bundle:
            bundle.writestr(NAME, PAYLOAD)
            bundle.writestr(NAME, PAYLOAD)
            bundle.writestr("SHA256SUMS.txt", f"{SHA}  {NAME}\n")
        with self.assertRaises(extractor.InvalidDebugBundle):
            self.extraction()

    def test_symlinked_output_directory_is_rejected(self):
        self.transport()
        alias = self.base / "alias"
        alias.symlink_to(self.private, target_is_directory=True)
        with self.assertRaisesRegex(extractor.InvalidDebugBundle, "symbolic link"):
            extractor.extract_bundle(self.bundle, alias, SOURCE, SHA)
        self.assertEqual(list(self.private.iterdir()), [])

    def test_symlinked_apk_member_and_declared_size_limit_rejected(self):
        with ZipFile(self.bundle, "w") as bundle:
            link = ZipInfo(NAME)
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(link, b"outside")
            bundle.writestr("SHA256SUMS.txt", f"{SHA}  {NAME}\n")
        with self.assertRaisesRegex(extractor.InvalidDebugBundle, "symlinks"):
            self.extraction()
        self.transport()
        with patch.object(extractor, "MAX_APK_BYTES", 4):
            with self.assertRaisesRegex(extractor.InvalidDebugBundle, "size limit"):
                self.extraction()

    def test_invalid_zip_and_private_directory_permission_refused(self):
        self.bundle.write_bytes(b"not a zip archive")
        with self.assertRaises(extractor.InvalidDebugBundle):
            self.extraction()
        self.transport()
        self.private.chmod(0o755)
        with self.assertRaisesRegex(extractor.InvalidDebugBundle, "owner-private"):
            self.extraction()

    def test_debug_artifact_stage_requires_verified_apk_and_short_retention(self):
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/android.yml"
        ).read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("Inspect tracked source, APK archive, debug signature"),
            workflow.index("Stage the verified CI debug APK"),
        )
        self.assertLess(
            workflow.index("Stage the verified CI debug APK"),
            workflow.index("Retain short-lived debug transport ZIP"),
        )
        self.assertIn("retention-days: 2", workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertIn("actions/upload-artifact@", workflow)
        self.assertIn("not standalone", workflow.lower())


if __name__ == "__main__":
    unittest.main()
