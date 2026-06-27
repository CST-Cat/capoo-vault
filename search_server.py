#!/usr/bin/env python3
"""Capoo Vault — TF-IDF sticker search with local GIF preview"""

import json
import os
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote

from dotenv import load_dotenv

load_dotenv()

STICKERS = []
STICKERS_BY_SET = {}
TFIDF_INDEX = None
VAULT_DIR = "/app/frames"
VAULT_DIRS = {}
COLLECTIONS = []


def load_data():
    global STICKERS, STICKERS_BY_SET, TFIDF_INDEX, VAULT_DIRS, COLLECTIONS
    meta_path = "data/stickers.json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            STICKERS = json.load(f)
        print(f"[load] {len(STICKERS)} annotations")
    for s in STICKERS:
        set_name = s.get("set", "")
        if set_name not in STICKERS_BY_SET:
            STICKERS_BY_SET[set_name] = []
        STICKERS_BY_SET[set_name].append(s)
    tfidf_path = "data/tfidf_index.json"
    if os.path.exists(tfidf_path):
        with open(tfidf_path) as f:
            TFIDF_INDEX = json.load(f)
        print("[load] TF-IDF index")
    if os.path.isdir(VAULT_DIR):
        for d in os.listdir(VAULT_DIR):
            if os.path.isdir(os.path.join(VAULT_DIR, d)) and len(d) >= 3:
                VAULT_DIRS[d[:3]] = d
        print(f"[load] {len(VAULT_DIRS)} GIF sets")
    for prefix in sorted(VAULT_DIRS.keys()):
        full_name = VAULT_DIRS[prefix]
        count = len([f for f in os.listdir(os.path.join(VAULT_DIR, full_name)) if f.endswith('.gif')])
        COLLECTIONS.append({"name": full_name, "prefix": prefix, "count": count})


def find_gif(set_name: str, gif_name: str) -> str | None:
    path = os.path.join(VAULT_DIR, set_name, gif_name)
    if os.path.isfile(path):
        return path
    prefix = set_name[:3] if len(set_name) >= 3 else set_name
    if prefix in VAULT_DIRS:
        full_dir = VAULT_DIRS[prefix]
        if full_dir.startswith(set_name):
            path = os.path.join(VAULT_DIR, full_dir, gif_name)
            if os.path.isfile(path):
                return path
    return None


def tfidf_search(query: str, limit: int = 0) -> list[dict]:
    if not TFIDF_INDEX:
        return []
    vocab = TFIDF_INDEX["vocab"]
    idf = TFIDF_INDEX["idf"]
    rows = TFIDF_INDEX["rows"]
    query_vec = {}
    for n in range(1, 5):
        for i in range(len(query) - n + 1):
            gram = query[i : i + n]
            if gram in vocab:
                idx = vocab[gram]
                query_vec[idx] = query_vec.get(idx, 0) + 1
    for idx in query_vec:
        query_vec[idx] *= idf[idx]
    if not query_vec:
        return []
    scores = []
    for i, row in enumerate(rows):
        dot = 0
        for j, col in enumerate(row["c"]):
            if col in query_vec:
                dot += query_vec[col] * row["v"][j]
        if dot > 0:
            scores.append((i, dot))
    scores.sort(key=lambda x: -x[1])
    results = []
    for idx, score in (scores[:limit] if limit else scores):
        sticker = STICKERS[idx] if idx < len(STICKERS) else {}
        results.append({"score": round(score, 4), **sticker})
    return results


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capoo Vault</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --primary: #cc785c;
  --primary-active: #a9583e;
  --ink: #141413;
  --body: #3d3d3a;
  --muted: #6c6a64;
  --muted-soft: #8e8b82;
  --hairline: #e6dfd8;
  --hairline-soft: #ebe6df;
  --canvas: #faf9f5;
  --surface-soft: #f5f0e8;
  --surface-card: #efe9de;
  --surface-cream-strong: #e8e0d2;
  --surface-dark: #181715;
  --surface-dark-elevated: #252320;
  --on-primary: #ffffff;
  --on-dark: #faf9f5;
  --on-dark-soft: #a09d96;
  --accent-teal: #5db8a6;
  --error: #c64545;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --sidebar-w: 240px;
  --sidebar-collapsed-w: 52px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, system-ui, sans-serif;
  background: var(--canvas);
  color: var(--ink);
  min-height: 100vh;
  display: flex;
}

/* ── Sidebar ── */
.sidebar {
  width: var(--sidebar-w);
  min-height: 100vh;
  background: var(--canvas);
  border-right: 1px solid var(--hairline);
  box-shadow: 2px 0 8px rgba(20,20,19,0.04);
  color: var(--ink);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0; top: 0; bottom: 0;
  z-index: 100;
  overflow: hidden;
  transition: width 0.2s ease;
}
.sidebar.collapsed { width: var(--sidebar-collapsed-w); }

.sidebar-brand {
  padding: 20px 16px;
  border-bottom: 1px solid var(--hairline);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
}
.sidebar-brand .brand-text { overflow: hidden; white-space: nowrap; }
.sidebar-brand h1 {
  font-family: 'Playfair Display', serif;
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.3px;
}
.sidebar-brand p {
  font-size: 12px;
  color: var(--muted);
  margin-top: 2px;
}
.sidebar.collapsed .brand-text,
.sidebar .nav-icon { display: none; }
.sidebar.collapsed .nav-icon { display: inline; }
.sidebar.collapsed .nav-label,
.sidebar.collapsed .sidebar-section,
.sidebar.collapsed .sidebar-collections,
.sidebar.collapsed .sidebar-download-all span,
.sidebar.collapsed .sidebar-download-all button { display: none; }

.sidebar-toggle {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--hairline);
  color: var(--muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  transition: background 0.15s;
}
.sidebar-toggle:hover { background: var(--surface-card); }

.sidebar-nav { padding: 12px 8px; }
.sidebar-nav a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  color: var(--muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-nav a:hover,
.sidebar-nav a.active {
  background: var(--surface-card);
  color: var(--ink);
}
.sidebar.collapsed .nav-label { display: none; }
.sidebar.collapsed .sidebar-nav a {
  justify-content: center;
  padding: 10px;
}

.sidebar-section {
  padding: 8px 16px 4px;
  font-size: 11px;
  font-weight: 500;
  color: var(--muted-soft);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-collections {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}
.sidebar-collections .coll-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-collections .coll-item:hover {
  background: var(--surface-card);
  color: var(--ink);
}
.sidebar-collections .coll-item .coll-count {
  font-size: 11px;
  color: var(--muted-soft);
  background: var(--surface-soft);
  padding: 2px 8px;
  border-radius: 9999px;
  flex-shrink: 0;
}
.sidebar-collections .coll-item .coll-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
}

.sidebar-download-all {
  padding: 12px 8px;
  border-top: 1px solid var(--hairline);
}
.sidebar-download-all button {
  width: 100%;
  padding: 9px 12px;
  background: var(--primary);
  color: var(--on-primary);
  border: none;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  font-family: 'Inter', sans-serif;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-download-all button:hover { background: var(--primary-active); }
.sidebar.collapsed .sidebar-download-all button {
  padding: 9px 4px;
  font-size: 0;
}
.sidebar.collapsed .sidebar-download-all button::after {
  content: "\2193";
  font-size: 14px;
}

/* ── Main ── */
.main {
  flex: 1;
  margin-left: var(--sidebar-w);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: margin-left 0.2s ease;
}
body.sidebar-collapsed .main { margin-left: var(--sidebar-collapsed-w); }

/* ── Header ── */
.header { padding: 48px 32px 32px; border-bottom: 1px solid var(--hairline); }
.header h2 {
  font-family: 'Playfair Display', serif;
  font-size: 36px; font-weight: 400; line-height: 1.1; letter-spacing: -0.5px; margin-bottom: 8px;
}
.header .subtitle { font-size: 15px; color: var(--muted); }

/* ── Search ── */
.search-wrap { max-width: 640px; padding: 24px 32px 0; }
.search-box { display: flex; gap: 8px; }
.search-box input {
  flex: 1; padding: 12px 16px; font-size: 15px; font-family: 'Inter', sans-serif;
  background: var(--canvas); border: 1px solid var(--hairline);
  border-radius: var(--radius-md); color: var(--ink); outline: none; height: 44px;
}
.search-box input:focus { border-color: var(--primary); }
.search-box input::placeholder { color: var(--muted-soft); }
.search-box button {
  padding: 12px 20px; background: var(--primary); color: var(--on-primary);
  border: none; border-radius: var(--radius-md); font-size: 14px; font-weight: 500;
  font-family: 'Inter', sans-serif; cursor: pointer; height: 44px; white-space: nowrap;
}
.search-box button:hover { background: var(--primary-active); }

/* ── Toolbar ── */
.toolbar {
  display: flex; align-items: center; justify-content: space-between; padding: 16px 32px 0;
}
.toolbar .stats { font-size: 14px; color: var(--muted); }
.toolbar .actions { display: flex; gap: 8px; }
.toolbar .actions button {
  padding: 8px 14px; background: var(--surface-card); color: var(--ink);
  border: 1px solid var(--hairline); border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 500; font-family: 'Inter', sans-serif; cursor: pointer;
}
.toolbar .actions button:hover { background: var(--surface-soft); }
.toolbar .actions button.primary {
  background: var(--primary); color: var(--on-primary); border-color: var(--primary);
}
.toolbar .actions button.primary:hover { background: var(--primary-active); }

/* ── Results ── */
.results {
  flex: 1; padding: 16px 32px 48px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px; align-content: start;
}
.card {
  background: var(--surface-card); border-radius: var(--radius-lg);
  overflow: hidden; border: 1px solid var(--hairline-soft);
  transition: transform 0.2s, box-shadow 0.2s; cursor: pointer; position: relative;
}
.card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(20,20,19,0.07); }
.card.selected { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(204,120,92,0.3); }
.card .select-check {
  position: absolute; top: 8px; left: 8px; width: 22px; height: 22px;
  border-radius: var(--radius-sm); background: var(--canvas);
  border: 2px solid var(--hairline); display: flex; align-items: center;
  justify-content: center; font-size: 13px; color: transparent; z-index: 2;
  transition: all 0.15s;
}
.card.selected .select-check {
  background: var(--primary); border-color: var(--primary); color: var(--on-primary);
}
.card .preview {
  width: 100%; aspect-ratio: 1; background: var(--surface-soft);
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.card .preview img { max-width: 100%; max-height: 100%; object-fit: contain; }
.card .info { padding: 12px; }
.card .emotion {
  font-family: 'Playfair Display', serif; font-size: 15px; font-weight: 500; line-height: 1.3;
}
.card .desc { font-size: 12px; color: var(--body); margin-top: 6px; line-height: 1.4; }
.card .tags { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 3px; }
.card .tags span {
  background: var(--surface-soft); color: var(--muted); font-size: 11px;
  font-weight: 500; padding: 2px 8px; border-radius: var(--radius-sm);
}
.card .meta {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 8px; font-size: 11px; color: var(--muted-soft);
}
.card .score { font-family: 'JetBrains Mono', monospace; }

/* ── Empty ── */
.empty { text-align: center; padding: 96px 24px; color: var(--muted-soft); grid-column: 1 / -1; }
.empty p { font-size: 16px; line-height: 1.55; }

/* ── Modal ── */
.modal-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(20,20,19,0.6); backdrop-filter: blur(4px);
  z-index: 1000; align-items: center; justify-content: center; padding: 24px;
}
.modal-overlay.active { display: flex; }
.modal {
  background: var(--canvas); border-radius: var(--radius-xl);
  max-width: 420px; width: 100%; overflow: hidden;
  box-shadow: 0 24px 64px rgba(20,20,19,0.2);
  animation: modalIn 0.2s ease-out; position: relative;
}
@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.modal-close {
  position: absolute; top: 12px; right: 12px;
  width: 32px; height: 32px; border-radius: 50%;
  background: rgba(20,20,19,0.5); color: #fff;
  border: none; font-size: 16px; cursor: pointer; z-index: 10;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.modal-close:hover { background: rgba(20,20,19,0.8); }
.modal .modal-preview {
  width: 100%; aspect-ratio: 1; background: var(--surface-soft);
  display: flex; align-items: center; justify-content: center;
}
.modal .modal-preview img { max-width: 100%; max-height: 100%; object-fit: contain; }
.modal .modal-info { padding: 20px; }
.modal .modal-title {
  font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 500; margin-bottom: 4px;
}
.modal .modal-desc { font-size: 14px; color: var(--body); line-height: 1.55; margin-bottom: 12px; }
.modal .modal-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 20px; }
.modal .modal-tags span {
  background: var(--surface-soft); color: var(--muted); font-size: 12px;
  font-weight: 500; padding: 3px 10px; border-radius: var(--radius-sm);
}
.modal .modal-actions { display: flex; gap: 8px; }
.modal .modal-actions button {
  flex: 1; padding: 12px 16px; border: none; border-radius: var(--radius-md);
  font-size: 14px; font-weight: 500; font-family: 'Inter', sans-serif;
  cursor: pointer; transition: background 0.15s, transform 0.1s;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.modal .modal-actions button:active { transform: scale(0.97); }
.modal .btn-copy { background: var(--primary); color: var(--on-primary); }
.modal .btn-copy:hover { background: var(--primary-active); }
.modal .btn-download { background: var(--surface-card); color: var(--ink); border: 1px solid var(--hairline) !important; }
.modal .btn-download:hover { background: var(--surface-soft); }

/* ── Toast ── */
.toast-container {
  position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
  z-index: 2000; display: flex; flex-direction: column; gap: 8px; pointer-events: none;
}
.toast {
  background: var(--canvas); color: var(--ink);
  padding: 12px 20px; border-radius: var(--radius-md);
  font-size: 14px; font-weight: 500; font-family: 'Inter', sans-serif;
  box-shadow: 0 8px 24px rgba(20,20,19,0.2);
  animation: toastIn 0.25s ease-out, toastOut 0.25s ease-in 2s forwards;
  border: 1px solid var(--hairline);
  display: flex; align-items: center; gap: 8px; pointer-events: auto;
}
.toast.success { border-left: 3px solid var(--accent-teal); }
.toast.error { border-left: 3px solid var(--error); }
@keyframes toastIn { from { opacity: 0; transform: translateY(-12px); } to { opacity: 1; transform: translateY(0); } }
@keyframes toastOut { from { opacity: 1; } to { opacity: 0; transform: translateY(-12px); } }

/* ── Footer ── */
/* ── Collection Pagination ── */

.coll-pagination {

  display: flex;

  align-items: center;

  justify-content: center;

  gap: 16px;

  padding: 24px 32px 48px;

}

.coll-nav-btn {

  padding: 10px 20px;

  background: var(--surface-card);

  color: var(--ink);

  border: 1px solid var(--hairline);

  border-radius: var(--radius-md);

  font-size: 14px;

  font-weight: 500;

  font-family: "Inter", sans-serif;

  cursor: pointer;

  transition: background 0.15s;

}

.coll-nav-btn:hover { background: var(--surface-soft); }

.coll-nav-btn:disabled {

  opacity: 0.4;

  cursor: not-allowed;

}

.coll-nav-info {

  font-size: 14px;

  color: var(--muted);

}
.footer {
  background: var(--surface-dark); color: var(--on-dark-soft);
  text-align: center; padding: 24px 32px; font-size: 13px;
  margin-left: var(--sidebar-w);
  transition: margin-left 0.2s ease;
}
body.sidebar-collapsed .footer { margin-left: var(--sidebar-collapsed-w); }
.footer a { color: var(--on-dark); text-decoration: none; }
.footer a:hover { color: var(--primary); }

/* ── Responsive ── */
@media (max-width: 768px) {
  .sidebar { display: none; }
  .main, .footer { margin-left: 0; }
  .results { grid-template-columns: repeat(2, 1fr); gap: 12px; padding: 16px; }
  .header { padding: 32px 16px 24px; }
  .header h2 { font-size: 28px; }
  .search-wrap { padding: 16px 16px 0; }
  .toolbar { padding: 12px 16px 0; }
}
</style>
</head>
<body>

<!-- Sidebar -->
<div class="sidebar" id="sidebar">
  <div class="sidebar-brand">
    <div class="brand-text">
      <h1>Capoo Vault</h1>
      <p>10,238 stickers</p>
    </div>
    <button class="sidebar-toggle" onclick="toggleSidebar()" title="Toggle sidebar">&laquo;</button>
  </div>
  <nav class="sidebar-nav">
    <a class="active" onclick="showHome()" id="nav-home"><span class="nav-label">Search</span><span class="nav-icon">S</span></a>
    <a onclick="showCollections()" id="nav-collections"><span class="nav-label">Collections</span><span class="nav-icon">C</span></a>
  </nav>
  <div class="sidebar-section">Collections</div>
  <div class="sidebar-collections" id="coll-list"></div>
  <div class="sidebar-download-all">
    <button onclick="downloadAllVisible()"><span>Download All</span></button>
  </div>
</div>

<!-- Main -->
<div class="main" id="main-content">
  <div id="view-home">
    <div class="header">
      <h2>Search Stickers</h2>
      <p class="subtitle">Find the perfect Capoo sticker by emotion, action, or description</p>
    </div>
    <div class="search-wrap">
      <div class="search-box">
        <input type="text" id="q" placeholder="e.g. 开心, 摸鱼, 大哭, 打瞌睡..." autofocus>
        <button onclick="doSearch()">Search</button>
      </div>
    </div>
    <div class="toolbar" id="toolbar" style="display:none">
      <div class="stats" id="stats"></div>
      <div class="actions">
        <button onclick="selectAll()">Select All</button>
        <button onclick="deselectAll()">Deselect</button>
        <button class="primary" onclick="downloadSelected()">Download Selected</button>
      </div>
    </div>
    <div class="results" id="results">
      <div class="empty"><p>Search for Capoo stickers by keyword</p></div>
    </div>
  </div>
  <div id="view-collection" style="display:none">
    <div class="header">
      <h2 id="coll-title">Collection</h2>
      <p class="subtitle" id="coll-subtitle"></p>
    </div>
    <div class="toolbar">
      <div class="stats" id="coll-stats"></div>
      <div class="actions">
        <button onclick="selectAll()">Select All</button>
        <button onclick="deselectAll()">Deselect</button>
        <button class="primary" onclick="downloadSelected()">Download Selected</button>
      </div>
    </div>
    <div class="results" id="coll-results"></div>
    <div class="coll-pagination" id="coll-pagination">
      <button class="coll-nav-btn" id="coll-prev" onclick="prevCollection()">Previous</button>
      <span class="coll-nav-info" id="coll-nav-info"></span>
      <button class="coll-nav-btn" id="coll-next" onclick="nextCollection()">Next</button>
    </div>
  </div>
</div>

<!-- Modal -->
<div class="modal-overlay" id="modal" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">X</button>
    <div class="modal-preview"><img id="modal-img" src="" alt=""></div>
    <div class="modal-info">
      <div class="modal-title" id="modal-title"></div>
      <div class="modal-desc" id="modal-desc"></div>
      <div class="modal-tags" id="modal-tags"></div>
      <div class="modal-actions">
        <button class="btn-copy" onclick="copyGif()">Copy</button>
        <button class="btn-download" onclick="downloadGif()">Download</button>
      </div>
    </div>
  </div>
</div>

<div class="toast-container" id="toasts"></div>

<script>
let currentSticker = null;
let selectedStickers = new Set();
let currentResults = [];
let currentView = "home";
let allCollections = [];
let currentCollIndex = -1;

function gifUrl(r) { return '/gif/' + encodeURIComponent(r.set) + '/' + encodeURIComponent(r.gif); }
function stickerKey(r) { return r.set + '/' + r.gif; }

// ── Sidebar ──
function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const collapsed = sb.classList.toggle('collapsed');
  document.body.classList.toggle('sidebar-collapsed', collapsed);
  sb.querySelector('.sidebar-toggle').innerHTML = collapsed ? '&raquo;' : '&laquo;';
  localStorage.setItem('sidebar-collapsed', collapsed ? '1' : '0');
}
(function() {
  if (localStorage.getItem('sidebar-collapsed') === '1') {
    document.getElementById('sidebar').classList.add('collapsed');
    document.body.classList.add('sidebar-collapsed');
    document.querySelector('.sidebar-toggle').innerHTML = '&raquo;';
  }
})();

// ── Toast ──
function showToast(msg, type = 'success') {
  const c = document.getElementById('toasts');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// ── Selection ──
function toggleSelect(r, e) {
  e.stopPropagation();
  const key = stickerKey(r);
  selectedStickers.has(key) ? selectedStickers.delete(key) : selectedStickers.add(key);
  renderCards();
}
function selectAll() {
  currentResults.forEach(r => selectedStickers.add(stickerKey(r)));
  renderCards();
  showToast(selectedStickers.size + ' selected');
}
function deselectAll() {
  selectedStickers.clear();
  renderCards();
}

function renderCards() {
  const container = currentView === 'home' ? 'results' : 'coll-results';
  document.getElementById(container).innerHTML = currentResults.map(r => {
    const key = stickerKey(r);
    const sel = selectedStickers.has(key);
    return '<div class="card ' + (sel ? 'selected' : '') + '" onclick=\'openModal(' + JSON.stringify(r).replace(/'/g,"&#39;") + ')\'>' +
      '<div class="select-check" onclick=\'toggleSelect(' + JSON.stringify(r).replace(/'/g,"&#39;") + ', event)\'>' + (sel ? 'v' : '') + '</div>' +
      '<div class="preview"><img src="' + gifUrl(r) + '" loading="lazy"></div>' +
      '<div class="info">' +
        '<div class="emotion">' + r.emotion + ' / ' + r.action + '</div>' +
        '<div class="desc">' + r.description + '</div>' +
        '<div class="tags">' + (r.tags||[]).slice(0,5).map(function(t){return '<span>'+t+'</span>'}).join('') + '</div>' +
        '<div class="meta"><span>' + r.set.split('-').slice(0,2).join('-') + '</span>' + (r.score !== undefined ? '<span class="score">'+r.score.toFixed(3)+'</span>' : '') + '</div>' +
      '</div></div>';
  }).join('');
}

// ── Download ──
async function downloadFile(url, filename) {
  const resp = await fetch(url);
  const blob = await resp.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}
function downloadGif() {
  if (!currentSticker) return;
  downloadFile(gifUrl(currentSticker), currentSticker.gif);
  showToast('Downloaded ' + currentSticker.gif);
}
async function downloadSelected() {
  if (!selectedStickers.size) { showToast('No stickers selected', 'error'); return; }
  showToast('Downloading ' + selectedStickers.size + ' stickers...');
  let i = 0;
  for (const key of selectedStickers) {
    const r = currentResults.find(function(s){return stickerKey(s)===key});
    if (r) { await downloadFile(gifUrl(r), r.gif); i++; await new Promise(function(ok){setTimeout(ok,200)}); }
  }
  showToast('Downloaded ' + i + ' stickers');
}
async function downloadAllVisible() {
  if (!currentResults.length) { showToast('No stickers to download', 'error'); return; }
  selectedStickers.clear();
  currentResults.forEach(function(r){selectedStickers.add(stickerKey(r))});
  await downloadSelected();
}

// ── Copy ──
async function copyGif() {
  if (!currentSticker) return;
  try {
    const resp = await fetch(gifUrl(currentSticker));
    const blob = await resp.blob();
    await navigator.clipboard.write([new ClipboardItem({ 'image/gif': blob })]);
    showToast('Copied to clipboard');
    closeModal();
  } catch (e) {
    showToast('Copy not supported, downloading instead', 'error');
    downloadGif();
  }
}

// ── Modal ──
function openModal(r) {
  currentSticker = r;
  document.getElementById('modal-img').src = gifUrl(r);
  document.getElementById('modal-title').textContent = r.emotion + ' / ' + r.action;
  document.getElementById('modal-desc').textContent = r.description;
  document.getElementById('modal-tags').innerHTML =
    (r.tags || []).slice(0, 6).map(function(t){return '<span>'+t+'</span>'}).join('');
  document.getElementById('modal').classList.add('active');
}
function closeModal(e) {
  if (e && e.target !== document.getElementById('modal')) return;
  document.getElementById('modal').classList.remove('active');
  currentSticker = null;
}
document.addEventListener('keydown', function(e){if(e.key==='Escape')closeModal()});

// ── Search ──
async function doSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  document.getElementById('stats').textContent = 'Searching...';
  document.getElementById('toolbar').style.display = 'flex';
  try {
    const resp = await fetch('/api/search?q=' + encodeURIComponent(q));
    const data = await resp.json();
    allCollections = data.collections;
    currentResults = data.results;
    currentView = 'home';
    if (!data.count) {
      document.getElementById('stats').textContent = 'No results for "' + data.query + '"';
      document.getElementById('results').innerHTML = '<div class="empty"><p>No stickers found</p></div>';
      return;
    }
    document.getElementById('stats').textContent = data.count + ' results for "' + data.query + '"';
    renderCards();
  } catch(e) { document.getElementById('stats').textContent = 'Error: ' + e.message; }
}
document.getElementById('q').addEventListener('keydown', function(e){if(e.key==='Enter')doSearch()});

// ── Navigation ──
function showHome() {
  document.getElementById('view-home').style.display = '';
  document.getElementById('view-collection').style.display = 'none';
  document.getElementById('nav-home').classList.add('active');
  document.getElementById('nav-collections').classList.remove('active');
  currentView = 'home';
}
function showCollections() {
  document.getElementById('view-home').style.display = 'none';
  document.getElementById('view-collection').style.display = '';
  document.getElementById('nav-home').classList.remove('active');
  document.getElementById('nav-collections').classList.add('active');
  currentView = 'collection';
}
async function openCollection(name) {
  showCollections();
  currentCollIndex = allCollections.findIndex(function(c){return c.name===name});
  document.getElementById("coll-title").textContent = name.split("-").slice(1).join("-");
  document.getElementById("coll-subtitle").textContent = "Loading...";
  document.getElementById("coll-results").innerHTML = "";
  updateCollPagination();
  try {
    const resp = await fetch("/api/collection?name=" + encodeURIComponent(name));
    const data = await resp.json();
    allCollections = data.collections;
    currentResults = data.stickers;
    document.getElementById("coll-subtitle").textContent = data.stickers.length + " stickers";
    document.getElementById("coll-stats").textContent = data.stickers.length + " stickers";
    renderCards();
  } catch(e) {
    document.getElementById("coll-subtitle").textContent = "Error loading collection";
  }
}
function updateCollPagination() {
  const prev = document.getElementById("coll-prev");
  const next = document.getElementById("coll-next");
  const info = document.getElementById("coll-nav-info");
  prev.disabled = currentCollIndex <= 0;
  next.disabled = currentCollIndex >= allCollections.length - 1;
  info.textContent = (currentCollIndex + 1) + " / " + allCollections.length;
}
function prevCollection() {
  if (currentCollIndex > 0) openCollection(allCollections[currentCollIndex - 1].name);
}
function nextCollection() {
  if (currentCollIndex < allCollections.length - 1) openCollection(allCollections[currentCollIndex + 1].name);
}

// ── Init ──
async function initCollections() {
  try {
    const resp = await fetch('/api/collections');
    const data = await resp.json();
    allCollections = data.collections;
    document.getElementById('coll-list').innerHTML = data.collections.map(function(c){
      return '<div class="coll-item" onclick="openCollection(\'' + c.name.replace(/'/g,"\\'") + '\')">' +
        '<span class="coll-name">' + c.name.split('-').slice(1).join('-') + '</span>' +
        '<span class="coll-count">' + c.count + '</span></div>';
    }).join('');
  } catch(e) {}
}
initCollections();
</script>
</body>
</html>"""


class SearchHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            limit = int(params.get("limit", [0])[0])
            if not q:
                self._json({"error": "missing q"})
                return
            results = tfidf_search(q, limit)
            self._json({"query": q, "count": len(results), "results": results})

        elif parsed.path == "/api/stats":
            self._json({"total": len(STICKERS), "has_tfidf": TFIDF_INDEX is not None})

        elif parsed.path == "/api/collections":
            self._json({"collections": COLLECTIONS})

        elif parsed.path == "/api/collection":
            params = parse_qs(parsed.query)
            name = params.get("name", [""])[0]
            stickers = STICKERS_BY_SET.get(name, [])
            self._json({"name": name, "count": len(stickers), "stickers": stickers})

        elif path.startswith("/gif/"):
            parts = path[len("/gif/"):].split("/", 1)
            if len(parts) == 2:
                set_name, gif_name = parts
                file_path = find_gif(set_name, gif_name)
                if file_path:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/gif")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                    return
            self.send_error(404)

        elif path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())

        else:
            self.send_error(404)

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


if __name__ == "__main__":
    load_data()
    port = int(os.getenv("PORT", "8000"))
    print(f"[start] Capoo Vault on http://localhost:{port}")
    HTTPServer(("0.0.0.0", port), SearchHandler).serve_forever()
