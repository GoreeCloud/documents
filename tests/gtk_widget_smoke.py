"""GTK4 synthetic owner-login and save lifecycle on an isolated X11 display.

Only a disposable SQLite database, loopback service and in-memory test token
are used. Run with xvfb-run on a host with system GTK4/PyGObject installed.
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback

# Optional packaged-client contract: import GTK/CLI modules from the
# actual installed .deb payload while using the checkout's server only as
# synthetic loopback test infrastructure. This must not test source GTK
# accidentally while claiming that a packaged build was verified.
PACKAGE_ROOT = os.environ.get("GCDOCS_TEST_CLIENT_DIR")
if PACKAGE_ROOT:
    client_root = Path(PACKAGE_ROOT).resolve()
    if not (client_root / "goreedocs/linux.py").is_file():
        raise RuntimeError("No installed GTK client at requested package path")
    sys.path.insert(0, str(client_root))
    import goreedocs
    if Path(goreedocs.__file__).resolve() != client_root / "goreedocs/__init__.py":
        raise RuntimeError("GTK smoke imported a non-packaged goreedocs module")
    goreedocs.__path__.append(str(Path(__file__).resolve().parents[1] / "goreedocs"))

from goreedocs import linux
from goreedocs.server import Service, Store

if PACKAGE_ROOT:
    if Path(linux.__file__).resolve() != client_root / "goreedocs/linux.py":
        raise RuntimeError("Native GTK module was not loaded from packaged payload")
    print("PACKAGED_GTK_MODULE=" + str(linux.__file__), flush=True)

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

os.environ.pop("GOREEDOCS_TOKEN", None)
temporary = tempfile.TemporaryDirectory(prefix="gcdocs-gtk-qa-")
store = Store(Path(temporary.name) / "documents.sqlite3")
created = store.create({
    "title": "Synthetic GTK document",
    "body": "# Initial",
    "folder": "Test/Synthetic",
    "format": "gcdoc",
})
synthetic_token = "synthetic-test-only-" + "q" * 40
server = Service(("127.0.0.1", 0), store, synthetic_token)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ["GOREEDOCS_URL"] = (
    "http://127.0.0.1:" + str(server.server_address[1])
)

deadline = time.monotonic() + 35
phase = 0
passed = False


def current_window():
    windows = Gtk.Window.get_toplevels()
    for index in range(windows.get_n_items()):
        item = windows.get_item(index)
        if hasattr(item, "auth_entry") and hasattr(item, "connect_session"):
            return item
    return None


def inspect():
    global phase, passed
    try:
        if time.monotonic() > deadline:
            raise TimeoutError("GTK lifecycle phase timed out: " + str(phase))
        ui = current_window()
        if ui is None:
            return True

        if phase == 0:
            assert ui.auth_strip.get_visible()
            assert not ui.auth_entry.get_visibility(), "Owner token must be masked"
            ui.auth_entry.set_text("invalid-synthetic-token")
            ui.connect_session()
            phase = 1
        elif phase == 1:
            if ui.busy or "Authentication rejected" not in ui.notice.get_text():
                return True
            assert ui.auth_entry.get_text() == "", "Token entry must be cleared"
            ui.auth_entry.set_text(synthetic_token)
            ui.connect_session()
            phase = 2
        elif phase == 2:
            if ui.busy or ui.auth_strip.get_visible() or len(ui.documents) != 1:
                return True
            assert ui.auth_entry.get_text() == "", "No token in visible field"
            print("PASS GTK rejected token, recovered, loaded library", flush=True)
            row = ui.listbox.get_row_at_index(0)
            assert row is not None
            ui.select_row(ui.listbox, row)
            phase = 3
        elif phase == 3:
            if ui.busy or ui.current is None:
                return True
            assert ui.current["id"] == created["id"]
            ui.title_entry.set_text("Synthetic edited via GTK")
            ui.body_view.get_buffer().set_text("# Updated through native editor")
            assert ui.is_dirty()
            ui.save()
            phase = 4
        elif phase == 4:
            if ui.busy or ui.current is None or ui.current["version"] < 2:
                return True
            saved = store.get(created["id"])
            assert saved["title"] == "Synthetic edited via GTK"
            assert saved["body"] == "# Updated through native editor"
            assert not ui.is_dirty()
            passed = True
            print("PASS GTK editor save and SQLite round-trip", flush=True)
            Gtk.Application.get_default().quit()
            return False
    except Exception:
        traceback.print_exc()
        Gtk.Application.get_default().quit()
        return False
    return True


GLib.timeout_add(180, inspect)
try:
    linux.main(["goreecloud-documents-synthetic-qa"])
finally:
    server.shutdown()
    server.server_close()
    temporary.cleanup()

assert passed, "GTK synthetic authentication/save acceptance failed"
print("GTK_SYNTHETIC_ACCEPTANCE=PASS", flush=True)
