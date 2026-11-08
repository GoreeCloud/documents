"""Fail-closed extraction of an inspected Android CI debug transport ZIP.

The ZIP is not the required standalone Google Drive APK. Callers must obtain
the source commit and APK checksum independently from the successful GitHub
Actions run, not from the untrusted ZIP being extracted. This tool does not
verify APK signatures, Android permissions, or software release readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile


MAX_TRANSPORT_BYTES = 80 * 1024 * 1024
MAX_APK_BYTES = 64 * 1024 * 1024
NAME = re.compile(
    r"GoreeCloud-Documents-0\.1\.0-dev-([0-9a-f]{40})-CI-debug\.apk\Z"
)
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")


class InvalidDebugBundle(ValueError):
    """Reject a malformed, wrong-run, or unverified transport bundle."""


def extract_bundle(archive, output_folder, expected_source_sha, expected_sha256):
    if not SOURCE_SHA.fullmatch(expected_source_sha):
        raise InvalidDebugBundle("Expected source SHA must be exactly 40 lowercase hex digits")
    if not SHA256.fullmatch(expected_sha256):
        raise InvalidDebugBundle("Expected APK SHA-256 must be exactly 64 lowercase hex digits")
    archive = Path(archive).expanduser().absolute()
    folder = Path(output_folder).expanduser().absolute()
    if archive.is_symlink() or not archive.is_file():
        raise InvalidDebugBundle("Transport must be a regular non-symlink ZIP")
    if archive.stat().st_size > MAX_TRANSPORT_BYTES:
        raise InvalidDebugBundle("Transport ZIP exceeds size limit")
    if folder.is_symlink() or not folder.is_dir():
        raise InvalidDebugBundle("Output directory must exist and not be a symbolic link")
    if stat.S_IMODE(folder.stat().st_mode) & 0o077:
        raise InvalidDebugBundle("Output directory must be owner-private (chmod 700)")

    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            members = bundle.infolist()
            if len(members) != 2:
                raise InvalidDebugBundle("Expected exactly one APK and one SHA256SUMS.txt")
            mapping = {member.filename: member for member in members}
            if len(mapping) != 2 or "SHA256SUMS.txt" not in mapping:
                raise InvalidDebugBundle("Transport has missing or duplicate members")
            names = [name for name in mapping if name != "SHA256SUMS.txt"]
            if len(names) != 1 or NAME.fullmatch(names[0]) is None:
                raise InvalidDebugBundle("Unexpected APK filename")
            name = names[0]
            if NAME.fullmatch(name).group(1) != expected_source_sha:
                raise InvalidDebugBundle("APK filename does not match independently verified source")
            for info in members:
                mode = (info.external_attr >> 16) & 0xFFFF
                if (info.is_dir() or
                        stat.S_IFMT(mode) == stat.S_IFLNK or
                        info.flag_bits & 0x1):
                    raise InvalidDebugBundle("Directories, symlinks and encrypted entries are refused")
            if (mapping["SHA256SUMS.txt"].file_size > 256 or
                    mapping[name].file_size > MAX_APK_BYTES):
                raise InvalidDebugBundle("Transport member exceeds size limit")
            checksum_file = bundle.read("SHA256SUMS.txt").decode("ascii")
            if checksum_file != expected_sha256 + "  " + name + "\n":
                raise InvalidDebugBundle("Transport checksum differs from independent CI evidence")
            target = folder / name
            if os.path.lexists(target):
                raise FileExistsError("Refusing to overwrite existing APK: " + str(target))

            descriptor, temporary = tempfile.mkstemp(
                prefix=".goreecloud-documents-apk-", suffix=".tmp", dir=folder
            )
            try:
                digest = hashlib.sha256()
                total = 0
                with os.fdopen(descriptor, "wb") as output:
                    with bundle.open(name, "r") as payload:
                        for chunk in iter(lambda: payload.read(1024 * 1024), b""):
                            total += len(chunk)
                            if total > MAX_APK_BYTES:
                                raise InvalidDebugBundle("APK uncompressed bytes exceed size limit")
                            digest.update(chunk)
                            output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if total != mapping[name].file_size or digest.hexdigest() != expected_sha256:
                    raise InvalidDebugBundle("APK content failed independent SHA-256 verification")
                # Publish atomically and never overwrite a previous extraction.
                os.link(temporary, target)
            finally:
                os.unlink(temporary)
            return {
                "standalone_apk": str(target),
                "source_commit": expected_source_sha,
                "sha256": expected_sha256,
                "bytes": total,
                "release_signed": False,
                "drive_delivery_complete": False,
            }
    except (zipfile.BadZipFile, UnicodeError, EOFError) as exc:
        raise InvalidDebugBundle("Invalid or corrupted transport ZIP") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport_zip")
    parser.add_argument("private_output_directory")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-apk-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = extract_bundle(
            args.transport_zip, args.private_output_directory,
            args.expected_source_sha, args.expected_apk_sha256,
        )
    except (InvalidDebugBundle, OSError) as failure:
        print("Debug APK extraction refused: " + str(failure), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
