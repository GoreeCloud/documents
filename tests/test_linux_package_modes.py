"""Debian package modes must not vary with a hardened caller umask."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "packaging/linux/build_deb.py"


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("sh")
                     and shutil.which("dpkg-deb"), "Debian packager unavailable")
class DebianPackageModesTest(unittest.TestCase):
    def test_owner_private_build_produces_installable_package_directories(self):
        with TemporaryDirectory(prefix="gcdocs-deb-modes-") as folder:
            package = Path(folder) / "goreecloud-documents.deb"
            command = ["sh", "-c", 'umask 077; exec "$@"', "sh",
                       sys.executable, str(BUILDER), str(package)]
            built = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=30,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertTrue(package.is_file())

            listed = subprocess.run(
                ["dpkg-deb", "--contents", str(package)],
                capture_output=True, text=True, timeout=15, check=True,
            ).stdout.splitlines()
            directories = [line for line in listed if line.startswith("d")]
            self.assertGreater(len(directories), 4)
            for entry in directories:
                with self.subTest(entry=entry):
                    self.assertEqual(entry.split()[0], "drwxr-xr-x")
            self.assertTrue(any("usr/lib/goreecloud-documents/" in line
                                for line in listed))
            self.assertTrue(any("./usr/bin/goreecloud-documents" in line
                                for line in listed))

            # The builder must not overwrite its prior verified output.
            first_digest = hashlib.sha256(package.read_bytes()).digest()
            second = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=30,
                check=False,
            )
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(hashlib.sha256(package.read_bytes()).digest(),
                             first_digest)


if __name__ == "__main__":
    unittest.main()
