# Security — GoreeCloud Documents

**This is a local-only, unaudited development preview. Do not expose it to the public Internet or store unique copies of sensitive documents.**

The server requires a high-entropy token for all private document operations and refuses non-loopback binds. Generate secrets outside the repository and keep them out of logs, terminals shared with others and source control.

The CLI and experimental stdio MCP adapter share one REST transport. It accepts loopback HTTP or explicitly configured HTTPS endpoints, validates the complete URL authority, rejects embedded URL credentials and ambiguous URL suffixes, and **does not follow HTTP redirects or honor environment HTTP(S) proxies**. This prevents unintentional forwarding of document bearer tokens when an endpoint is misconfigured or a server responds with a redirect. Remote HTTPS still requires a separately authorized, correctly authenticated gateway; this client transport is not an identity system or network exposure authorization.

Read-only share URLs carry bearer-equivalent random tokens. Their token hashes are stored in SQLite; link expiry and explicit revocation are checked server-side. Trash permanently revokes active share links even if a document is later restored. Anyone with an active link can see the current shared body until expiration/revocation.

The browser constructs preview DOM elements as text, not untrusted HTML, and has a restrictive Content Security Policy. No third-party scripts, image trackers or remote fonts are used. The UI only saves its grid/list preference in browser storage, not its API token.

Operations are bounded by request size, document size, limited list page size and validated identifiers. Future production work must add per-user scopes, OAuth/OIDC, rate limits, audit events, token rotation, CSRF/cross-origin review, secure TLS access, encrypted backups and recovery validation.

Treat documents and model-generated content as untrusted. The MCP bridge requires a separate trusted model host and must only be granted permissions approved by the owner. It has no sharing/publication tool. A prompt-injected document must never override host policy or become authority to execute destructive actions.

**Backup and restore threat model:** The development recovery utility stores
unencrypted SQLite snapshots containing private documents and revision history.
It requires owner-private source files and a pre-existing owner-private backup
directory; it creates only new no-overwrite output files. Restored copies
revoke historical share links without modifying the live source database.
Backups require separate encrypted, access-controlled off-device custody,
retention, integrity checks, and restore testing. A passing SQLite integrity
check is not proof of disaster recovery readiness. See
[docs/RECOVERY.md](docs/RECOVERY.md) for exact commands and acceptance gates.

**CI supply-chain boundary:** For my Documents repository I pin third-party
and first-party GitHub Actions to their full, resolved Git commit SHA rather
than a movable version tag. These pins were resolved from the upstream
maintainers' published `v4`/`v5` tags and, for Gradle, its annotated
`v4.4.3` commit. Version labels remain in workflow comments for auditing.
A future dependency update must intentionally verify and review the new
upstream release and its resolved commit before changing a pin, and must pass
both Android and Documents workflows. SHA pinning improves reproducibility;
it is **not** a malware audit, provenance verification of every transitive
component, deployment approval, or a substitute for least-privilege CI tokens.

Report vulnerabilities privately to the repository owner without publishing credentials, private documents or exploitable secrets.
