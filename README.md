# GoreeCloud Documents

**GoreeCloud Documents** is an original, private-by-default document manager, reader, and editor with a single self-hosted backend for the browser, CLI, and authorized AI tools.

**Status: 0.1.0 development preview.** This repository contains code and tests; it is not a deployed, audited, Stable or production-ready document service. Do not use it as the only copy of irreplaceable information.

## Implemented today

- A polished, responsive GoreeCloud UI-inspired browser interface with an overview homepage, interactive document thumbnails, a visible format badge on the top right of each thumbnail, changeable default grid/list views, shortcuts, overview widgets and native scrolling.
- Sidebar navigation for Overview, All documents, Favorites, Recent, Trash, dynamic folders and file formats; search, sorting, auto-loading paginated results and a manual Load more action.
- A built-in Markdown editor with autosave, read/edit/split modes, logical folders, version history, conflict-safe editing, soft delete and recovery.
- A first-party **.gcdoc** file format with versioned JSON envelope and Markdown body, including import/export. Plain UTF-8 **.md** documents remain compatible. File type is stored as document metadata and shown before opening.
- One authenticated JSON REST API, a Python CLI, and a local experimental stdio MCP bridge for AI clients that permit tools.
- Read-only share URLs with expiration and explicit revocation. Trash permanently revokes any previously issued share links.
- SQLite persistence with a write-ahead log, snapshots per revision, and stale-update protection via required version checks.
- Development-only, owner-private SQLite online backups and isolated no-overwrite restores with integrity/schema checks and restored-share revocation. See [Recovery](docs/RECOVERY.md) for commands, security boundaries and release gates.

GoreeCloud Docs complements [GoreeCloud Drive](https://github.com/GoreeCloud/drive) (general files and sharing) and [GoreeCloud Markdown](https://github.com/GoreeCloud/markdown) (standalone local editing). These integrations are not yet connected. Native Linux GTK4 client and Android app are separate development milestones; the responsive browser is not an Android APK.

## Development quick start

Requires Python 3.11+ (no pip dependencies for the service). Node.js is optional for syntax checks.

1. In the repository root, generate a unique strong token and keep it out of source control:

       export GOREEDOCS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

2. Start the loopback-only service with a local development database:

       python3 -m goreedocs.server --host 127.0.0.1 --port 8735 --db ./data/documents.sqlite3

3. Open http://127.0.0.1:8735 in a browser, and enter the token from step 1. The token is held only in tab memory; the grid/list preference alone is saved locally.

4. In a separate shell with the same token set:

       export GOREEDOCS_URL=http://127.0.0.1:8735
       printf '# Privacy Policy\n\nDevelopment draft.\n' | python3 -m goreedocs.cli create --title "Privacy Policy" --folder "Policies" --format gcdoc --file -
       python3 -m goreedocs.cli list --search Privacy

The create command returns a new document ID and version. When updating, first GET the document and pass its version to the update operation. A stale version causes a conflict, not an overwrite.

## Native .gcdoc document format

The GoreeCloud DOC format is a UTF-8 JSON document with a v1 envelope: kind, schema_version, title, folder, format and body. The body is Markdown source, intentionally readable and portable. For Markdown-only interoperability, import or export .md. Format and folder are metadata; the backend does not treat them as arbitrary server-side filesystem paths.

**Governance boundary:** authoritative GoreeCloud project documents in Google Drive remain UTF-8 Markdown. Exporting a .gcdoc from this service does not replace, move, or rewrite an existing canonical Drive document. See [native format specification](docs/GCDOC_FORMAT.md).

## AI, API and CLI integration

The same REST backend supports the web client, CLI, and an experimental MCP stdio bridge. A trusted local MCP host can execute the module named goreedocs.mcp with the service URL and token in its process environment.

MCP tools currently cover list, read, create, update, history, read revision, trash and restore. They are intended for hosts such as Claude Desktop or other compatible model tools, **but host interoperability is not yet validated**. AI is not given sharing/publication capability by default.

Models do not get document access merely from knowing this repository. ChatGPT on the web and remote AI hosts require a separately configured, supported, authorized integration/gateway before they can write to this private loopback service. The present project does not provide such a hosted connector or public tunnel.

[API reference](docs/API.md) · [Architecture](docs/ARCHITECTURE.md) · [Security](SECURITY.md) · [MIPS and release gates](docs/MIPS.md)

## Verification

    python3 -m unittest discover -s tests -v
    python3 -m compileall -q goreedocs
    node --check web/app.js
    node --check web/share.js

These tests check storage rules, a request/response API, CLI/MCP commands, native-format round trips, migration behavior and UI source contracts. They do not represent complete native runtime testing, browser visual acceptance, vulnerability scanning, or production recovery testing.

## License

Original GoreeCloud source is MIT licensed (see LICENSE). No secrets, private documents or customer data belong in this public repository.
