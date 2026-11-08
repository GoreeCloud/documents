# HTTP API — developer preview

Default URL: http://127.0.0.1:8735

All API requests except /api/public/{share_token} require a Bearer token in the Authorization header. Body-bearing writes require Content-Type: application/json. Responses are JSON objects; errors contain an error string and an appropriate status code.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | Process liveness |
| GET | /api/overview | Total, favorites, trash, last-week counts and folder breakdown |
| GET | /api/documents | Filtered/paginated document thumbnails and metadata |
| POST | /api/documents | Create document with title/body/folder/format/favorite |
| POST | /api/documents/import | Import filename and full content for .gcdoc or .md |
| GET | /api/documents/{id} | Read current document |
| PATCH | /api/documents/{id} | Edit partial fields with required current version |
| GET | /api/documents/{id}/export | Export current file as JSON envelope containing filename/content/MIME |
| POST | /api/documents/{id}/trash | Move to trash and revoke existing share links |
| POST | /api/documents/{id}/restore | Restore a soft-deleted document |
| GET | /api/documents/{id}/revisions | List revisions (most recent first) |
| GET | /api/documents/{id}/revisions/{number} | Read historical Markdown snapshot |
| POST | /api/documents/{id}/revisions/{number} | Revert historical content into a new revision, with current version |
| POST | /api/documents/{id}/share | Create expiring read-only capability link, hours 1–168 |
| DELETE | /api/shares/{token} | Revoke existing capability link |
| GET | /api/public/{token} | Read current body/title with a valid unexpired share capability |

**Import request-size boundary (development preview):** The serialized `.gcdoc` or `.md` file content itself remains limited to `MAX_JSON = 1,052,672` UTF-8 bytes, and the Markdown body remains limited to 1 MiB. Because the `POST /api/documents/import` request wraps that file content inside another JSON object, escaping can expand the HTTP body. This import route alone permits up to `6 * MAX_JSON + 4096` transport bytes, while `Store.import_file` independently rejects oversized native file content. Other authenticated write endpoints retain the original `MAX_JSON` request ceiling. This is a bounded developer-preview change pending dedicated HTTP regressions and resource-impact review; it is not a promise of unrestricted uploads.

List query parameters: q (case-insensitive text), trash=1, favorites=1, recent=1, folder (exact folder or children), format (gcdoc or md), sort (updated, created, title), direction (asc or desc), limit (1–100; default 60) and offset (0–1,000,000). Result includes documents, total, offset, limit and has_more.

Create example:

    curl --fail-with-body http://127.0.0.1:8735/api/documents \
      -H "Authorization: Bearer $GOREEDOCS_TOKEN" -H "Content-Type: application/json" \
      -d '{"title":"Privacy Policy draft","body":"# Privacy Policy\n\nDraft only.","folder":"Policies","format":"gcdoc"}'

Edit example (check GET version before sending):

    curl --fail-with-body -X PATCH http://127.0.0.1:8735/api/documents/DOCUMENT_ID \
      -H "Authorization: Bearer $GOREEDOCS_TOKEN" -H "Content-Type: application/json" \
      -d '{"version":1,"body":"# Revised content"}'

HTTP 409 means concurrent edit conflict: never blindly overwrite. HTTP 428 indicates a missing/invalid version. Document max body is 1 MiB. No public deletion endpoint exists; Trash is reversible. Never log share capabilities or expose tokens in URLs to external analytics.
