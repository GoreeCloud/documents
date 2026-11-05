"use strict";
const title = document.getElementById("shared-title");
const content = document.getElementById("shared-content");
const status = document.getElementById("shared-status");
function render(text, target) {
  target.replaceChildren();
  for (const line of text.split("\n")) {
    let node, value = line;
    if (/^#{1,6} /.test(line)) {
      const depth = line.match(/^#+/)[0].length;
      node = document.createElement("h" + depth);
      value = line.slice(depth + 1);
    } else if (/^[-*] /.test(line)) {
      node = document.createElement("p"); node.className = "bullet"; value = "•  " + line.slice(2);
    } else { node = document.createElement("p"); if (!line.trim()) node.className = "blank"; }
    node.textContent = value; target.append(node);
  }
}
const token = decodeURIComponent(location.hash.slice(1));
if (!/^[A-Za-z0-9_-]{20,120}$/.test(token)) {
  title.textContent = "Invalid share link"; status.textContent = "This link is incomplete.";
} else {
  fetch("/api/public/" + encodeURIComponent(token), {cache:"no-store"})
    .then(async r => { const d = await r.json(); if (!r.ok) throw new Error(d.error || "Unavailable"); return d; })
    .then(d => { title.textContent = d.title; status.textContent = "Read-only · Updated " + new Date(d.updated_at).toLocaleString(); render(d.body, content); })
    .catch(e => { title.textContent = "Document unavailable"; status.textContent = e.message; });
}
