# GoreeCloud Documents — Linux GTK4 development client

**Status:** Native GTK4 development-preview source is integrated into `main`. Disposable Ubuntu CI has passed source, GTK runtime, Debian package install/removal and upgrade/downgrade tests. No supported or Stable desktop release has been delivered.

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

## Native keyboard access

In the GTK4 preview, `Ctrl+N` creates a document, `Ctrl+S` saves current
edits, `Ctrl+F` focuses library search, `Ctrl+E` focuses the Markdown editor,
and `F5` refreshes the library. The new and save actions obey the existing
unsaved-change and pending-operation guards; a shortcut does not bypass
optimistic version checks. The native window owns these actions, so focus can
move between search results and the editor.

These shortcuts are supported at the source and virtual-display startup-test
level. Full screen-reader, alternative keyboard-layout, focus-order, and
high-contrast accessibility checks on an actual desktop remain outstanding.

## Design and verification

The UI uses the canonical GC UI semantic intent: Canvas for the native window, Surface for reading and editing, and a bounded sidebar/navigation layer. Its accent and radii map to verified Iris reference values in `GoreeCloud/gc-ui`. A complete native design-token adapter, high-contrast/screen-reader review, target-desktop visual acceptance, signed package custody and physical target-machine installation/upgrade/rollback still require validation. Disposable CI package lifecycle tests have already passed.

The Python test suite validates REST transport, in-memory token isolation, and the actual `DesktopAPI` against a real local `Service` instance (including authenticated create/list/read/save, version conflict rejection, and invalid credential handling). This verifies the client-to-service contract, not the GUI's visual and interactive behavior. Separate Xvfb CI tests start the GTK4 window and packaged launcher. A synthetic runtime regression also tests an invalid owner token, successful reconnect, native document selection, edit and Save against an isolated loopback SQLite service. These tests, plus disposable package upgrade and downgrade, have passed on hosted Linux CI. They do not establish a supported distribution or Stable package without actual target acceptance.

Because this native client calls `goreedocs.cli.call`, it includes the verified redirect-safe CLI source from merged PR #2. The portable Python service and all platform-specific acceptance criteria remain independent.

## Installed Debian GTK behavior acceptance

The Debian CI runner now exercises the **installed** `/usr/lib/goreecloud-documents/goreedocs/linux.py` and packaged `cli.py` through a synthetic loopback owner session, rather than only testing the checkout source and checking that an installed window opens. The test verifies rejection and recovery of an invalid owner token, a masked/cleared token entry, loading a synthetic private document, editing, explicit Save, and SQLite round-trip without credentials or owner data. The test script refuses a requested packaged path if it cannot verify the GTK module was loaded from that exact path. This is hosted-package runtime acceptance; physical package signing and normal persistent-desktop release acceptance remain separate.

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

The build tool refuses to overwrite an existing package. It explicitly
sets `0755` modes for directories **inside the assembled Debian archive**,
including the control directory, even when the operator uses hardened
`umask 077`; the temporary build parent remains owner-private. A
Linux regression verifies directory modes and no-overwrite under that umask.
It never installs the package or alters host application state. Disposable
Ubuntu CI runners are used for independent build, install, GTK4 launch and
uninstall smoke tests. On an authorized Zorin OS 18.1 laptop, the extracted
package's native Python GTK4 client also launched a real window in an isolated
X11 session without installing the `.deb` into the host OS.
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
