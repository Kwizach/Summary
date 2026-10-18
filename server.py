#!/usr/bin/env python3
"""
Local web server for the YouTube summaries in reports/.

Usage: server.py [--port 47821] [--dir reports]

Serves the report pages, plus a library page at / to browse summaries, group
them into folders and delete them. Folder data lives in reports/library.json;
report files stay where they are, so their URLs never change.

API (JSON; write calls must come from the library page itself):
  GET  /api/ping                 {"app": "yt-summary", "mtime": <server.py mtime>}
  GET  /api/library              {"folders": [...], "summaries": [...]}
  POST /api/folders              {"name": "AI"}            -> {"id": "f-..."}
  POST /api/folders/delete       {"id": "f-..."}           (its summaries become unsorted)
  POST /api/move                 {"ids": [...], "folder": "f-..." | null}
  POST /api/delete               {"ids": [...]}            (removes all of each summary's files)

Binds to 127.0.0.1 only.
"""

import argparse
import json
import os
import re
import shutil
import sys
import threading
import uuid
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_report import find_video_id  # noqa: E402

SERVER_MTIME = os.path.getmtime(os.path.abspath(__file__))
SUMMARY_ID_RE = re.compile(r"^summary-[0-9A-Za-z_-]+$")
LOCK = threading.Lock()


class Library:
    def __init__(self, root):
        self.root = root
        self.path = os.path.join(root, "library.json")

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        data.setdefault("folders", [])
        data.setdefault("assignments", {})
        return data

    def save(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def summary_ids(self):
        ids = set()
        for name in os.listdir(self.root):
            stem, ext = os.path.splitext(name)
            if ext in (".html", ".md") and SUMMARY_ID_RE.match(stem):
                ids.add(stem)
        return ids

    def describe(self, summary_id, assignments):
        md_path = os.path.join(self.root, summary_id + ".md")
        status_path = os.path.join(self.root, ".jobs", summary_id, "status.json")
        title, video_id, state = None, None, "done"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                markdown = f.read()
            match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
            title = match.group(1).strip() if match else None
            video_id = find_video_id(markdown)
        else:
            try:
                with open(status_path, encoding="utf-8") as f:
                    status = json.load(f)
            except (OSError, ValueError):
                status = {}
            state = "error" if status.get("state") == "error" else "running" if status else "error"
            title = status.get("title") or None
            video_id = find_video_id(status.get("url", ""))
        stamp = summary_id.removeprefix("summary-")
        try:
            created = datetime.strptime(stamp, "%Y-%m-%d_%H%M%S").isoformat()
        except ValueError:
            created = None
        return {
            "id": summary_id,
            "title": title or "Untitled summary",
            "video_id": video_id,
            "created": created,
            "state": state,
            "folder": assignments.get(summary_id),
        }

    def listing(self):
        data = self.load()
        summaries = [self.describe(i, data["assignments"]) for i in self.summary_ids()]
        summaries.sort(key=lambda s: s["id"], reverse=True)
        return {"folders": data["folders"], "summaries": summaries}

    def create_folder(self, name):
        name = " ".join(str(name).split())[:80]
        if not name:
            raise ValueError("Folder name is empty")
        data = self.load()
        if any(f["name"].lower() == name.lower() for f in data["folders"]):
            raise ValueError(f"A folder named '{name}' already exists")
        folder = {"id": "f-" + uuid.uuid4().hex[:10], "name": name}
        data["folders"].append(folder)
        data["folders"].sort(key=lambda f: f["name"].lower())
        self.save(data)
        return folder

    def delete_folder(self, folder_id):
        data = self.load()
        data["folders"] = [f for f in data["folders"] if f["id"] != folder_id]
        data["assignments"] = {k: v for k, v in data["assignments"].items() if v != folder_id}
        self.save(data)

    def move(self, ids, folder_id):
        data = self.load()
        if folder_id is not None and folder_id not in {f["id"] for f in data["folders"]}:
            raise ValueError("Unknown folder")
        for summary_id in self.valid_ids(ids):
            if folder_id is None:
                data["assignments"].pop(summary_id, None)
            else:
                data["assignments"][summary_id] = folder_id
        self.save(data)

    def delete(self, ids):
        data = self.load()
        for summary_id in self.valid_ids(ids):
            for name in os.listdir(self.root):
                if os.path.splitext(name)[0] == summary_id:
                    os.remove(os.path.join(self.root, name))
            shutil.rmtree(os.path.join(self.root, ".jobs", summary_id), ignore_errors=True)
            data["assignments"].pop(summary_id, None)
        self.save(data)

    def valid_ids(self, ids):
        if not isinstance(ids, list) or not all(isinstance(i, str) and SUMMARY_ID_RE.match(i) for i in ids):
            raise ValueError("Invalid summary ids")
        unknown = set(ids) - self.summary_ids()
        if unknown:
            raise ValueError("Unknown summaries: " + ", ".join(sorted(unknown)))
        return ids


class Handler(SimpleHTTPRequestHandler):
    library: Library = None
    port: int = 0

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        # Rejects DNS-rebinding requests that reach us under another hostname.
        return self.headers.get("Host", "") in (f"localhost:{self.port}", f"127.0.0.1:{self.port}")

    def do_GET(self):
        if not self.host_ok():
            return self.send_error(403)
        path = self.path.split("?", 1)[0]
        if path == "/":
            body = LIBRARY_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path == "/api/ping":
            return self.send_json({"app": "yt-summary", "mtime": SERVER_MTIME})
        if path == "/api/library":
            return self.send_json(self.library.listing())
        if path.endswith("/") or path.startswith("/library.json"):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        # JSON content type forces a CORS preflight (which we never approve) for
        # cross-site requests; the Origin check covers the rest.
        origin_ok = self.headers.get("Origin") in (f"http://localhost:{self.port}", f"http://127.0.0.1:{self.port}")
        json_ok = self.headers.get("Content-Type", "").startswith("application/json")
        if not (self.host_ok() and origin_ok and json_ok):
            return self.send_json({"error": "Forbidden"}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            path = self.path.split("?", 1)[0]
            with LOCK:
                if path == "/api/folders":
                    return self.send_json(self.library.create_folder(body.get("name", "")))
                if path == "/api/folders/delete":
                    self.library.delete_folder(body.get("id"))
                elif path == "/api/move":
                    self.library.move(body.get("ids"), body.get("folder"))
                elif path == "/api/delete":
                    self.library.delete(body.get("ids"))
                else:
                    return self.send_json({"error": "Not found"}, 404)
            return self.send_json({"ok": True})
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)


LIBRARY_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Summaries</title>
<style>
:root { --fg: #1f2328; --muted: #59636e; --bg: #fff; --rule: #d1d9e0; --card: #f6f8fa; --link: #0969da; --hover: #eef4ff; --sel: #ddf4ff; --err: #cf222e; --accent: #0969da; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e6edf3; --muted: #9198a1; --bg: #0d1117; --rule: #3d444d; --card: #161b22; --link: #4493f8; --hover: #1a2433; --sel: #12263f; --err: #f85149; --accent: #4493f8; }
}
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.5 -apple-system, "Helvetica Neue", sans-serif; color: var(--fg); background: var(--bg); }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; background: var(--card); border: 1px solid var(--rule); border-radius: 6px; padding: 5px 12px; }
button:hover { background: var(--hover); }
button.danger { color: var(--err); }
.layout { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
aside { border-right: 1px solid var(--rule); padding: 20px 12px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }
aside h1 { font-size: 17px; margin: 0 8px 16px; }
.folders { list-style: none; margin: 0; padding: 0; }
.folders li { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
.folders li:hover { background: var(--hover); }
.folders li.active { background: var(--sel); font-weight: 600; }
.folders li.drop { outline: 2px dashed var(--accent); }
.folders .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.folders .count { color: var(--muted); font-size: 13px; }
.folders .del { visibility: hidden; border: 0; background: none; padding: 0 4px; color: var(--muted); }
.folders li:hover .del { visibility: visible; }
.folders .del:hover { color: var(--err); }
.sep { border-top: 1px solid var(--rule); margin: 10px 8px; }
#new-folder { width: 100%; margin-top: 10px; border: 1px dashed var(--rule); background: none; color: var(--muted); }
#new-folder-form { display: none; margin-top: 10px; gap: 6px; }
#new-folder-form input { flex: 1; min-width: 0; padding: 5px 8px; border: 1px solid var(--rule); border-radius: 6px; background: var(--bg); }
main { padding: 20px 24px 60px; min-width: 0; }
.top { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
.top h2 { margin: 0; font-size: 22px; flex: 1; }
#search { padding: 6px 10px; border: 1px solid var(--rule); border-radius: 6px; background: var(--bg); width: 240px; max-width: 100%; }
#toolbar { display: none; align-items: center; gap: 10px; flex-wrap: wrap; position: sticky; top: 0; z-index: 5; background: var(--sel); border: 1px solid var(--rule); border-radius: 8px; padding: 8px 12px; margin-bottom: 16px; }
#toolbar.show { display: flex; }
#toolbar .count { font-weight: 600; margin-right: auto; }
#toolbar select { padding: 4px 8px; border: 1px solid var(--rule); border-radius: 6px; background: var(--bg); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 18px; }
.card { position: relative; border-radius: 10px; border: 1px solid var(--rule); background: var(--card); overflow: hidden; }
.card.selected { outline: 3px solid var(--accent); }
.card a { color: inherit; text-decoration: none; display: block; }
.thumb { aspect-ratio: 16 / 9; background: #000 center / cover no-repeat; position: relative; }
.badge { position: absolute; bottom: 6px; right: 6px; font-size: 12px; padding: 1px 7px; border-radius: 4px; background: rgba(0,0,0,.75); color: #fff; }
.badge.error { background: var(--err); }
.info { padding: 8px 10px 10px; }
.title { font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.meta { color: var(--muted); font-size: 13px; margin-top: 2px; }
.check { position: absolute; top: 8px; left: 8px; width: 22px; height: 22px; z-index: 2; opacity: 0; accent-color: var(--accent); cursor: pointer; }
.card:hover .check, .card.selected .check, body.selecting .check { opacity: 1; }
.empty { color: var(--muted); padding: 40px 0; text-align: center; }
#error { color: var(--err); }
@media (max-width: 700px) {
  .layout { grid-template-columns: 1fr; }
  aside { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--rule); }
  main { padding: 16px; }
  .check { opacity: 1; }
}
</style>
</head><body>
<div class="layout">
  <aside>
    <h1>📹 YouTube Summaries</h1>
    <ul class="folders" id="fixed"></ul>
    <div class="sep"></div>
    <ul class="folders" id="folders"></ul>
    <button id="new-folder">+ New folder</button>
    <form id="new-folder-form"><input id="new-folder-name" placeholder="Folder name" maxlength="80"><button>Add</button></form>
  </aside>
  <main>
    <div class="top"><h2 id="heading">All summaries</h2><input id="search" type="search" placeholder="Search titles"></div>
    <div id="toolbar">
      <span class="count" id="sel-count"></span>
      <label>Move to <select id="move-to"></select></label>
      <button class="danger" id="delete">Delete</button>
      <button id="clear">Cancel</button>
    </div>
    <p id="error" hidden></p>
    <div class="grid" id="grid"></div>
    <p class="empty" id="empty" hidden></p>
  </main>
</div>
<script>
const $ = id => document.getElementById(id);
let data = { folders: [], summaries: [] };
let view = localStorageGet("view") || "all";   // "all" | "unsorted" | folder id
const selected = new Set();

function localStorageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function localStorageSet(key, value) { try { localStorage.setItem(key, value); } catch {} }

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || response.statusText);
  return result;
}

function showError(message) {
  $("error").hidden = !message;
  $("error").textContent = message || "";
}

async function refresh() {
  try {
    data = await api("/api/library");
    showError("");
  } catch (e) {
    showError("Could not load the library: " + e.message);
  }
  const ids = new Set(data.summaries.map(s => s.id));
  [...selected].forEach(id => ids.has(id) || selected.delete(id));
  if (!["all", "unsorted"].includes(view) && !data.folders.some(f => f.id === view)) view = "all";
  render();
}

function inView(summary) {
  if (view === "all") return true;
  if (view === "unsorted") return !summary.folder;
  return summary.folder === view;
}

function folderItem(id, name, count, deletable) {
  const li = document.createElement("li");
  li.dataset.id = id;
  li.className = view === id ? "active" : "";
  li.innerHTML = '<span class="name"></span><span class="count"></span>';
  li.querySelector(".name").textContent = name;
  li.querySelector(".count").textContent = count;
  li.onclick = () => { view = id; localStorageSet("view", id); render(); };
  if (deletable) {
    const del = document.createElement("button");
    del.className = "del";
    del.title = "Delete folder";
    del.textContent = "✕";
    del.onclick = async e => {
      e.stopPropagation();
      if (!confirm(`Delete the folder "${name}"? Its ${count} summar${count === 1 ? "y" : "ies"} will move to Unsorted.`)) return;
      await act(() => api("/api/folders/delete", { id }));
    };
    li.append(del);
  }
  if (id !== "all") {
    // Drop summaries on a folder (or Unsorted) to move them.
    li.ondragover = e => { e.preventDefault(); li.classList.add("drop"); };
    li.ondragleave = () => li.classList.remove("drop");
    li.ondrop = async e => {
      e.preventDefault();
      li.classList.remove("drop");
      const ids = JSON.parse(e.dataTransfer.getData("application/x-summary-ids") || "[]");
      if (ids.length) await act(() => api("/api/move", { ids, folder: id === "unsorted" ? null : id }));
    };
  }
  return li;
}

function card(summary) {
  const folder = data.folders.find(f => f.id === summary.folder);
  const div = document.createElement("div");
  div.className = "card";
  div.dataset.id = summary.id;
  div.draggable = true;
  div.innerHTML = `
    <input type="checkbox" class="check" title="Select">
    <a href="/${summary.id}.html">
      <div class="thumb"></div>
      <div class="info"><div class="title"></div><div class="meta"></div></div>
    </a>`;
  const check = div.querySelector(".check");
  check.onchange = () => { check.checked ? selected.add(summary.id) : selected.delete(summary.id); updateSelection(); };
  const thumb = div.querySelector(".thumb");
  if (summary.video_id) thumb.style.backgroundImage = `url("https://i.ytimg.com/vi/${summary.video_id}/mqdefault.jpg")`;
  if (summary.state !== "done") {
    const badge = document.createElement("span");
    badge.className = "badge" + (summary.state === "error" ? " error" : "");
    badge.textContent = summary.state === "error" ? "Failed" : "⏳ In progress";
    thumb.append(badge);
  }
  div.querySelector(".title").textContent = summary.title;
  div.querySelector(".title").title = summary.title;
  const date = summary.created ? new Date(summary.created).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  div.querySelector(".meta").textContent = [date, view === "all" && folder ? "📁 " + folder.name : ""].filter(Boolean).join(" · ");
  div.ondragstart = e => {
    const ids = selected.has(summary.id) ? [...selected] : [summary.id];
    e.dataTransfer.setData("application/x-summary-ids", JSON.stringify(ids));
    e.dataTransfer.effectAllowed = "move";
  };
  return div;
}

function render() {
  const count = filter => data.summaries.filter(filter).length;
  $("fixed").replaceChildren(
    folderItem("all", "All summaries", data.summaries.length, false),
    folderItem("unsorted", "Unsorted", count(s => !s.folder), false),
  );
  $("folders").replaceChildren(...data.folders.map(f => folderItem(f.id, "📁 " + f.name, count(s => s.folder === f.id), true)));

  const current = data.folders.find(f => f.id === view);
  $("heading").textContent = view === "all" ? "All summaries" : view === "unsorted" ? "Unsorted" : current.name;
  const query = $("search").value.trim().toLowerCase();
  const visible = data.summaries.filter(s => inView(s) && (!query || s.title.toLowerCase().includes(query)));
  $("grid").replaceChildren(...visible.map(card));
  $("empty").hidden = visible.length > 0;
  $("empty").textContent = query ? "No summary matches your search." : view === "all"
    ? "No summaries yet. Copy a YouTube link and run the Shortcut."
    : "This folder is empty. Drag summaries here, or select them and use “Move to”.";

  updateSelection();
  $("move-to").replaceChildren(
    new Option("Choose…", ""),
    new Option("Unsorted", "unsorted"),
    ...data.folders.map(f => new Option(f.name, f.id)),
  );
}

function updateSelection() {
  document.querySelectorAll(".card").forEach(card => {
    const isSelected = selected.has(card.dataset.id);
    card.classList.toggle("selected", isSelected);
    card.querySelector(".check").checked = isSelected;
  });
  document.body.classList.toggle("selecting", selected.size > 0);
  $("toolbar").classList.toggle("show", selected.size > 0);
  $("sel-count").textContent = `${selected.size} selected`;
}

async function act(fn) {
  try {
    await fn();
  } catch (e) {
    showError(e.message);
  }
  await refresh();
}

$("move-to").onchange = async e => {
  const target = e.target.value;
  if (!target) return;
  const ids = [...selected];
  selected.clear();
  await act(() => api("/api/move", { ids, folder: target === "unsorted" ? null : target }));
};
$("delete").onclick = async () => {
  const n = selected.size;
  if (!confirm(`Delete ${n} summar${n === 1 ? "y" : "ies"}? This removes the files and can't be undone.`)) return;
  const ids = [...selected];
  selected.clear();
  await act(() => api("/api/delete", { ids }));
};
$("clear").onclick = () => { selected.clear(); updateSelection(); };
$("search").oninput = render;
$("new-folder").onclick = () => {
  $("new-folder").style.display = "none";
  $("new-folder-form").style.display = "flex";
  $("new-folder-name").focus();
};
$("new-folder-form").onsubmit = async e => {
  e.preventDefault();
  const name = $("new-folder-name").value;
  $("new-folder-name").value = "";
  $("new-folder-form").style.display = "none";
  $("new-folder").style.display = "";
  if (name.trim()) await act(async () => { const f = await api("/api/folders", { name }); view = f.id; localStorageSet("view", f.id); });
};
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { selected.clear(); updateSelection(); }
});

refresh();
setInterval(() => { if (!document.hidden && selected.size === 0) refresh(); }, 5000);
</script>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--port", type=int, default=47821)
    parser.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports"))
    args = parser.parse_args()
    root = os.path.abspath(args.dir)
    os.makedirs(root, exist_ok=True)
    Handler.library = Library(root)
    Handler.port = args.port
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=root))
    server.serve_forever()


if __name__ == "__main__":
    main()
