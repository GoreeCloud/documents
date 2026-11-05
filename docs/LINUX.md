# GoreeCloud Documents — Linux GTK4 development client

**Status:** Native Linux UI source preview. Not packaged, visually accepted, runtime-certified, or released.

## Requirements

- Linux desktop with GTK 4 and Python GObject Introspection (PyGObject)
- Python 3.11 or newer
- A running **local** GoreeCloud Documents development server
- An authorized `GOREEDOCS_TOKEN` set in the launching process

On a Linux distribution with native GTK4 Python bindings, start the local service as described in the repository README, then open a terminal in the repository checkout and launch:

```sh
export GOREEDOCS_URL=http://127.0.0.1:8735
python3 -m goreedocs.linux
```

The client reads `GOREEDOCS_TOKEN` from the environment, as the existing CLI does. Do not put tokens into shell history or publicly readable files. If GTK4 bindings or a display server are unavailable, the client cannot launch. The source has no bundled installer or APK and cannot be represented as an installed Linux application.

## Features in this development slice

- Native `Gtk.Application` and `Gtk.ApplicationWindow`, with system widget styling and a limited GC UI Iris reference accent.
- Searchable, paginated document list, including upper-right format badges on thumbnails.
- Create and open documents, and manually save title, folder and UTF-8 Markdown body.
- Optimistic version checks through the existing REST API; a conflict is surfaced as an error rather than silently overwriting a concurrent edit.
- Unsaved-change protection when changing documents or closing the window; explicit Discard edits action.
- HTTP work runs in background worker threads; UI updates return to the GTK main loop.

The desktop client has **no standalone offline document store**, system integration package, per-user authentication dialog, native import/export dialogs, thumbnail image rendering, sharing controls, or established platform theme/accessibility acceptance. The web app has features not yet present in the Linux preview.

## Design and verification

The UI uses the canonical GC UI semantic intent: Canvas for the native window, Surface for reading and editing, and a bounded sidebar/navigation layer. Its accent and radii map to verified Iris reference values in `GoreeCloud/gc-ui`. A complete native token adapter, high-contrast audit, keyboard screen-reader test, light/dark visual review, installation/removal testing and screenshot-led acceptance remain outstanding.

The Python unit suite checks the REST transport contract and basic GTK4 wiring without importing GTK on CI. It **does not launch a graphical window**. Follow the repository's release gates before claiming any supported Linux distribution or stable package.

Because this native client calls `goreedocs.cli.call`, integrate and validate the security fix in draft PR #2 before productionizing or distributing it.
