"use strict";
const $ = id => document.getElementById(id);
let token = "", current = null, dirty = false, saving = false, halted = false, timer = null;
let category = "overview", folderFilter = "", query = "", sortKey = "updated", direction = "desc";
let documents = [], nextOffset = 0, hasMore = false, total = 0, loading = false, requestSeq = 0;
let view = "grid";
try { if (localStorage.getItem("gcdocs:default-view") === "list") view = "list"; } catch (_) {}
const status = text => { $("status").textContent = text; };

async function api(path, options = {}) {
  const headers = {"Authorization": "Bearer " + token, "Accept": "application/json"};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method: options.method || "GET", headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body), cache: "no-store"
  });
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data.error || "Request failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderMarkdown(text, target) {
  target.replaceChildren();
  let inCode = false, pre = null;
  for (const line of text.split("\n")) {
    if (/^\x60{3}/.test(line)) {
      inCode = !inCode;
      if (inCode) { pre = el("pre", ""); target.append(pre); }
      continue;
    }
    if (inCode) { pre.textContent += line + "\n"; continue; }
    let node, value = line;
    if (/^#{1,6} /.test(line)) {
      const n = line.match(/^#+/)[0].length;
      node = el("h" + n);
      value = line.slice(n + 1);
    } else if (/^[-*] /.test(line)) {
      node = el("p", undefined, "bullet");
      value = "•  " + line.slice(2);
    } else if (/^> /.test(line)) {
      node = el("blockquote");
      value = line.slice(2);
    } else if (/^---+$/.test(line.trim())) {
      node = el("hr");
      value = "";
    } else {
      node = el("p", undefined, line.trim() ? "" : "blank");
    }
    node.textContent = value;
    target.append(node);
  }
}

function formatName(fmt) { return fmt === "md" ? "MD" : "GC DOC"; }
function dateDisplay(iso) {
  try { return new Date(iso).toLocaleDateString(undefined, {month: "short", day: "numeric", year: "numeric"}); }
  catch (_) { return iso; }
}

function showDocument(doc) {
  current = doc;
  dirty = false;
  halted = false;
  $("library").hidden = true;
  $("editor").hidden = false;
  $("title").value = doc.title;
  $("body").value = doc.body;
  $("folder").value = doc.folder;
  $("version-badge").textContent = "Version " + doc.version;
  $("format-badge").textContent = formatName(doc.format);
  $("crumb").textContent = doc.title;
  $("remove").textContent = doc.deleted_at ? "Restore" : "Trash";
  $("favorite-toggle").textContent = doc.favorite ? "★" : "☆";
  for (const id of ["back", "favorite-toggle", "history", "share", "export", "remove"]) {
    $(id).hidden = false;
  }
  for (const id of ["history", "share", "export", "remove", "favorite-toggle"]) {
    $(id).disabled = false;
  }
  $("share").disabled = !!doc.deleted_at;
  $("favorite-toggle").disabled = !!doc.deleted_at;
  for (const id of ["title", "body", "folder"]) $(id).disabled = !!doc.deleted_at;
  renderMarkdown(doc.body, $("preview"));
  $("editor").scrollTop = 0;
  status(doc.deleted_at ? "In trash · Read only" : "All changes saved");
}

function leaveEditor() {
  if (!canLeave()) return;
  clearTimeout(timer);
  current = null; dirty = false; halted = false;
  $("editor").hidden = true; $("library").hidden = false;
  for (const id of ["back", "favorite-toggle", "history", "share", "export", "remove"]) $(id).hidden = true;
  $("crumb").textContent = categoryLabel();
  status("Ready");
  loadDocuments(true).catch(e => status(e.message));
}

function canLeave() { return !dirty || confirm("Unsaved changes remain. Leave without saving?"); }

async function openDocument(id) {
  if (current?.id === id || !canLeave()) return;
  clearTimeout(timer);
  try {
    const doc = await api("/api/documents/" + encodeURIComponent(id) + (category === "trash" ? "?trash=1" : ""));
    showDocument(doc);
  } catch (e) { status(e.message); }
}

async function createDocument() {
  if (!canLeave()) return;
  clearTimeout(timer);
  try {
    const doc = await api("/api/documents", {method: "POST",
      body: {title: "Untitled document", body: "", folder: "", format: "gcdoc"}});
    showDocument(doc);
    $("title").focus();
    $("title").select();
    await updateOverview();
  } catch (e) { status(e.message); }
}

function edited() {
  if (!current || current.deleted_at) return;
  dirty = true;
  status("Unsaved changes");
  renderMarkdown($("body").value, $("preview"));
  clearTimeout(timer);
  if (!halted) timer = setTimeout(save, 850);
}

async function save() {
  if (!dirty || saving || !current || halted) return;
  const id = current.id;
  const payload = {title: $("title").value, body: $("body").value,
    folder: $("folder").value, version: current.version};
  saving = true;
  status("Saving…");
  try {
    const doc = await api("/api/documents/" + id, {method: "PATCH", body: payload});
    current = doc;
    $("version-badge").textContent = "Version " + doc.version;
    $("crumb").textContent = doc.title;
    dirty = ["title", "body", "folder"].some(k => $(k).value !== doc[k]);
    status(dirty ? "More changes to save…" : "All changes saved");
  } catch (e) {
    if (e.status === 409) {
      halted = true;
      status("Edit conflict — copy your changes, then reopen");
    } else status("Save failed — " + e.message);
  } finally {
    saving = false;
    if (dirty && !halted) { clearTimeout(timer); timer = setTimeout(save, 2000); }
  }
}

async function updateOverview() {
  const data = await api("/api/overview");
  for (const [id, value] of [["stat-total", data.total], ["stat-favorites", data.favorites],
    ["stat-recent", data.recent], ["stat-trash", data.trash], ["count", data.total]]) {
    $(id).textContent = String(value);
  }
  const nav = $("folders-nav"); nav.replaceChildren();
  if (!data.folders.length) nav.append(el("p", "No folders yet", "list-empty"));
  for (const folder of data.folders) {
    const button = el("button", undefined, "nav");
    const name = el("span", "⌑  " + folder.name, "folder-name");
    const count = el("span", folder.count, "nav-count");
    button.append(name, count);
    button.classList.toggle("active", category === "folder" && folderFilter === folder.name);
    button.setAttribute("aria-current", category === "folder" && folderFilter === folder.name ? "page" : "false");
    button.onclick = () => selectCategory("folder", folder.name);
    nav.append(button);
  }
}

function categoryLabel() {
  if (category === "folder") return folderFilter;
  const names = {overview: "Overview", all: "All documents", favorites: "Favorites",
    recent: "Recent", trash: "Trash", gcdoc: "GoreeCloud DOC", md: "Markdown"};
  return names[category] || "Documents";
}

function navState() {
  for (const id of ["overview", "all", "favorites", "recent", "trash", "format-gcdoc", "format-md"]) {
    const active = id === category || (id === "format-" + category);
    $(id).classList.toggle("active", active);
    $(id).setAttribute("aria-current", active ? "page" : "false");
  }
  for (const b of $("folders-nav").querySelectorAll("button")) {
    const name = b.querySelector(".folder-name")?.textContent.slice(3);
    const selected = category === "folder" && name === folderFilter;
    b.classList.toggle("active", selected);
    b.setAttribute("aria-current", selected ? "page" : "false");
  }
  $("home-header").hidden = category !== "overview";
  $("widgets").hidden = category !== "overview";
  $("shortcuts").hidden = category !== "overview";
  $("section-title").textContent = category === "overview" ? "Your documents" : categoryLabel();
  $("crumb").textContent = categoryLabel();
}

function selectCategory(next, folder = "") {
  if (!$("editor").hidden && !canLeave()) return;
  category = next; folderFilter = folder;
  if (!$("editor").hidden) {
    current = null; dirty = false; halted = false; $("editor").hidden = true; $("library").hidden = false;
    for (const id of ["back", "favorite-toggle", "history", "share", "export", "remove"]) $(id).hidden = true;
  }
  navState();
  $("library").scrollTop = 0;
  loadDocuments(true).catch(e => status(e.message));
}

function setView(next) {
  view = next;
  $("cards").className = "cards " + view + "-view";
  for (const name of ["grid", "list"]) {
    const button = $("view-" + name);
    button.classList.toggle("selected", name === view);
    button.setAttribute("aria-pressed", String(name === view));
  }
  try { localStorage.setItem("gcdocs:default-view", view); } catch (_) {}
}

function buildCard(doc) {
  const card = el("article", undefined, "doc-card");
  const main = el("button", undefined, "card-main");
  main.setAttribute("aria-label", "Open " + doc.title + ", " + formatName(doc.format));
  main.onclick = () => openDocument(doc.id);
  const thumb = el("div", undefined, "doc-thumb");
  const badge = el("span", formatName(doc.format), "thumb-format " + (doc.format === "md" ? "markdown" : "native"));
  const paper = el("div", undefined, "thumb-paper");
  const type = el("span", "GoreeCloud / Documents", "paper-overline");
  const paperTitle = el("strong", doc.title, "paper-title");
  const snippet = el("p", doc.excerpt || "A new page full of possibility.", "paper-snippet");
  const line1 = el("div", undefined, "paper-line");
  const line2 = el("div", undefined, "paper-line short");
  paper.append(type, paperTitle, snippet, line1, line2);
  thumb.append(paper, badge);
  const details = el("div", undefined, "card-details");
  const title = el("strong", doc.title, "card-title");
  const detail = el("span", (doc.folder || "Unfiled") + " · " + dateDisplay(doc.updated_at), "card-subtitle");
  details.append(title, detail);
  main.append(thumb, details); card.append(main);
  if (!doc.deleted_at) {
    const fav = el("button", doc.favorite ? "★" : "☆", "fav-button");
    fav.setAttribute("aria-label", doc.favorite ? "Remove favorite " + doc.title : "Favorite " + doc.title);
    fav.onclick = () => toggleFavorite(doc);
    card.append(fav);
  }
  return card;
}

async function toggleFavorite(doc = current) {
  if (!doc) return;
  if (current?.id === doc.id && dirty) { status("Save changes before favoriting"); return; }
  try {
    const updated = await api("/api/documents/" + doc.id, {
      method: "PATCH", body: {version: doc.version, favorite: !Boolean(doc.favorite)}
    });
    if (current?.id === doc.id) showDocument(updated);
    await updateOverview();
    if ($("editor").hidden) await loadDocuments(true);
    status(updated.favorite ? "Added to favorites" : "Removed from favorites");
  } catch (e) { status(e.message + (e.status === 409 ? " — refresh library" : "")); }
}

async function loadDocuments(reset = true) {
  if (loading && !reset) return;
  const seq = ++requestSeq;
  loading = true;
  const offset = reset ? 0 : nextOffset;
  const params = new URLSearchParams({
    q: query, offset: String(offset), limit: "48",
    trash: category === "trash" ? "1" : "0",
    favorites: category === "favorites" ? "1" : "0",
    recent: category === "recent" ? "1" : "0",
    folder: category === "folder" ? folderFilter : "",
    format: category === "md" || category === "gcdoc" ? category : "",
    sort: sortKey, direction
  });
  $("load-more").disabled = true;
  try {
    const data = await api("/api/documents?" + params);
    if (seq !== requestSeq) return;
    if (reset) { documents = []; $("cards").replaceChildren(); }
    documents.push(...data.documents);
    const box = $("cards");
    for (const doc of data.documents) box.append(buildCard(doc));
    nextOffset = data.offset + data.documents.length;
    hasMore = data.has_more;
    total = data.total;
    $("load-more").hidden = !hasMore;
    $("empty-results").hidden = total !== 0;
    $("results-count").textContent = total === 1 ? "1 document" : total + " documents";
    status("Ready");
  } catch (e) {
    if (seq === requestSeq) status(e.message);
  } finally {
    if (seq === requestSeq) {
      loading = false;
      $("load-more").disabled = false;
    }
  }
}

async function trashOrRestore() {
  if (!current || !canLeave()) return;
  const restore = !!current.deleted_at;
  if (!restore && !confirm("Move this document to Trash? Existing sharing links will be revoked.")) return;
  try {
    await api("/api/documents/" + current.id + "/" + (restore ? "restore" : "trash"), {method: "POST"});
    current = null; dirty = false; $("editor").hidden = true; $("library").hidden = false;
    for (const id of ["back", "favorite-toggle", "history", "share", "export", "remove"]) $(id).hidden = true;
    await Promise.all([updateOverview(), loadDocuments(true)]);
    status(restore ? "Document restored" : "Moved to Trash");
  } catch (e) { status(e.message); }
}

async function showHistory() {
  if (!current) return;
  try {
    const data = await api("/api/documents/" + current.id + "/revisions");
    const box = $("versions"); box.replaceChildren();
    for (const rev of data.revisions) {
      const row = el("div", undefined, "revision-row");
      const info = el("span"); info.append(el("strong", "Version " + rev.version),
        el("small", dateDisplay(rev.created_at)));
      const button = el("button", "View", "button ghost");
      button.onclick = async () => {
        try {
          const historic = await api("/api/documents/" + current.id + "/revisions/" + rev.version);
          if (confirm("Version " + rev.version + " — " + historic.title + "\n\n" +
            historic.body.slice(0, 1200) + "\n\nRestore this revision as a new version?")) {
            if (dirty || current.deleted_at) { status("Save or restore this document first"); return; }
            const restored = await api("/api/documents/" + current.id + "/revisions/" + rev.version,
              {method: "POST", body: {version: current.version}});
            showDocument(restored);
            $("versions-dialog").close();
          }
        } catch (e) { status(e.message); }
      };
      row.append(info, button); box.append(row);
    }
    $("versions-dialog").showModal();
  } catch (e) { status(e.message); }
}

function shareDocument() {
  if (!current || dirty || saving) { status("Finish saving before sharing"); return; }
  $("share-url").hidden = true; $("copy-link").hidden = true;
  $("copy-link").textContent = "Copy link";
  $("share-dialog").showModal();
}

async function createShare() {
  if (!current) return;
  try {
    const data = await api("/api/documents/" + current.id + "/share", {
      method: "POST", body: {hours: Number($("expiry").value)}
    });
    $("share-url").value = location.origin + "/share#" + encodeURIComponent(data.token);
    $("share-url").hidden = false; $("copy-link").hidden = false;
  } catch (e) { status(e.message); }
}

async function exportCurrent() {
  if (!current || dirty || saving) { status("Finish saving before downloading"); return; }
  const documentId = current.id, documentFormat = current.format;
  try {
    let data;
    try {
      data = await api("/api/documents/" + documentId + "/export");
    } catch (e) {
      if (e.status !== 413 || documentFormat !== "gcdoc") throw e;
      if (!current || current.id !== documentId || dirty || saving) {
        status("Document changed while preparing download; try again");
        return;
      }
      const approved = confirm("Native GC DOC export exceeds the size limit. Download a Markdown (.md) copy instead? Text is preserved, but folder metadata is not included. Your saved document will not change.");
      if (!approved) { status("Download canceled; document unchanged"); return; }
      data = await api("/api/documents/" + documentId + "/export?format=md");
    }
    const blob = new Blob([data.content], {type: data.mime_type});
    const link = document.createElement("a"), url = URL.createObjectURL(blob);
    link.href = url; link.download = data.filename;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    status("Downloaded " + data.filename);
  } catch (e) { status(e.message); }
}

async function importFile(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (!/\.(gcdoc|md)$/i.test(file.name) || file.size > 1024 * 1024 + 4096) {
    status("Import only .gcdoc or .md files up to 1 MiB"); return;
  }
  if (!canLeave()) return;
  try {
    const content = await file.text();
    const doc = await api("/api/documents/import", {
      method: "POST", body: {filename: file.name, content}
    });
    showDocument(doc); await updateOverview();
  } catch (e) { status(e.message); }
}

function editorMode(next) {
  $("panes").className = "panes " + (next === "edit" ? "edit-only" : next === "preview" ? "preview-only" : "split");
  for (const name of ["edit", "split", "preview"]) {
    const btn = $("mode-" + name);
    btn.classList.toggle("selected", name === next);
    btn.setAttribute("aria-pressed", String(name === next));
  }
}

$("login-form").onsubmit = async e => {
  e.preventDefault();
  token = $("token").value.trim();
  try {
    await Promise.all([updateOverview(), loadDocuments(true)]);
    $("login").hidden = true; $("shell").hidden = false; $("token").value = "";
    setView(view); navState(); status("Ready");
  } catch (err) { token = ""; $("login-error").textContent = "Unable to unlock: " + err.message; }
};
$("new").onclick = $("quick-create").onclick = $("empty-new").onclick = createDocument;
$("import").onclick = $("quick-import").onclick = () => $("import-input").click();
$("import-input").onchange = importFile;
$("quick-policies").onclick = () => selectCategory("folder", "Policies");
for (const id of ["overview", "all", "favorites", "recent", "trash"]) {
  $(id).onclick = () => selectCategory(id);
}
$("format-gcdoc").onclick = () => selectCategory("gcdoc");
$("format-md").onclick = () => selectCategory("md");
for (const name of ["total", "favorites", "recent", "trash"]) {
  $("stat-" + name).closest("button").onclick = () => selectCategory(name === "total" ? "all" : name);
}
$("search").oninput = e => { query = e.target.value; loadDocuments(true).catch(err => status(err.message)); };
$("sort").onchange = e => { sortKey = e.target.value; loadDocuments(true).catch(err => status(err.message)); };
$("direction").onclick = () => {
  direction = direction === "desc" ? "asc" : "desc";
  $("direction").textContent = direction === "desc" ? "↓" : "↑";
  loadDocuments(true).catch(err => status(err.message));
};
$("load-more").onclick = () => loadDocuments(false).catch(e => status(e.message));
$("library").onscroll = () => {
  if (hasMore && !loading &&
    $("library").scrollTop + $("library").clientHeight > $("library").scrollHeight - 500) {
    loadDocuments(false).catch(e => status(e.message));
  }
};
for (const name of ["grid", "list"]) $("view-" + name).onclick = () => setView(name);
for (const id of ["title", "folder", "body"]) $(id).oninput = edited;
$("back").onclick = leaveEditor;
$("favorite-toggle").onclick = () => toggleFavorite();
$("history").onclick = showHistory;
$("remove").onclick = trashOrRestore;
$("share").onclick = shareDocument;
$("export").onclick = exportCurrent;
$("create-link").onclick = createShare;
$("copy-link").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("share-url").value);
    $("copy-link").textContent = "Copied ✓";
  } catch (_) { $("share-url").select(); }
};
for (const name of ["edit", "split", "preview"]) {
  $("mode-" + name).onclick = () => editorMode(name);
}
document.querySelectorAll("[data-close]").forEach(b => {
  b.onclick = () => b.closest("dialog").close();
});
$("logout").onclick = () => {
  if (!canLeave()) return;
  clearTimeout(timer);
  token = ""; current = null; dirty = false; $("shell").hidden = true; $("login").hidden = false;
  $("search").value = ""; query = "";
};
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault(); clearTimeout(timer); save();
  }
});
window.addEventListener("beforeunload", e => {
  if (dirty) { e.preventDefault(); e.returnValue = ""; }
});
