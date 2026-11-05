"""Native GTK4 client transport contract; no graphical display required for CI."""
import ast
from pathlib import Path
import unittest

from goreedocs.linux import DesktopAPI


class NativeLinuxContractTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake(path, method="GET", payload=None):
            self.calls.append((path, method, payload))
            return {"path": path, "method": method, "payload": payload}

        self.api = DesktopAPI(fake)

    def test_browse_query_and_pagination_encoding(self):
        result = self.api.list("family & notes", offset=60, limit=50)
        self.assertEqual(result["method"], "GET")
        self.assertIn("q=family+%26+notes", result["path"])
        self.assertIn("offset=60", result["path"])
        self.assertIn("limit=50", result["path"])

    def test_create_uses_native_format_and_existing_rest_api(self):
        result = self.api.create()
        self.assertEqual(result["path"], "/api/documents")
        self.assertEqual(result["method"], "POST")
        self.assertEqual(result["payload"]["format"], "gcdoc")
        self.assertEqual(result["payload"]["body"], "")

    def test_read_and_optimistic_save(self):
        doc = self.api.read("123-abc")
        self.assertEqual(doc["path"], "/api/documents/123-abc")
        saved = self.api.save("123-abc", 7, "Updated", "Family", "# 📄")
        self.assertEqual(saved["method"], "PATCH")
        self.assertEqual(saved["payload"], {
            "version": 7, "title": "Updated", "folder": "Family", "body": "# 📄",
        })

    def test_pygobject_is_only_required_when_gui_launches(self):
        import inspect
        from goreedocs import linux
        source = inspect.getsource(linux)
        tree = ast.parse(source)
        self.assertTrue(any(
            isinstance(node, ast.FunctionDef) and node.name == "main"
            for node in tree.body
        ))
        self.assertIn('gi.require_version("Gtk", "4.0")', source)
        self.assertIn('Gdk.Display.get_default()', source)
        self.assertIn('GLib.idle_add', source)
        self.assertIn('self.is_dirty()', source)
        self.assertIn('Gtk.Overlay()', source)
        self.assertIn('thumb.add_overlay(badge)', source)
        self.assertIn('self.listbox.set_activate_on_single_click(True)', source)
        self.assertIn('self.save_button.connect("clicked", self.save)', source)
        self.assertIn('self.connect("close-request", self.prevent_data_loss)', source)
        self.assertIn("Gtk.PasswordEntry()", source)
        self.assertIn('self.auth_entry.set_text("")', source)
        self.assertIn("session_request", source)
        self.assertIn('session["token"] = ""', source)
        self.assertIn("self.auth_strip.set_visible(True)", source)


if __name__ == "__main__":
    unittest.main()
