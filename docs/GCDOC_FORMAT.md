# GoreeCloud DOC native format — v1

The portable, user-facing GoreeCloud document format has filename extension **.gcdoc** and MIME type **application/vnd.goreecloud.document+json**.

GCDOC v1 is a UTF-8 JSON object with these fields:

| Field | Type | Notes |
| --- | --- | --- |
| kind | string | Required literal goreecloud.document |
| schema_version | integer | Required literal 1 |
| title | string | Required on import; between 1 and 160 trimmed characters |
| body | string | Required UTF-8 Markdown content; at most 1 MiB |
| folder | string | Optional logical folder path, not a filesystem path |
| format | string | Informational literal gcdoc; import validates and stores native format |

Example valid content, as a JSON file:

    {
      "kind": "goreecloud.document",
      "schema_version": 1,
      "title": "Example",
      "body": "# Example\n\nText.",
      "folder": "Notes",
      "format": "gcdoc"
    }

This format is designed to be plain-text, diffable, easy to edit through APIs, and stable to parse. It is not a zipped or encrypted container. Text is Markdown; it is not a lossless rich-text layout engine and currently has no embedded media or attachment entries.

Import and export enforce the same maximum serialized native GCDOC package size on the Python service (the Markdown body limit of 1 MiB plus 4 KiB for package overhead). JSON escaping may make an otherwise valid Markdown body too large for a `.gcdoc` package; the service rejects that native export with HTTP 413 and suggests exporting the original Markdown (`.md`) instead. The document remains stored and unchanged. In the browser editor, an oversized native export offers a consent-based `.md` download instead; Markdown preserves text but not the native logical-folder metadata, and choosing the fallback does not change the saved document. The native Android codec's matching boundary is a separate, outstanding acceptance item; do not assume Android parity until its change and tests are verified.

Import validates schema identity/version, Unicode text, title and folder bounds. The imported document gets a NEW ID, a new v1 revision and an independent lifecycle. The portable envelope intentionally excludes API credentials, link capabilities, internal revision IDs and database metadata. Import of future schema versions is rejected until a reviewed migration exists.

Plain .md files may be imported, edited and exported without wrapper metadata. The library displays format as **GC DOC** or **MD** on the upper-right corner of thumbnails before opening the file.

The native file format is not the canonical editable source for GoreeCloud project governance documents, which remain Markdown under existing GoreeCloud Google Drive instructions. Export is explicit user action, not automatic migration.

Planned future compatible additions require schema versioning, published schema validation, independent import/export reference tests and security review. Preserve backward-readable v1 support.
