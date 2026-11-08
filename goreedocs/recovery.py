"""Owner-private, no-overwrite SQLite backups and isolated restores.

The live SQLite database may be in WAL mode: use SQLite's online backup API,
never shutil.copyfile, to capture committed pages consistently.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from urllib.parse import quote


class RecoveryError(Exception):
    """Refuse an unsafe recovery operation."""


REQUIRED = {
    "documents": {"id", "title", "body", "folder", "version", "created_at",
                  "updated_at", "deleted_at", "format", "favorite"},
    "revisions": {"doc_id", "version", "title", "body", "folder", "created_at"},
    "shares": {"token_hash", "doc_id", "expires_at", "revoked_at", "created_at"},
}


def _private_file(path):
    path = Path(path).expanduser().absolute()
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise RecoveryError("Source database does not exist") from None
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RecoveryError("Source must be a regular owner-private file (chmod 600)")
    return path


def _new_destination(path):
    path = Path(path).expanduser().absolute()
    folder = path.parent
    if not folder.is_dir() or folder.stat().st_mode & 0o077:
        raise RecoveryError("Destination directory must exist and be owner-private (chmod 700)")
    if os.path.lexists(path):
        raise RecoveryError("Destination already exists; refusing to overwrite")
    return path


def _connect_readonly(path):
    # A read-only connection still observes uncheckpointed WAL pages.
    uri = "file:" + quote(str(path), safe="/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def _inspect(connection):
    try:
        check = connection.execute("PRAGMA integrity_check").fetchall()
        if check != [("ok",)]:
            raise RecoveryError("SQLite integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RecoveryError("SQLite foreign key check failed")
        for table, columns in REQUIRED.items():
            actual = {row[1] for row in connection.execute("PRAGMA table_info(" + table + ")")}
            if not columns.issubset(actual):
                raise RecoveryError("Missing required GoreeCloud Documents schema: " + table)
        return {
            "documents": connection.execute("SELECT count(*) FROM documents").fetchone()[0],
            "revisions": connection.execute("SELECT count(*) FROM revisions").fetchone()[0],
            "shares": connection.execute("SELECT count(*) FROM shares").fetchone()[0],
        }
    except sqlite3.DatabaseError:
        raise RecoveryError("Invalid or corrupted SQLite database") from None


def verify_database(path):
    """Verify a private database without creating or changing any files."""
    path = _private_file(path)
    connection = _connect_readonly(path)
    try:
        return _inspect(connection)
    finally:
        connection.close()


def _snapshot(source, destination, revoke_shares):
    source = _private_file(source)
    destination = _new_destination(destination)
    original = _connect_readonly(source)
    temporary = None
    try:
        _inspect(original)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".goreedocs-recovery-", suffix=".sqlite", dir=destination.parent
        )
        os.close(descriptor)
        copy = sqlite3.connect(temporary, timeout=10)
        try:
            original.backup(copy, pages=256, sleep=0.01)
            mode = copy.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if mode.lower() != "delete":
                raise RecoveryError("Could not finalize a single-file SQLite snapshot")
            if revoke_shares:
                # Restoring older state must never reactivate a previously revoked link.
                stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                copy.execute(
                    "UPDATE shares SET revoked_at=? WHERE revoked_at IS NULL", (stamp,)
                )
                copy.commit()
            details = _inspect(copy)
        finally:
            copy.close()
        # The database is self-contained; no WAL sidecars may be required to restore.
        if os.path.exists(temporary + "-wal") or os.path.exists(temporary + "-shm"):
            raise RecoveryError("Snapshot still has SQLite WAL sidecars")
        fd = os.open(temporary, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        # Same-directory hard link is atomic and fails if another writer created
        # the name; unlike os.replace, it never overwrites an existing backup.
        os.link(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {"output": str(destination), **details,
                "share_links_revoked": bool(revoke_shares)}
    except sqlite3.DatabaseError:
        raise RecoveryError("SQLite backup or restore failed") from None
    finally:
        original.close()
        if temporary is not None:
            for name in (temporary, temporary + "-wal", temporary + "-shm"):
                try:
                    os.unlink(name)
                except FileNotFoundError:
                    pass


def backup_database(database, output):
    """Create a consistent backup while the service can continue serving writes."""
    return _snapshot(database, output, revoke_shares=False)


def restore_database(backup, output):
    """Recover into a NEW database path, revoking any historical share links."""
    return _snapshot(backup, output, revoke_shares=True)


def main():
    parser = argparse.ArgumentParser(
        prog="python -m goreedocs.recovery",
        description="Owner-private backup, validation and isolated restore; never overwrite",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Online snapshot of a live database")
    backup.add_argument("--db", required=True)
    backup.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="Read-only SQLite integrity/schema check")
    verify.add_argument("--db", required=True)
    restore = commands.add_parser("restore", help="Restore into a new, unused database path")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            outcome = backup_database(args.db, args.output)
        elif args.command == "restore":
            outcome = restore_database(args.backup, args.output)
        else:
            outcome = verify_database(args.db)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
    except (RecoveryError, OSError, sqlite3.Error) as exc:
        parser.exit(1, "Recovery refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
