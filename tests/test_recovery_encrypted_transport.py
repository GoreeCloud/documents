"""Synthetic CMS-encrypted recovery transport contract; no production data.

Requires a locally installed OpenSSL CLI; skips on unsupported hosts. This
tests explicit owner-controlled encryption, not built-in document encryption,
cloud replication, or operational disaster recovery readiness.
"""
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from goreedocs.recovery import backup_database, restore_database, verify_database
from goreedocs.server import Store


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI unavailable")
class EncryptedRecoveryTransportTest(unittest.TestCase):
    def test_synthetic_backup_survives_public_key_encryption_and_restore(self):
        with TemporaryDirectory(prefix="gcdocs-encrypted-test-") as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            store = Store(source)
            document = store.create({
                "title": "Synthetic encrypted transport",
                "body": "# Fictional QA record\nNo user data",
                "format": "gcdoc",
                "folder": "Private/QA",
            })
            share = store.share(document["id"], 24)
            archive = root / "archive.sqlite3"
            backup_database(source, archive)
            self.assertEqual(verify_database(archive)["documents"], 1)
            original = archive.read_bytes()

            # The private key never leaves this disposable owner-private folder.
            key = root / "private.key"
            cert = root / "recipient.pem"
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert), "-days", "1",
                "-subj", "/CN=GoreeCloud-Documents-synthetic-fixture",
            ], check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=30)
            self.assertEqual(key.stat().st_mode & 0o077, 0)

            compressed = root / "backup.sqlite3.gz"
            compressed.write_bytes(gzip.compress(original, mtime=0))
            encrypted = root / "encrypted.cms"
            subprocess.run([
                "openssl", "cms", "-encrypt", "-binary", "-aes-256-cbc",
                "-in", str(compressed), "-out", str(encrypted),
                "-outform", "DER", str(cert),
            ], check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=30)
            ciphertext = encrypted.read_bytes()
            self.assertNotIn(b"Synthetic encrypted transport", ciphertext)
            self.assertNotEqual(ciphertext, original)

            # The ciphertext is the only artifact needed for transport; the
            # receiver decrypts it using its own private key in this fixture.
            transferred = root / "received.cms"
            transferred.write_bytes(ciphertext)
            output = root / "decrypted.gz"
            subprocess.run([
                "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                "-in", str(transferred), "-recip", str(cert),
                "-inkey", str(key), "-out", str(output),
            ], check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=30)
            recovered = gzip.decompress(output.read_bytes())
            self.assertEqual(hashlib.sha256(recovered).digest(),
                             hashlib.sha256(original).digest())
            received_backup = root / "received.sqlite3"
            received_backup.write_bytes(recovered)
            received_backup.chmod(0o600)
            restored = root / "restored.sqlite3"
            result = restore_database(received_backup, restored)
            self.assertTrue(result["share_links_revoked"])
            self.assertEqual(Store(restored).get(document["id"])["body"],
                             "# Fictional QA record\nNo user data")
            self.assertEqual(store.public(share["token"])["body"],
                             "# Fictional QA record\nNo user data")

            import sqlite3
            with sqlite3.connect(restored) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM shares WHERE revoked_at IS NULL"
                ).fetchone()[0], 0)


    def test_wrong_recipient_or_malformed_envelope_refuses_decryption(self):
        # CMS encryption here is a synthetic transport example, not a
        # production authenticated-backup protocol. In particular, CBC does
        # not itself authenticate modified ciphertext.
        with TemporaryDirectory(prefix="gcdocs-invalid-cms-") as directory:
            root = Path(directory)
            source = root / "synthetic.gz"
            source.write_bytes(gzip.compress(b"Synthetic secret fixture only", mtime=0))
            recipients = []
            for index in (1, 2):
                key = root / ("recipient%d.key" % index)
                cert = root / ("recipient%d.pem" % index)
                subprocess.run([
                    "openssl", "req", "-x509", "-newkey", "rsa:2048",
                    "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=synthetic-recipient-%d" % index,
                ], check=True, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(key.stat().st_mode & 0o077, 0)
                recipients.append((key, cert))

            payload = root / "encrypted.cms"
            subprocess.run([
                "openssl", "cms", "-encrypt", "-binary", "-aes-256-cbc",
                "-in", str(source), "-out", str(payload),
                "-outform", "DER", str(recipients[0][1]),
            ], check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=30)
            original_digest = hashlib.sha256(source.read_bytes()).digest()
            output = root / "decrypted.gz"

            wrong = subprocess.run([
                "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                "-in", str(payload), "-recip", str(recipients[1][1]),
                "-inkey", str(recipients[1][0]), "-out", str(output),
            ], check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=30)
            self.assertNotEqual(wrong.returncode, 0)
            self.assertFalse(output.exists() and
                             output.read_bytes() == source.read_bytes())

            # A malformed ASN.1/CMS envelope is rejected; do not generalize
            # this to authenticated integrity for all CBC tampering.
            malformed = root / "malformed.cms"
            malformed.write_bytes(b"not a CMS envelope" + payload.read_bytes())
            if output.exists():
                output.unlink()
            rejected = subprocess.run([
                "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                "-in", str(malformed), "-recip", str(recipients[0][1]),
                "-inkey", str(recipients[0][0]), "-out", str(output),
            ], check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=30)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),
                             original_digest)


if __name__ == "__main__":
    unittest.main()
