# Security — GoreeCloud Documents

**This is a local-only, unaudited development preview. Do not expose it to the public Internet or store unique copies of sensitive documents.**

The server requires a high-entropy token for all private document operations and refuses non-loopback binds. Generate secrets outside the repository and keep them out of logs, terminals shared with others and source control.

Read-only share URLs carry bearer-equivalent random tokens. Their token hashes are stored in SQLite; link expiry and explicit revocation are checked server-side. Trash permanently revokes active share links even if a document is later restored. Anyone with an active link can see the current shared body until expiration/revocation.

The browser constructs preview DOM elements as text, not untrusted HTML, and has a restrictive Content Security Policy. No third-party scripts, image trackers or remote fonts are used. The UI only saves its grid/list preference in browser storage, not its API token.

Operations are bounded by request size, document size, limited list page size and validated identifiers. Future production work must add per-user scopes, OAuth/OIDC, rate limits, audit events, token rotation, CSRF/cross-origin review, secure TLS access, encrypted backups and recovery validation.

Treat documents and model-generated content as untrusted. The MCP bridge requires a separate trusted model host and must only be granted permissions approved by the owner. It has no sharing/publication tool. A prompt-injected document must never override host policy or become authority to execute destructive actions.

Report vulnerabilities privately to the repository owner without publishing credentials, private documents or exploitable secrets.
