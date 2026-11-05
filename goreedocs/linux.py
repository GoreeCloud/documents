"""Native Linux GTK4 development client for the GoreeCloud Documents REST API.

GTK is imported only when launched: backend integration remains unit-testable
without a graphical display or PyGObject on CI.
"""
import os
from threading import Thread
from urllib.parse import quote, urlencode
import sys

from .cli import call


class DesktopAPI:
    """Small transport adapter. The service owns all document state."""

    def __init__(self, transport=None):
        self.transport = transport if transport is not None else call

    def list(self, query="", offset=0, limit=60):
        return self.transport("/api/documents?" + urlencode({
            "q": query, "offset": offset, "limit": limit,
            "sort": "updated", "direction": "desc",
        }))

    def read(self, doc_id):
        return self.transport("/api/documents/" + quote(doc_id, safe=""))

    def create(self):
        return self.transport("/api/documents", "POST", {
            "title": "Untitled document", "body": "", "folder": "",
            "format": "gcdoc",
        })

    def save(self, doc_id, version, title, folder, body):
        return self.transport("/api/documents/" + quote(doc_id, safe=""), "PATCH", {
            "version": version, "title": title, "folder": folder, "body": body,
        })


def main(argv=None):
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, Gio, GLib, Gtk, Pango
    except (ImportError, ValueError) as exc:
        print("GTK4 and its Python GObject bindings are required: " + str(exc),
              file=sys.stderr)
        return 2

    session = {"token": os.environ.get("GOREEDOCS_TOKEN", "")}

    def session_request(path, method="GET", payload=None):
        # The GUI token is kept in process memory, never copied to disk.
        return call(path, method, payload, token=session["token"])

    api = DesktopAPI(session_request)

    class DocumentsWindow(Gtk.ApplicationWindow):
        def __init__(self, application):
            super().__init__(application=application, title="GoreeCloud Documents")
            self.set_default_size(1160, 780)
            self.set_size_request(630, 450)
            self.busy = False
            self.refresh_pending = False
            self.search_timer = None
            self.documents = []
            self.current = None
            self.saved_fields = None
            self.filling = False
            self.rows = {}

            header = Gtk.HeaderBar()
            heading = Gtk.Label(label="GoreeCloud  /  Documents")
            heading.add_css_class("gc-heading")
            header.set_title_widget(heading)
            self.refresh_button = Gtk.Button(label="Refresh")
            self.refresh_button.connect("clicked", lambda *_: self.refresh(True))
            header.pack_start(self.refresh_button)
            self.discard_button = Gtk.Button(label="Discard edits")
            self.discard_button.connect("clicked", self.discard)
            header.pack_end(self.discard_button)
            self.save_button = Gtk.Button(label="Save")
            self.save_button.add_css_class("gc-primary")
            self.save_button.set_tooltip_text("Save document changes (Ctrl+S)")
            self.save_button.connect("clicked", self.save)
            header.pack_end(self.save_button)
            self.new_button = Gtk.Button(label="+ New")
            self.new_button.set_tooltip_text("Create a document (Ctrl+N)")
            self.new_button.connect("clicked", self.create)
            header.pack_end(self.new_button)
            self.set_titlebar(header)

            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.set_child(layout)
            self.auth_strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            self.auth_strip.add_css_class("gc-auth")
            token_label = Gtk.Label(label="_Owner API token", use_underline=True)
            self.auth_strip.append(token_label)
            self.auth_entry = Gtk.Entry()
            self.auth_entry.set_visibility(False)
            self.auth_entry.set_hexpand(True)
            self.auth_entry.set_placeholder_text("Paste authorized local document token")
            self.auth_entry.set_tooltip_text(
                "Credential is held only in this running client session, never saved."
            )
            token_label.set_mnemonic_widget(self.auth_entry)
            self.auth_entry.connect("activate", self.connect_session)
            self.auth_strip.append(self.auth_entry)
            connect_button = Gtk.Button(label="Connect")
            connect_button.connect("clicked", self.connect_session)
            self.auth_strip.append(connect_button)
            layout.append(self.auth_strip)
            split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
            split.set_position(355)
            split.set_wide_handle(True)
            split.set_vexpand(True)
            layout.append(split)

            sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            sidebar.add_css_class("gc-sidebar")
            self.search = Gtk.SearchEntry()
            self.search.set_placeholder_text("Search documents")
            self.search.set_tooltip_text("Search document titles, contents and folders (Ctrl+F)")
            self.search.connect("search-changed", self.search_changed)
            sidebar.append(self.search)
            self.results = Gtk.Label(label="Your documents")
            self.results.set_xalign(0)
            self.results.add_css_class("gc-section")
            sidebar.append(self.results)
            scroll = Gtk.ScrolledWindow()
            scroll.set_vexpand(True)
            self.listbox = Gtk.ListBox()
            self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            self.listbox.set_activate_on_single_click(True)
            self.listbox.add_css_class("gc-document-list")
            self.listbox.connect("row-activated", self.select_row)
            scroll.set_child(self.listbox)
            sidebar.append(scroll)
            self.load_more_button = Gtk.Button(label="Load more")
            self.load_more_button.connect("clicked", lambda *_: self.refresh(False))
            sidebar.append(self.load_more_button)
            split.set_start_child(sidebar)

            pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            pane.add_css_class("gc-editor")
            split.set_end_child(pane)
            self.document_name = Gtk.Label(label="Select a document or create a new one")
            self.document_name.add_css_class("gc-document-heading")
            self.document_name.set_xalign(0)
            self.document_name.set_wrap(True)
            pane.append(self.document_name)
            self.format_label = Gtk.Label(label="Local, private by default")
            self.format_label.add_css_class("gc-subtitle")
            self.format_label.set_xalign(0)
            pane.append(self.format_label)
            self.title_entry = Gtk.Entry()
            self.title_entry.set_placeholder_text("Document title")
            self.title_entry.set_tooltip_text("Document title")
            self.title_entry.connect("changed", self.edited)
            pane.append(self.title_entry)
            self.folder_entry = Gtk.Entry()
            self.folder_entry.set_placeholder_text("Folder (optional)")
            self.folder_entry.set_tooltip_text("Logical document folder")
            self.folder_entry.connect("changed", self.edited)
            pane.append(self.folder_entry)
            editor_scroll = Gtk.ScrolledWindow()
            editor_scroll.set_vexpand(True)
            editor_scroll.add_css_class("gc-paper")
            self.body_view = Gtk.TextView()
            self.body_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            self.body_view.set_left_margin(16)
            self.body_view.set_right_margin(16)
            self.body_view.set_top_margin(16)
            self.body_view.set_bottom_margin(16)
            self.body_view.set_monospace(True)
            self.body_view.get_buffer().connect("changed", self.edited)
            editor_scroll.set_child(self.body_view)
            pane.append(editor_scroll)
            self.notice = Gtk.Label(label="Connecting to local Documents service…")
            self.notice.set_xalign(0)
            self.notice.set_wrap(True)
            self.notice.add_css_class("gc-status")
            layout.append(self.notice)

            css = Gtk.CssProvider()
            # Values below map to the verified GC UI Iris reference palette and
            # 12/18px radii; OS-native text and surfaces retain the system theme.
            css.load_from_data(b"""
                .gc-heading { color: #5145d9; font-size: 18px; font-weight: 800; }
                .gc-auth { padding: 14px 20px; }
                .gc-auth entry { min-height: 44px; }
                .gc-sidebar { padding: 18px; }
                .gc-editor { padding: 24px; }
                .gc-section { font-size: 17px; font-weight: 700; }
                .gc-document-heading { font-size: 23px; font-weight: 750; }
                .gc-subtitle { opacity: .72; }
                .gc-status { padding: 12px 20px; opacity: .85; }
                .gc-paper { border-radius: 18px; border: 1px solid alpha(currentColor, .15); }
                button.gc-primary { background: #5145d9; color: white; border-radius: 12px; min-height: 44px; }
                .gc-document-list row { margin-bottom: 8px; border-radius: 12px; }
                .gc-card { padding: 9px; }
                .gc-thumbnail { border-radius: 12px; padding: 9px; min-width: 78px; min-height: 68px; background: #e8e6ff; }
                .gc-format { font-size: 9px; font-weight: 800; border-radius: 8px; padding: 3px 5px; background: #5145d9; color: white; }
                .gc-card-title { font-weight: 750; }
                .gc-card-detail { opacity: .74; font-size: 11px; }
            """)
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            self.install_keyboard_actions(application)
            self.connect("close-request", self.prevent_data_loss)
            self.set_editor_enabled(False)
            self.present()
            self.auth_strip.set_visible(not bool(session["token"]))
            self.new_button.set_sensitive(bool(session["token"]))
            self.refresh_button.set_sensitive(bool(session["token"]))
            if session["token"]:
                self.refresh(True)
            else:
                self.notice.set_text(
                    "Enter your local owner token to connect. It will not be saved."
                )
                self.auth_entry.grab_focus()

        def install_keyboard_actions(self, application):
            """Native window actions; GTK handles keyboard layouts and focus."""
            bindings = (
                ("new-document", ("<Primary>n",), self.create),
                ("save-document", ("<Primary>s",), self.save),
                ("search-documents", ("<Primary>f",), self.search.grab_focus),
                ("refresh-library", ("F5",), lambda: self.refresh(True)),
                ("focus-editor", ("<Primary>e",), self.body_view.grab_focus),
            )
            for name, shortcuts, handler in bindings:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda *_ignored, fn=handler: fn())
                self.add_action(action)
                application.set_accels_for_action("win." + name, list(shortcuts))

        def connect_session(self, *_):
            if self.busy:
                return
            entered = self.auth_entry.get_text().strip()
            if not entered:
                self.notice.set_text("A local Documents API token is required")
                return
            session["token"] = entered
            self.auth_entry.set_text("")
            self.auth_strip.set_visible(False)
            self.new_button.set_sensitive(True)
            self.refresh_button.set_sensitive(True)
            self.refresh(True)

        def set_editor_enabled(self, enabled):
            self.title_entry.set_sensitive(enabled)
            self.folder_entry.set_sensitive(enabled)
            self.body_view.set_sensitive(enabled)
            self.save_button.set_sensitive(enabled and not self.busy and self.is_dirty())
            self.discard_button.set_sensitive(enabled and not self.busy and self.is_dirty())

        def fields(self):
            buffer = self.body_view.get_buffer()
            return (
                self.title_entry.get_text(),
                self.folder_entry.get_text(),
                buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True),
            )

        def is_dirty(self):
            return self.current is not None and self.fields() != self.saved_fields

        def edited(self, *_):
            if self.filling:
                return
            self.set_editor_enabled(self.current is not None)
            if self.is_dirty():
                self.notice.set_text("Unsaved edits — Save or Discard before switching documents")

        def populate(self, doc):
            self.current = doc
            self.saved_fields = (doc["title"], doc["folder"], doc["body"])
            self.filling = True
            self.title_entry.set_text(doc["title"])
            self.folder_entry.set_text(doc["folder"])
            self.body_view.get_buffer().set_text(doc["body"])
            self.filling = False
            self.document_name.set_text(doc["title"])
            self.format_label.set_text(
                ("GC DOC" if doc.get("format") == "gcdoc" else "Markdown") +
                "   •   Version " + str(doc["version"])
            )
            self.set_editor_enabled(True)
            self.notice.set_text("Document ready — manually save changes")

        def worker(self, action, completed):
            if self.busy:
                self.notice.set_text("Another document operation is still running")
                return
            self.busy = True
            self.new_button.set_sensitive(False)
            self.refresh_button.set_sensitive(False)
            self.load_more_button.set_sensitive(False)
            self.set_editor_enabled(self.current is not None)
            self.notice.set_text("Working…")

            def run():
                try:
                    result = action()
                except Exception as error:
                    GLib.idle_add(self.failed, str(error))
                else:
                    GLib.idle_add(self.succeeded, completed, result)

            Thread(target=run, daemon=True).start()

        def finish(self):
            self.busy = False
            self.new_button.set_sensitive(bool(session["token"]))
            self.refresh_button.set_sensitive(bool(session["token"]))
            self.set_editor_enabled(self.current is not None)
            if self.refresh_pending:
                self.refresh_pending = False
                GLib.idle_add(self.refresh, True)

        def succeeded(self, completed, result):
            self.finish()
            completed(result)
            return False

        def failed(self, message):
            self.finish()
            if "authorization required" in message.casefold() or "401" in message:
                session["token"] = ""
                self.auth_strip.set_visible(True)
                self.new_button.set_sensitive(False)
                self.refresh_button.set_sensitive(False)
                self.notice.set_text("Authentication rejected. Enter an authorized owner token.")
                self.auth_entry.grab_focus()
            else:
                self.notice.set_text("Operation failed: " + message)
            return False

        def refresh(self, reset=True):
            if not session["token"]:
                self.auth_strip.set_visible(True)
                self.notice.set_text("Connect with your local owner token first")
                return False
            if self.busy:
                self.refresh_pending = True
                return False
            query = self.search.get_text()
            offset = 0 if reset else len(self.documents)

            def completed(response):
                if reset:
                    self.documents = []
                    self.rows = {}
                    while (row := self.listbox.get_row_at_index(0)) is not None:
                        self.listbox.remove(row)
                self.documents.extend(response["documents"])
                for doc in response["documents"]:
                    self.add_row(doc)
                self.results.set_text(str(response["total"]) + " documents")
                self.load_more_button.set_sensitive(response["has_more"])
                self.notice.set_text("Library loaded" if self.documents else "No matching documents")

            self.worker(lambda: api.list(query, offset), completed)
            return False

        def add_row(self, doc):
            row = Gtk.ListBoxRow()
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            content.add_css_class("gc-card")
            thumb = Gtk.Overlay()
            paper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            paper.add_css_class("gc-thumbnail")
            summary = Gtk.Label(label=(doc.get("excerpt") or "New page")[:54])
            summary.set_max_width_chars(18)
            summary.set_ellipsize(Pango.EllipsizeMode.END)
            summary.set_wrap(True)
            summary.set_valign(Gtk.Align.END)
            paper.append(summary)
            thumb.set_child(paper)
            badge = Gtk.Label(label="MD" if doc.get("format") == "md" else "GC DOC")
            badge.add_css_class("gc-format")
            badge.set_halign(Gtk.Align.END)
            badge.set_valign(Gtk.Align.START)
            thumb.add_overlay(badge)
            content.append(thumb)
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            details.set_valign(Gtk.Align.CENTER)
            title = Gtk.Label(label=doc["title"])
            title.set_xalign(0)
            title.set_max_width_chars(25)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.add_css_class("gc-card-title")
            details.append(title)
            folder = Gtk.Label(label=doc.get("folder") or "Unfiled")
            folder.set_xalign(0)
            folder.add_css_class("gc-card-detail")
            details.append(folder)
            content.append(details)
            row.set_child(content)
            self.rows[row] = doc["id"]
            self.listbox.append(row)

        def select_row(self, _listbox, row):
            if self.busy:
                return
            if self.is_dirty():
                self.notice.set_text("Save or Discard your unsaved edits first")
                return
            identifier = self.rows.get(row)
            if identifier:
                self.worker(lambda: api.read(identifier), self.populate)

        def create(self, *_):
            if self.busy or self.is_dirty():
                self.notice.set_text("Save or Discard unsaved edits first")
                return
            def completed(doc):
                self.populate(doc)
                self.refresh(True)
                self.title_entry.grab_focus()
                self.title_entry.select_region(0, -1)
            self.worker(api.create, completed)

        def save(self, *_):
            if self.busy or not self.is_dirty():
                return
            doc = self.current
            fields = self.fields()
            def completed(updated):
                # Do not discard typing made while the save request was in flight.
                self.current = updated
                self.saved_fields = (updated["title"], updated["folder"], updated["body"])
                self.format_label.set_text(
                    ("GC DOC" if updated.get("format") == "gcdoc" else "Markdown") +
                    "   •   Version " + str(updated["version"])
                )
                self.document_name.set_text(updated["title"])
                self.set_editor_enabled(True)
                self.notice.set_text(
                    "Saved; newer edits still pending" if self.is_dirty() else "All changes saved"
                )
                if not self.is_dirty():
                    self.refresh(True)
            self.worker(lambda: api.save(doc["id"], doc["version"], *fields), completed)

        def discard(self, *_):
            if self.current is not None and not self.busy:
                self.populate(self.current)

        def search_changed(self, *_):
            if self.search_timer is not None:
                GLib.source_remove(self.search_timer)
            self.search_timer = GLib.timeout_add(300, self.search_ready)

        def search_ready(self):
            self.search_timer = None
            self.refresh(True)
            return False

        def prevent_data_loss(self, *_):
            if self.busy or self.is_dirty():
                self.notice.set_text("Save or Discard edits, and finish pending operations before closing")
                return True
            return False

    app = Gtk.Application(application_id="com.goreecloud.Documents")
    app.connect("activate", lambda application: DocumentsWindow(application))
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
