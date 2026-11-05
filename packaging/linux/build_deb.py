"""Build an offline, reviewable Debian GTK4 development-preview package.

This tool only creates a local .deb. It does not install, execute, publish,
upload or overwrite a package, and does not read secrets or API tokens.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "goreecloud-documents"
VERSION = "0.1.0~dev1"
DEB_NAME = f"{PACKAGE}_{VERSION}_all.deb"


def copy_file(staging, from_relative, destination, executable=False):
    original = ROOT / from_relative
    if not original.is_file() or original.is_symlink():
        raise ValueError("Missing or unexpected source file: " + from_relative)
    target = staging / destination.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, target)
    target.chmod(0o755 if executable else 0o644)


def build(output=None):
    """Build, then publish atomically to a fresh path; never replace a file."""
    target = Path(output) if output is not None else ROOT / "dist" / DEB_NAME
    target = target.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError("Package already exists; refusing to replace: " + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gcdocs-deb-", dir=target.parent) as place:
        staging = Path(place) / "root"
        control = staging / "DEBIAN" / "control"
        control.parent.mkdir(parents=True, exist_ok=True)
        control.write_text(
            f"Package: {PACKAGE}\n"
            f"Version: {VERSION}\n"
            "Section: editors\n"
            "Priority: optional\n"
            "Architecture: all\n"
            "Maintainer: GoreeCloud <admin@goreecloud.com>\n"
            "Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0\n"
            "Description: Native local Documents GTK4 development preview\n"
            " This pre-release client needs a separately running local Documents\n"
            " service and an authorized token. It is not a stable product.\n",
            encoding="utf-8",
        )
        control.chmod(0o644)
        for filename in ("__init__.py", "cli.py", "linux.py"):
            copy_file(
                staging, "goreedocs/" + filename,
                "/usr/lib/goreecloud-documents/goreedocs/" + filename,
            )
        copy_file(
            staging, "packaging/linux/goreecloud-documents",
            "/usr/bin/goreecloud-documents", executable=True,
        )
        copy_file(
            staging, "packaging/linux/com.goreecloud.Documents.desktop",
            "/usr/share/applications/com.goreecloud.Documents.desktop",
        )
        copy_file(
            staging, "packaging/linux/goreecloud-documents.svg",
            "/usr/share/icons/hicolor/scalable/apps/goreecloud-documents.svg",
        )
        for src, dest in (
            ("LICENSE", "LICENSE"),
            ("packaging/linux/LICENSE.GC-UI", "LICENSE.GC-UI"),
            ("packaging/linux/ASSET_PROVENANCE.md", "ASSET_PROVENANCE.md"),
        ):
            copy_file(staging, src, "/usr/share/doc/goreecloud-documents/" + dest)
        candidate = Path(place) / DEB_NAME
        subprocess.run(
            ["dpkg-deb", "--build", "--root-owner-group", str(staging), str(candidate)],
            check=True,
        )
        # Source and output share the same filesystem. os.link is atomic and
        # will fail instead of overwriting another build's existing filename.
        os.link(candidate, target)
        return target


def main():
    try:
        print(build(sys.argv[1] if len(sys.argv) == 2 else None))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Package build failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
