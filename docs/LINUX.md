# GoreeCloud Documents — Linux GTK4 development client

**Status:** Native GTK4 source preview, with an experimental Debian package builder. Package build/install/uninstall tests are under review; this is not a stable or supported release.

## Requirements

- Linux desktop with GTK 4 and Python GObject Introspection (PyGObject)
- Python 3.11 or newer
- A running **local** GoreeCloud Documents development server
- An authorized Documents API owner token, supplied through the environment or the native masked token entry

On a Linux distribution with native GTK4 Python bindings, start the local service as described in the repository README, then open a terminal in the repository checkout and launch:

```sh
export GOREEDOCS_URL=http://127.0.0.1:8735
python3 -m goreedocs.linux
```

The client reads `GOREEDOCS_TOKEN` if supplied, but also shows a native password-masked owner-token entry when none is configured or when the server rejects a token. The entry clears after connection and the token is kept in process memory for that session only; there is no keyring or on-disk credential persistence. Do not put tokens in shell history or publicly readable files. If GTK4 bindings or a display server are unavailable, the client cannot launch. The optional Debian package below is a separate source-built, unshipped preview and does not itself establish desktop acceptance.

## Features in this development slice

- Native `Gtk.Application` and `Gtk.ApplicationWindow`, a password-masked in-memory connection flow, system widget styling and a limited GC UI Iris reference accent.
- Searchable, paginated document list, including upper-right format badges on thumbnails.
- Create and open documents, and manually save title, folder and UTF-8 Markdown body.
- Optimistic version checks through the existing REST API; a conflict is surfaced as an error rather than silently overwriting a concurrent edit.
- Unsaved-change protection when changing documents or closing the window; explicit Discard edits action.
- HTTP work runs in background worker threads; UI updates return to the GTK main loop.

The desktop client has **no standalone offline document store**, OS keyring integration, native import/export dialogs, thumbnail image rendering, sharing controls, or established platform theme/accessibility acceptance. An experimental Debian launcher and desktop-entry package exists, but has not been released and cannot solve these gaps. The web app has features not yet present in the Linux preview.

## Design and verification

The UI uses the canonical GC UI semantic intent: Canvas for the native window, Surface for reading and editing, and a bounded sidebar/navigation layer. Its accent and radii map to verified Iris reference values in `GoreeCloud/gc-ui`. A complete native token adapter, high-contrast audit, keyboard screen-reader test, light/dark visual review, installation/removal testing and screenshot-led acceptance remain outstanding.

The Python test suite validates REST transport, in-memory token isolation, and the actual `DesktopAPI` against a real local `Service` instance (including authenticated create/list/read/save, version conflict rejection, and invalid credential handling). This verifies the client-to-service contract, not the GUI's visual and interactive behavior. Separate Xvfb CI tests start the GTK4 window and the packaged launcher, both with and without a pre-provisioned token. Follow the repository's release gates before claiming any supported Linux distribution or stable package.

Because this native client calls `goreedocs.cli.call`, it includes the verified redirect-safe CLI source from merged PR #2. The portable Python service and all platform-specific acceptance criteria remain independent.

## Experimental Debian package build

The source tree includes a no-overwrite, offline `dpkg-deb` packager for
development-only Linux distribution testing:

```sh
python3 packaging/linux/build_deb.py
dpkg-deb --contents dist/goreecloud-documents_0.1.0~dev1_all.deb
```

The package includes only the minimum GTK4 client Python files, a launcher,
a `.desktop` entry and the official GC UI SVG mark with its Apache-2.0
license and provenance. It declares native runtime dependencies on Python
3.11+, `python3-gi` and `gir1.2-gtk-4.0`. It does **not** install or run
the Documents service, configure a gateway, migrate databases, run privileged
maintainer scripts, or store credentials.

The build tool refuses to overwrite an existing package. It never installs
the package or alters the host application state. Disposable Ubuntu CI runners
are used for independent build, install, GTK4 launch and uninstall smoke tests.
Passing them establishes only package mechanics on the tested environment.
Do not distribute this development package before security review, a native
token/session login flow, manual desktop quality checks, update/rollback review,
and acceptance for each target Linux distribution.

The installed launcher uses isolated Python imports so untrusted current
working directories, `PYTHONPATH` and user site-packages cannot replace the
packaged GTK code. Desktop-menu launches without an existing environment
`GOREEDOCS_TOKEN` now show an in-memory, masked native token prompt. This is
not GoreeCloud Identity integration or a replacement for secure token provisioning,
revocation and keyring-reviewed session handling.
