# GoreeCloud Documents — local SQLite backup and recovery

**Status: development preview, not a production-ready backup service.** These
commands operate only on an explicitly supplied local SQLite database. They do
not configure automatic schedules, remote storage, deployment, or cloud recovery.
Keep independent, tested, encrypted off-device backups of important data.

## Important boundaries

- The active Documents server uses SQLite **WAL mode**. The recovery utility
  uses the SQLite online backup API; a raw copy of only the live `.sqlite3`
  file can omit committed WAL changes and must not be treated as a backup.
- Source databases and backup files must be private regular files (permissions
  `0600`). The **destination directory must already exist** and must be
  owner-private (permissions `0700`). The recovery utility also rejects
  a **direct symbolic link** in the selected destination directory path,
  even when the symlink target itself has private permissions; it does not
  guarantee race-free protection against another process modifying ancestor
  directories concurrently.
- The destination filename must **not exist**. Backup/restore refuses to
  overwrite an existing file, including a symlink. Never choose a live database
  filename as the output of a restore.
- Neither backup nor restore copies API bearer credentials into a portable
  `.gcdoc` file, but **the raw database backup contains private document
  bodies, metadata, revisions and hashed sharing capabilities**. Treat it as
  highly sensitive; the utility does not encrypt it.
- Restore creates an **isolated new database**. It explicitly revokes any
  historical share links within the restored copy, so old link tokens cannot
  reactivate on cutover. It does not change or revoke shares in the existing
  live database or the backup source.

## Make an online backup

Choose an existing, private source database. The example below uses the local
development database from the repository quickstart. Run the commands as the
same authorized operating-system user that owns the database.

```sh
umask 077
mkdir -p ./data/private-backups
chmod 700 ./data/private-backups

python3 -m goreedocs.recovery verify --db ./data/documents.sqlite3
python3 -m goreedocs.recovery backup \
  --db ./data/documents.sqlite3 \
  --output ./data/private-backups/documents-2026-11-05.sqlite3
python3 -m goreedocs.recovery verify \
  --db ./data/private-backups/documents-2026-11-05.sqlite3
```

The backup command produces a new private, self-contained SQLite database;
the online SQLite operation includes committed WAL changes. The destination
name is illustrative: select a fresh filename on every backup. If the backup
or verification fails, **do not delete the live source** or interpret an
incomplete file as a good backup. Inspect the failure and any partially
published destination before attempting a new, uniquely named backup.

The `verify` command checks SQLite integrity, foreign-key references,
required table columns and document/revision/share counts. These checks do
not prove every Markdown document is semantically correct, that a backup can
be decrypted after off-device archiving, or that it meets disaster-recovery
retention requirements.

## Rehearse an isolated restore

```sh
python3 -m goreedocs.recovery restore \
  --backup ./data/private-backups/documents-2026-11-05.sqlite3 \
  --output ./data/private-backups/restore-rehearsal.sqlite3
python3 -m goreedocs.recovery verify \
  --db ./data/private-backups/restore-rehearsal.sqlite3
```

The restore operation leaves the live database untouched. Confirm recovered
document and revision content, access permissions, and the expected number
of records in an **isolated test environment** before considering any live
recovery. Do not point two running Documents services at the same mutable
database. Any future production cutover requires an explicit outage plan,
verified backup, owner authorization, audited credentials and a rollback.

## Synthetic encrypted off-device rehearsal — November 7, 2026

For my GoreeCloud Documents recovery workflow, I require **restorable,
owner-private backups** and controlled off-device custody, not merely an
unencrypted copy of a live SQLite file. The recovery CLI currently produces
a private **unencrypted** SQLite snapshot; encryption and off-device storage
remain separately configured operator responsibilities.

An authorized **synthetic-data-only** rehearsal on November 7, 2026 used
two distinct connected machines. A disposable local Documents database
was backed up through the SQLite online-backup API, gzip-compressed and
encrypted with OpenSSL CMS (AES-256-CBC content encryption using a
recipient's ephemeral RSA certificate). Only the encrypted payload was
transferred; the recipient's private key remained on the destination.
The destination decrypted the payload, verified SHA-256 parity with the
source snapshot, restored to a **new** SQLite path, confirmed document
content, and confirmed active historical shares were revoked in the
restored copy while original shares remained unchanged.

The reproducible `tests/test_recovery_encrypted_transport.py` exercises
the same synthetic CMS encryption/decryption and isolated restore checks
without requiring any connected accounts, real credentials, or network
access. It requires the OpenSSL CLI; it skips on systems where OpenSSL
is unavailable. This test is **not** an encrypted backup product feature.

**Encryption integrity boundary:** The synthetic CMS exercise uses AES-256-CBC and an independently verified source SHA-256 digest. CBC is **not authenticated encryption**. Verifying a checksum obtained through an untrusted channel is insufficient to establish ciphertext authenticity; a production workflow needs authenticated encryption or a trusted signed manifest, verified recipients and key management. The additional negative regression tests refuse a mismatched recipient or malformed CMS envelope, but do not prove detection of arbitrary ciphertext modifications.

**Outstanding operational acceptance:** authenticate and pin intended
recipients; verify trustworthy key custody, expiry, rotation and
revocation; use appropriate approved cryptography and integrity checks;
define encrypted off-device retention, recovery-time objectives and
recovery-point objectives; test real host/disk interruption, loss of the
source computer, key-loss scenarios, and an audited restoration/rollback.
Neither this synthetic exercise nor the automated test authorizes
production backup scheduling, live database replacement, or a Stable claim.

## Validation and limitations

The unit suite covers document history, format preservation, isolation from
later source writes, historical share revocation on restore, private modes,
corrupt inputs, no-overwrite behavior, active WAL readers and simulated
publication I/O failure. The checks run on temporary disposable test files
only. Real interruption, low-disk, cross-filesystem and operational restore
acceptance are separate release gates.

This utility does **not** schedule backups, rotate or purge old copies,
monitor replication, validate off-device recovery, manage encryption keys,
or guarantee recovery after an arbitrary disk or host failure. Avoid
automating production cutovers or deleting any source based on these
development tests alone.
