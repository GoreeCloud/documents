# Architecture and scope boundaries

**Single write path:** Browser, CLI and experimental local stdio MCP adapter all invoke the same authenticated REST API. No AI provider has direct access to the underlying SQLite file. AI hosts must be separately configured and authorized for tool calls.

**Persistence:** SQLite in WAL mode. Each document stores Markdown body, title, logical folder, stored format (gcdoc or md), favorite flag, revision/version and timestamps. Versions are snapshotted on each edit. Optimistic concurrency is checked within BEGIN IMMEDIATE transactions. Existing v0 databases migrate by adding format/favorite columns without replacing document IDs.

**Native format:** .gcdoc is an explicit UTF-8 JSON envelope containing Markdown. It is portable across hosts, deliberately not an opaque binary archive. Import creates a new record. Export preserves body and logical folder but does not claim to preserve server-generated IDs or revision history. See GCDOC_FORMAT.md.

**Browser:** GC UI semantic-role mapping; default Overview with stats, cards, and actions. Document cards show a format badge in the upper-right BEFORE opening. Grid/list choice persists as a local UI preference only. Sidebar contains folders and categories. Search and list pagination operate server-side; scrolling loads additional results. Markdown preview uses safe text nodes, not raw HTML.

**Access:** Loopback-only server with single-owner bearer token, no account system. Public read-only share tokens are random, hashed in the datastore, checked on each read and revocable; moving a file to Trash permanently revokes active shares.

**Security and operations gaps:** No OIDC, scoped tokens, per-user ACL, network TLS termination, encrypted recovery pipeline, formal audit logs, cross-device conflict merge, crash-safe browser drafts, production systemd service, rate-limiting, hardened distribution or complete mobile device testing. Treat the current release as local development only.

**Integration boundaries:** GoreeCloud Drive remains general file storage and sharing. GoreeCloud Markdown remains local editing. GoreeCloud Identity should provide future SSO; GoreeCloud Mesh may provide cross-service events. Do not copy Drive canonical documents here without verified source-of-truth mapping and explicit user action.

**Native roadmap:** An operating-system-native Linux GTK4 client and Android Kotlin/Compose application should reuse the documented REST/format contracts. A web app remains a web app and is not a native mobile release.

**Performance roadmap:** SQLite FTS search, formal paginated revision history, large-library accessibility, cache/ETag semantics, incremental thumbnails, local/offline draft sync, observability, backup/restore validation and concurrency simulations.
