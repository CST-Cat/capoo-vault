#!/usr/bin/env python3
"""Capoo Vault — TF-IDF sticker search with local GIF preview"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote

from dotenv import load_dotenv
load_dotenv()


def default_vault_dir():
    for path in ("gifs-vault", "/app/frames", "frames/gifs"):
        if os.path.isdir(path):
            return path
    return "gifs-vault"


STICKERS = []
STICKERS_BY_SET = {}
TFIDF_INDEX = None
VAULT_DIR = os.getenv("VAULT_DIR") or default_vault_dir()
VAULT_DIRS = {}
COLLECTIONS = []
VALID_SEARCH_MODES = {"tfidf", "embedding", "hybrid"}
DEFAULT_SEARCH_LIMIT = 120
RERANK_CANDIDATE_LIMIT = 500


def default_search_mode():
    mode = os.getenv("SEARCH_MODE", "tfidf").lower()
    return mode if mode in VALID_SEARCH_MODES else "tfidf"


def search_by_mode(query, mode, limit=0):
    if mode == "embedding":
        return embedding_search(query, limit)
    if mode == "hybrid":
        return hybrid_search(query, limit)
    return tfidf_search(query, limit)


def result_key(item):
    return f"{item.get('collection') or item.get('set','')}/{item.get('gif','')}"


def norm_scores(results):
    if not results:
        return {}
    max_score = max(float(r.get("score", 0)) for r in results)
    if max_score <= 0:
        return {result_key(r): 0.0 for r in results}
    return {result_key(r): float(r.get("score", 0)) / max_score for r in results}


def field_match_score(query, sticker):
    q = query.strip().lower()
    if not q:
        return 0.0
    score = 0.0
    fields = [
        ("emotion", 1.00),
        ("action", 0.80),
        ("tags", 0.75),
        ("description", 0.45),
        ("scene", 0.25),
    ]
    for field, weight in fields:
        value = sticker.get(field, "")
        if isinstance(value, list):
            text = " ".join(str(v) for v in value).lower()
        else:
            text = str(value).lower()
        if q in text:
            score = max(score, weight)
    return score


def sticker_collection(sticker):
    path = sticker.get("path", "").replace("\\", "/")
    if "/" in path:
        return path.split("/", 1)[0]
    return sticker.get("collection") or sticker.get("set", "")


def load_data():
    global STICKERS, STICKERS_BY_SET, TFIDF_INDEX, VAULT_DIRS, COLLECTIONS
    meta_path = "data/stickers.json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            STICKERS = json.load(f)
        print(f"[load] {len(STICKERS)} annotations")
    for s in STICKERS:
        cn = sticker_collection(s)
        s["collection"] = cn
        STICKERS_BY_SET.setdefault(cn, []).append(s)
        sn = s.get("set", "")
        if sn and sn != cn:
            STICKERS_BY_SET.setdefault(sn, []).append(s)
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
    for prefix in sorted(VAULT_DIRS):
        full = VAULT_DIRS[prefix]
        gd = os.path.join(VAULT_DIR, full)
        gifs = sorted([f for f in os.listdir(gd) if f.endswith('.gif')]) if os.path.isdir(gd) else []
        COLLECTIONS.append({"name": full, "prefix": prefix, "count": len(gifs), "previews": gifs[:4]})


def find_gif(sn, gn):
    p = os.path.join(VAULT_DIR, sn, gn)
    if os.path.isfile(p):
        return p
    px = sn[:3] if len(sn) >= 3 else sn
    if px in VAULT_DIRS:
        fd = VAULT_DIRS[px]
        if fd.startswith(sn):
            p2 = os.path.join(VAULT_DIR, fd, gn)
            if os.path.isfile(p2):
                return p2
    return None


def tfidf_search(query, limit=0):
    if not TFIDF_INDEX:
        return []
    vocab = TFIDF_INDEX["vocab"]
    idf = TFIDF_INDEX["idf"]
    rows = TFIDF_INDEX["rows"]
    qv = {}
    for n in range(1, 5):
        for i in range(len(query) - n + 1):
            g = query[i:i+n]
            if g in vocab:
                idx = vocab[g]
                qv[idx] = qv.get(idx, 0) + 1
    for idx in qv:
        qv[idx] *= idf[idx]
    if not qv:
        return []
    scores = []
    for i, row in enumerate(rows):
        dot = 0
        for j, col in enumerate(row["c"]):
            if col in qv:
                dot += qv[col] * row["v"][j]
        if dot > 0:
            scores.append((i, dot))
    scores.sort(key=lambda x: -x[1])
    out = []
    for idx, sc in (scores[:limit] if limit else scores):
        s = STICKERS[idx] if idx < len(STICKERS) else {}
        out.append({"score": round(sc, 4), **s})
    return out



def embedding_search(query, limit=0):
    """Embedding API search"""
    import numpy as np
    api_key = os.getenv('OPENAI_API_KEY')
    base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    model = os.getenv('OPENAI_EMBEDDING_MODEL', 'Qwen/Qwen3-Embedding-0.6B')
    if not api_key:
        return tfidf_search(query, limit)
    
    emb_path = 'data/embeddings.npy'
    if not os.path.exists(emb_path):
        return tfidf_search(query, limit)
    
    try:
        import httpx
        # Get query embedding
        resp = httpx.post(
            f'{base_url}/embeddings',
            headers={'Authorization': f'Bearer {api_key}'},
            json={'model': model, 'input': [query]},
            timeout=30
        )
        resp.raise_for_status()
        qvec = np.array(resp.json()['data'][0]['embedding'], dtype=np.float32)
        
        # Load precomputed embeddings
        embeddings = np.load(emb_path)
        
        # Compute cosine similarity even if the stored vectors are not normalized.
        emb_norm = np.linalg.norm(embeddings, axis=1, keepdims=True)
        emb_norm[emb_norm == 0] = 1
        qnorm = np.linalg.norm(qvec)
        if qnorm == 0:
            return []
        scores = (embeddings / emb_norm) @ (qvec / qnorm)
        top = np.argsort(scores)[::-1]
        
        results = []
        for idx in top:
            if scores[idx] <= 0.1:
                break
            if limit and len(results) >= limit:
                break
            s = STICKERS[idx] if idx < len(STICKERS) else {}
            results.append({'score': round(float(scores[idx]), 4), **s})
        return results
    except Exception:
        return tfidf_search(query, limit)


def hybrid_search(query, limit=0):
    """Hybrid: embedding + TF-IDF + field match rerank."""
    final_limit = limit or DEFAULT_SEARCH_LIMIT
    tfidf_results = tfidf_search(query, RERANK_CANDIDATE_LIMIT)
    emb_results = embedding_search(query, RERANK_CANDIDATE_LIMIT)

    if not emb_results:
        return tfidf_results[:final_limit]

    tfidf_norm = norm_scores(tfidf_results)
    emb_norm = norm_scores(emb_results)
    candidates = {}
    for r in tfidf_results + emb_results:
        candidates[result_key(r)] = r

    reranked = []
    for key, item in candidates.items():
        emb_score = emb_norm.get(key, 0.0)
        tfidf_score = tfidf_norm.get(key, 0.0)
        field_score = field_match_score(query, item)
        final_score = 0.55 * emb_score + 0.30 * tfidf_score + 0.15 * field_score
        out = {**item, "score": round(final_score, 4), "method": "hybrid"}
        reranked.append(out)

    reranked.sort(key=lambda x: -x["score"])
    return reranked[:final_limit]



HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capoo Vault</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--primary:#cc785c;--primary-active:#a9583e;--ink:#141413;--body:#3d3d3a;--muted:#6c6a64;--muted-soft:#8e8b82;--hairline:#e6dfd8;--hairline-soft:#ebe6df;--canvas:#faf9f5;--surface-soft:#f5f0e8;--surface-card:#efe9de;--surface-dark:#181715;--preview-bg:#fff;--on-primary:#fff;--on-dark:#faf9f5;--on-dark-soft:#a09d96;--accent-teal:#5db8a6;--error:#c64545;--r-sm:6px;--r-md:8px;--r-lg:12px;--r-xl:16px;--sb-w:240px;--sb-cw:52px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,system-ui,sans-serif;background:var(--canvas);color:var(--ink);min-height:100vh;display:flex}

.sidebar{width:var(--sb-w);min-height:100vh;background:var(--canvas);border-right:1px solid var(--hairline);box-shadow:2px 0 8px rgba(20,20,19,.04);display:flex;flex-direction:column;position:fixed;left:0;top:0;bottom:0;z-index:100;overflow:hidden;transition:width .2s}
.sidebar.collapsed{width:var(--sb-cw)}
.sidebar-brand{padding:20px 16px;border-bottom:1px solid var(--hairline);display:flex;align-items:center;justify-content:space-between;min-height:64px}
.sidebar-brand .brand-text{overflow:hidden;white-space:nowrap}
.sidebar-brand h1{font-family:'Playfair Display',serif;font-size:20px;font-weight:500;letter-spacing:-.3px}
.sidebar-brand p{font-size:12px;color:var(--muted);margin-top:2px}
.sidebar.collapsed .brand-text,.sidebar.collapsed .nav-label,.sidebar.collapsed .sidebar-section,.sidebar.collapsed .sidebar-collections,.sidebar.collapsed .sidebar-download-all span{display:none}
.sidebar .nav-icon{display:none}
.sidebar.collapsed .nav-icon{display:inline}
.sidebar-toggle{width:28px;height:28px;border-radius:var(--r-sm);background:0 0;border:1px solid var(--hairline);color:var(--muted);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
.sidebar-toggle:hover{background:var(--surface-card)}
.sidebar-nav{padding:12px 8px}
.sidebar-nav a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:var(--r-md);color:var(--muted);text-decoration:none;font-size:14px;font-weight:500;cursor:pointer;white-space:nowrap;overflow:hidden}
.sidebar-nav a:hover,.sidebar-nav a.active{background:var(--surface-card);color:var(--ink)}
.sidebar.collapsed .sidebar-nav a{justify-content:center;padding:10px}
.sidebar-section{padding:8px 16px 4px;font-size:11px;font-weight:500;color:var(--muted-soft);letter-spacing:1.5px;text-transform:uppercase}
.sidebar-collections{flex:1;overflow-y:auto;padding:0 8px 12px}
.sidebar-collections .coll-item{display:flex;align-items:center;justify-content:space-between;padding:7px 12px;border-radius:var(--r-sm);color:var(--muted);font-size:13px;cursor:pointer;white-space:nowrap;overflow:hidden}
.sidebar-collections .coll-item:hover,.sidebar-collections .coll-item.active{background:var(--surface-card);color:var(--ink)}
.sidebar-collections .coll-item.active .coll-count{background:var(--canvas);color:var(--primary)}
.sidebar-collections .coll-item .coll-count{font-size:11px;color:var(--muted-soft);background:var(--surface-soft);padding:2px 8px;border-radius:9999px;flex-shrink:0}
.sidebar-collections .coll-item .coll-name{overflow:hidden;text-overflow:ellipsis;max-width:150px}
.sidebar-download-all{padding:12px 8px;border-top:1px solid var(--hairline)}
.sidebar-download-all button{width:100%;padding:9px 12px;background:var(--primary);color:var(--on-primary);border:none;border-radius:var(--r-md);font-size:13px;font-weight:500;font-family:'Inter',sans-serif;cursor:pointer}
.sidebar-download-all button:hover{background:var(--primary-active)}
.sidebar.collapsed .sidebar-download-all button{padding:9px 4px;font-size:0}
.sidebar.collapsed .sidebar-download-all button::after{content:"\2193";font-size:14px}

.main{flex:1;margin-left:var(--sb-w);min-height:100vh;display:flex;flex-direction:column;transition:margin-left .2s}
body.sidebar-collapsed .main{margin-left:var(--sb-cw)}
.header{padding:48px 32px 32px;border-bottom:1px solid var(--hairline)}
.header-top{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}
.header h2{font-family:'Playfair Display',serif;font-size:36px;font-weight:400;line-height:1.1;letter-spacing:-.5px;margin-bottom:8px}
.header .subtitle{font-size:15px;color:var(--muted)}
.mode-selector{position:relative;flex-shrink:0}
.mode-btn{min-width:132px;height:38px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--canvas);color:var(--ink);border:1px solid var(--hairline);border-radius:var(--r-md);font-size:13px;font-weight:500;font-family:'Inter',sans-serif;cursor:pointer;box-shadow:0 1px 2px rgba(20,20,19,.04)}
.mode-btn:hover,.mode-btn.open{background:var(--surface-soft);border-color:var(--primary)}
.mode-btn .arrow{font-size:10px;color:var(--muted);transition:transform .15s}
.mode-btn.open .arrow{transform:rotate(180deg)}
.mode-dropdown{display:none;position:absolute;right:0;top:46px;width:220px;background:var(--canvas);border:1px solid var(--hairline);border-radius:var(--r-md);box-shadow:0 16px 40px rgba(20,20,19,.14);padding:6px;z-index:20}
.mode-dropdown.show{display:block;animation:dd .12s ease-out}
@keyframes dd{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
.mode-option{padding:10px 12px;border-radius:var(--r-sm);cursor:pointer;color:var(--ink)}
.mode-option:hover,.mode-option.active{background:var(--surface-card)}
.mode-option.active{box-shadow:inset 3px 0 0 var(--primary)}
.mode-option-title{font-size:13px;font-weight:600;line-height:1.3}
.mode-desc{font-size:12px;color:var(--muted);line-height:1.35;margin-top:2px}
.search-wrap{max-width:640px;padding:24px 32px 0}
.search-box{display:flex;gap:8px}
.search-box input{flex:1;padding:12px 16px;font-size:15px;font-family:'Inter',sans-serif;background:var(--canvas);border:1px solid var(--hairline);border-radius:var(--r-md);color:var(--ink);outline:none;height:44px}
.search-box input:focus{border-color:var(--primary)}
.search-box input::placeholder{color:var(--muted-soft)}
.search-box button{padding:12px 20px;background:var(--primary);color:var(--on-primary);border:none;border-radius:var(--r-md);font-size:14px;font-weight:500;font-family:'Inter',sans-serif;cursor:pointer;height:44px}
.search-box button:hover{background:var(--primary-active)}
.toolbar{display:flex;align-items:center;justify-content:space-between;padding:16px 32px 0}
.toolbar .stats{font-size:14px;color:var(--muted)}
.toolbar .actions{display:flex;gap:8px}
.toolbar .actions button{padding:8px 14px;background:var(--surface-card);color:var(--ink);border:1px solid var(--hairline);border-radius:var(--r-sm);font-size:13px;font-weight:500;font-family:'Inter',sans-serif;cursor:pointer}
.toolbar .actions button:hover{background:var(--surface-soft)}
.toolbar .actions button.primary{background:var(--primary);color:var(--on-primary);border-color:var(--primary)}
.toolbar .actions button.primary:hover{background:var(--primary-active)}
.results{flex:1;padding:16px 32px 48px;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;align-content:start}
.card{background:var(--surface-card);border-radius:var(--r-lg);overflow:hidden;border:1px solid var(--hairline-soft);transition:transform .2s,box-shadow .2s;cursor:pointer;position:relative}
.card:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(20,20,19,.07)}
.card.selected{border-color:var(--primary);box-shadow:0 0 0 2px rgba(204,120,92,.3)}
.card .select-check{position:absolute;top:8px;left:8px;width:22px;height:22px;border-radius:var(--r-sm);background:var(--canvas);border:2px solid var(--hairline);display:flex;align-items:center;justify-content:center;font-size:13px;color:transparent;z-index:2}
.card.selected .select-check{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}
.card .preview{width:100%;aspect-ratio:1;background:var(--preview-bg);display:flex;align-items:center;justify-content:center;overflow:hidden}
.card .preview img{max-width:100%;max-height:100%;object-fit:contain;background:var(--preview-bg)}
.card .info{padding:12px}
.card .emotion{font-family:'Playfair Display',serif;font-size:15px;font-weight:500;line-height:1.3}
.card .desc{font-size:12px;color:var(--body);margin-top:6px;line-height:1.4}
.card .tags{margin-top:8px;display:flex;flex-wrap:wrap;gap:3px}
.card .tags span{background:var(--surface-soft);color:var(--muted);font-size:11px;font-weight:500;padding:2px 8px;border-radius:var(--r-sm)}
.card .meta{display:flex;justify-content:space-between;align-items:center;margin-top:8px;font-size:11px;color:var(--muted-soft)}
.card .set-link{max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:0 0;border:0;color:var(--muted);font:inherit;font-weight:500;cursor:pointer;padding:2px 0;text-align:left}
.card .set-link:hover{color:var(--primary)}
.card .score{font-family:'JetBrains Mono',monospace}

.folder-grid{flex:1;padding:24px 32px 48px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px;align-content:start}
.folder-card{background:var(--surface-card);border-radius:var(--r-lg);border:1px solid var(--hairline-soft);overflow:hidden;cursor:pointer;transition:transform .2s,box-shadow .2s}
.folder-card:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(20,20,19,.07)}
.folder-card .folder-preview{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:var(--preview-bg);aspect-ratio:2/1}
.folder-card .folder-preview img{width:100%;height:100%;object-fit:contain;background:var(--preview-bg)}
.folder-card .folder-info{padding:14px 16px}
.folder-card .folder-name{font-family:'Playfair Display',serif;font-size:15px;font-weight:500;line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.folder-card .folder-meta{display:flex;justify-content:space-between;align-items:center;margin-top:6px;font-size:12px;color:var(--muted)}

.pagination{display:flex;align-items:center;justify-content:center;gap:4px;padding:16px 32px 48px;flex-wrap:wrap}
.page-btn{min-width:32px;height:32px;padding:0 6px;display:inline-flex;align-items:center;justify-content:center;background:transparent;color:var(--ink);border:1px solid var(--hairline);border-radius:var(--r-sm);font-size:13px;font-weight:500;font-family:'Inter',sans-serif;cursor:pointer;transition:all .15s}
.page-btn:hover{background:var(--surface-soft);color:var(--ink);border-color:var(--hairline)}
.page-btn.active{background:var(--primary);color:var(--on-primary);border-color:var(--primary)}
.page-btn:disabled{opacity:.35;cursor:not-allowed;background:transparent;color:var(--muted-soft)}
.page-ellipsis{min-width:32px;height:32px;display:inline-flex;align-items:center;justify-content:center;font-size:13px;color:var(--muted-soft);letter-spacing:2px;user-select:none}

.empty{text-align:center;padding:96px 24px;color:var(--muted-soft);grid-column:1/-1}
.empty p{font-size:16px;line-height:1.55}

.modal-overlay{display:none;position:fixed;inset:0;background:rgba(20,20,19,.6);backdrop-filter:blur(4px);z-index:1000;align-items:center;justify-content:center;padding:24px}
.modal-overlay.active{display:flex}
.modal{background:var(--canvas);border-radius:var(--r-xl);max-width:420px;width:100%;overflow:hidden;box-shadow:0 24px 64px rgba(20,20,19,.2);animation:mi .2s ease-out;position:relative}
@keyframes mi{from{opacity:0;transform:scale(.95) translateY(8px)}to{opacity:1;transform:scale(1) translateY(0)}}
.modal-close{position:absolute;top:12px;right:12px;width:32px;height:32px;border-radius:50%;background:rgba(20,20,19,.5);color:#fff;border:none;font-size:16px;cursor:pointer;z-index:10;display:flex;align-items:center;justify-content:center}
.modal-close:hover{background:rgba(20,20,19,.8)}
.modal .modal-preview{width:100%;aspect-ratio:1;background:var(--preview-bg);display:flex;align-items:center;justify-content:center}
.modal .modal-preview img{max-width:100%;max-height:100%;object-fit:contain;background:var(--preview-bg)}
.modal .modal-info{padding:20px}
.modal .modal-title{font-family:'Playfair Display',serif;font-size:20px;font-weight:500;margin-bottom:4px}
.modal .modal-desc{font-size:14px;color:var(--body);line-height:1.55;margin-bottom:12px}
.modal .modal-tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:20px}
.modal .modal-tags span{background:var(--surface-soft);color:var(--muted);font-size:12px;font-weight:500;padding:3px 10px;border-radius:var(--r-sm)}
.modal .modal-actions{display:flex;gap:8px}
.modal .modal-actions button{flex:1;padding:12px 16px;border:none;border-radius:var(--r-md);font-size:14px;font-weight:500;font-family:'Inter',sans-serif;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px}
.modal .btn-copy{background:var(--primary);color:var(--on-primary)}
.modal .btn-copy:hover{background:var(--primary-active)}
.modal .btn-download{background:var(--surface-card);color:var(--ink);border:1px solid var(--hairline)!important}
.modal .btn-download:hover{background:var(--surface-soft)}

.toast-container{position:fixed;top:24px;left:50%;transform:translateX(-50%);z-index:2000;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:var(--canvas);color:var(--ink);padding:12px 20px;border-radius:var(--r-md);font-size:14px;font-weight:500;font-family:'Inter',sans-serif;box-shadow:0 8px 24px rgba(20,20,19,.2);animation:ti .25s ease-out,to .25s ease-in 2s forwards;border:1px solid var(--hairline);display:flex;align-items:center;gap:8px;pointer-events:auto}
.toast.success{border-left:3px solid var(--accent-teal)}
.toast.error{border-left:3px solid var(--error)}
@keyframes ti{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:translateY(0)}}
@keyframes to{from{opacity:1}to{opacity:0;transform:translateY(-12px)}}

.footer{background:var(--surface-dark);color:var(--on-dark-soft);text-align:center;padding:24px 32px;font-size:13px;margin-left:var(--sb-w);transition:margin-left .2s}
body.sidebar-collapsed .footer{margin-left:var(--sb-cw)}
.footer a{color:var(--on-dark);text-decoration:none}
.footer a:hover{color:var(--primary)}

@media(max-width:768px){.sidebar{display:none}.main,.footer{margin-left:0}.results,.folder-grid{grid-template-columns:repeat(2,1fr);gap:12px;padding:16px}.header{padding:32px 16px 24px}.header-top{align-items:flex-start}.header h2{font-size:28px}.mode-btn{min-width:118px}.mode-dropdown{right:0;width:204px}.search-wrap,.toolbar,.pagination{padding-left:16px;padding-right:16px}}
</style>
</head>
<body>

<div class="sidebar" id="sidebar">
  <div class="sidebar-brand">
    <div class="brand-text"><h1>Capoo Vault</h1><p>10,238 stickers</p></div>
    <button class="sidebar-toggle" onclick="toggleSidebar()">&laquo;</button>
  </div>
  <nav class="sidebar-nav">
    <a class="active" onclick="showHome()" id="nav-home"><span class="nav-label">Search</span><span class="nav-icon">S</span></a>
    <a onclick="showCollections()" id="nav-collections"><span class="nav-label">Collections</span><span class="nav-icon">C</span></a>
  </nav>
  <div class="sidebar-section">Collections</div>
  <div class="sidebar-collections" id="coll-list"></div>
  <div class="sidebar-download-all"><button onclick="downloadAllVisible()"><span>Download All</span></button></div>
</div>

<div class="main">
  <div id="view-home">
    <div class="header">
      <div class="header-top">
        <div>
          <h2>Search Stickers</h2>
          <p class="subtitle">Find the perfect Capoo sticker by emotion, action, or description</p>
        </div>
        <div class="mode-selector">
          <button class="mode-btn" id="mode-btn" onclick="toggleModeDropdown()">
            <span id="mode-label">TF-IDF</span>
            <span class="arrow">&#9662;</span>
          </button>
          <div class="mode-dropdown" id="mode-dropdown">
            <div class="mode-option active" data-mode="tfidf" onclick="setMode('tfidf')">
              <div class="mode-option-title">TF-IDF</div>
              <div class="mode-desc">Fast keyword matching</div>
            </div>
            <div class="mode-option" data-mode="embedding" onclick="setMode('embedding')">
              <div class="mode-option-title">Embedding</div>
              <div class="mode-desc">Semantic search via API</div>
            </div>
            <div class="mode-option" data-mode="hybrid" onclick="setMode('hybrid')">
              <div class="mode-option-title">Hybrid</div>
              <div class="mode-desc">TF-IDF + Embedding combined</div>
            </div>
          </div>
        </div>
      </div>
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
    <div class="results" id="results"><div class="empty"><p>Search for Capoo stickers by keyword</p></div></div>
  </div>

  <div id="view-collections" style="display:none">
    <div class="header">
      <h2>Collections</h2>
      <p class="subtitle" id="coll-grid-subtitle"></p>
    </div>
    <div class="folder-grid" id="folder-grid"></div>
    <div class="pagination" id="folder-pagination"></div>
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
    <div class="pagination" id="coll-pagination"></div>
  </div>
</div>

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
var curSticker=null,selected=new Set(),curResults=[],curView='home',allColl=[],curCollIdx=-1,activeCollName='',FOLDER_PAGE=12,folderPg=0,collectionReqId=0;
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function gifSet(r){return r.collection||r.set||''}
function gifUrl(r){return'/gif/'+encodeURIComponent(gifSet(r))+'/'+encodeURIComponent(r.gif)}
function sKey(r){return gifSet(r)+'/'+r.gif}

/* Sidebar */
function toggleSidebar(){var s=document.getElementById('sidebar'),c=s.classList.toggle('collapsed');document.body.classList.toggle('sidebar-collapsed',c);s.querySelector('.sidebar-toggle').innerHTML=c?'&raquo;':'&laquo;';localStorage.setItem('sb-collapsed',c?'1':'0')}
if(localStorage.getItem('sb-collapsed')==='1'){document.getElementById('sidebar').classList.add('collapsed');document.body.classList.add('sidebar-collapsed');document.querySelector('.sidebar-toggle').innerHTML='&raquo;'}

/* Toast */
function showToast(m,t){t=t||'success';var c=document.getElementById('toasts'),el=document.createElement('div');el.className='toast '+t;el.textContent=m;c.appendChild(el);setTimeout(function(){el.remove()},2500)}

/* Active collection */
function setActiveCollection(name){activeCollName=name||'';document.querySelectorAll('.coll-item').forEach(function(el){el.classList.toggle('active',el.dataset.name===activeCollName)})}

/* Selection */
function toggleSel(r,e){e.stopPropagation();var k=sKey(r);selected.has(k)?selected.delete(k):selected.add(k);renderCards()}
function toggleSelByIndex(i,e){toggleSel(curResults[i],e)}
function selectAll(){curResults.forEach(function(r){selected.add(sKey(r))});renderCards();showToast(selected.size+' selected')}
function deselectAll(){selected.clear();renderCards()}
function renderCards(){var id=curView==='home'?'results':'coll-results';document.getElementById(id).innerHTML=curResults.map(function(r,i){var k=sKey(r),sel=selected.has(k),meta=gifSet(r).split('-').slice(0,2).join('-');return'<div class="card '+(sel?'selected':'')+'" onclick="openModalByIndex('+i+')"><div class="select-check" onclick="toggleSelByIndex('+i+',event)">'+(sel?'v':'')+'</div><div class="preview"><img src="'+gifUrl(r)+'" loading="lazy"></div><div class="info"><div class="emotion">'+esc(r.emotion)+' / '+esc(r.action)+'</div><div class="desc">'+esc(r.description)+'</div><div class="tags">'+(r.tags||[]).slice(0,5).map(function(t){return'<span>'+esc(t)+'</span>'}).join('')+'</div><div class="meta"><button class="set-link" onclick="openCardCollection('+i+',event)" title="'+esc(gifSet(r))+'">'+esc(meta)+'</button>'+(r.score!==undefined?'<span class="score">'+esc(r.score.toFixed(3))+'</span>':'')+'</div></div></div>'}).join('')}

/* Folder Grid */
function clampFolderPage(pg){var tp=Math.ceil(allColl.length/FOLDER_PAGE);return tp>0?Math.max(0,Math.min(pg,tp-1)):0}
function renderFolders(){folderPg=clampFolderPage(folderPg);var s=folderPg*FOLDER_PAGE,e=Math.min(s+FOLDER_PAGE,allColl.length),pg=allColl.slice(s,e);document.getElementById('folder-grid').innerHTML=pg.length?pg.map(function(c,i){var idx=s+i,pv=(c.previews||[]).slice(),html=pv.map(function(g){return'<img src="/gif/'+encodeURIComponent(c.name)+'/'+encodeURIComponent(g)+'" loading="lazy">'}).join('');while(pv.length<4){html+='<div></div>';pv.push(null)}return'<div class="folder-card" onclick="openCollectionByIndex('+idx+')"><div class="folder-preview">'+html+'</div><div class="folder-info"><div class="folder-name">'+esc(c.name.split('-').slice(1).join('-'))+'</div><div class="folder-meta"><span>'+esc(c.count)+' stickers</span><span>'+esc(c.prefix)+'</span></div></div></div>'}).join(''):'<div class="empty"><p>No collections found</p></div>';renderFolderPager()}
function goFolderPage(pg){folderPg=clampFolderPage(pg);renderFolders()}
function renderFolderPager(){var tp=Math.ceil(allColl.length/FOLDER_PAGE),cur=folderPg,h=[];if(tp<=1){document.getElementById('folder-pagination').innerHTML='';return}h.push('<button class="page-btn" onclick="goFolderPage('+(cur-1)+')"'+(cur<=0?' disabled':'')+'>‹</button>');var range=[];for(var i=0;i<tp;i++){if(i===0||i===tp-1||Math.abs(i-cur)<=2)range.push(i)}var last=-1;for(var j=0;j<range.length;j++){var p=range[j];if(last>=0&&p-last>1)h.push('<span class="page-ellipsis">...</span>');h.push('<button class="page-btn'+(p===cur?' active':'')+'" onclick="goFolderPage('+p+')">'+(p+1)+'</button>');last=p}h.push('<button class="page-btn" onclick="goFolderPage('+(cur+1)+')"'+(cur>=tp-1?' disabled':'')+'>›</button>');document.getElementById('folder-pagination').innerHTML=h.join('')}
function openCollectionByIndex(i){if(allColl[i])openCollection(allColl[i].name)}
function openCardCollection(i,e){e.stopPropagation();var r=curResults[i],name=r&&gifSet(r);if(name)openCollection(name)}

/* Download */
async function dlFile(url,fn){var r=await fetch(url),b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=fn;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(a.href)}
function downloadGif(){if(!curSticker)return;dlFile(gifUrl(curSticker),curSticker.gif);showToast('Downloaded '+curSticker.gif)}
async function downloadSelected(){if(!selected.size){showToast('No stickers selected','error');return}showToast('Downloading '+selected.size+'...');var i=0;for(var k of selected){var r=curResults.find(function(s){return sKey(s)===k});if(r){await dlFile(gifUrl(r),r.gif);i++;await new Promise(function(ok){setTimeout(ok,200)})}}showToast('Downloaded '+i+' stickers')}
async function downloadAllVisible(){if(!curResults.length){showToast('No stickers','error');return}selected.clear();curResults.forEach(function(r){selected.add(sKey(r))});await downloadSelected()}

/* Copy */
async function copyGif(){if(!curSticker)return;try{var r=await fetch(gifUrl(curSticker)),b=await r.blob();await navigator.clipboard.write([new ClipboardItem({'image/gif':b})]);showToast('Copied');closeModal()}catch(e){showToast('Copy failed, downloading','error');downloadGif()}}

/* Modal */
function openModalByIndex(i){if(curResults[i])openModal(curResults[i])}
function openModal(r){curSticker=r;document.getElementById('modal-img').src=gifUrl(r);document.getElementById('modal-title').textContent=r.emotion+' / '+r.action;document.getElementById('modal-desc').textContent=r.description;document.getElementById('modal-tags').innerHTML=(r.tags||[]).slice(0,6).map(function(t){return'<span>'+esc(t)+'</span>'}).join('');document.getElementById('modal').classList.add('active')}
function closeModal(e){if(e&&e.target!==document.getElementById('modal'))return;document.getElementById('modal').classList.remove('active');curSticker=null}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeModal()});


/* Mode Selector */
var searchMode = '__DEFAULT_SEARCH_MODE__';
function toggleModeDropdown() {
  var dd = document.getElementById('mode-dropdown');
  var btn = document.getElementById('mode-btn');
  dd.classList.toggle('show');
  btn.classList.toggle('open');
}
function setMode(mode, rerun) {
  if (['tfidf','embedding','hybrid'].indexOf(mode) === -1) mode = 'tfidf';
  searchMode = mode;
  var labels = {tfidf:'TF-IDF', embedding:'Embedding', hybrid:'Hybrid'};
  document.getElementById('mode-label').textContent = labels[mode];
  document.querySelectorAll('.mode-option').forEach(function(el) {
    el.classList.toggle('active', el.dataset.mode === mode);
  });
  document.getElementById('mode-dropdown').classList.remove('show');
  document.getElementById('mode-btn').classList.remove('open');
  // Re-search if there's a query
  var q = document.getElementById('q').value.trim();
  if (rerun !== false && q) doSearch();
}
// Close dropdown on outside click
document.addEventListener('click', function(e) {
  if (!e.target.closest('.mode-selector')) {
    document.getElementById('mode-dropdown').classList.remove('show');
    document.getElementById('mode-btn').classList.remove('open');
  }
});
/* Search */
async function doSearch(){var q=document.getElementById('q').value.trim();if(!q)return;document.getElementById('stats').textContent='Searching...';document.getElementById('toolbar').style.display='flex';try{var r=await fetch('/api/search?q='+encodeURIComponent(q)+'&mode='+searchMode),d=await r.json();curResults=d.results;curView='home';if(!d.count){document.getElementById('stats').textContent='No results';document.getElementById('results').innerHTML='<div class="empty"><p>No stickers found</p></div>';return}document.getElementById('stats').textContent=d.count+' results for "'+d.query+'"';renderCards()}catch(e){document.getElementById('stats').textContent='Error: '+e.message}}
document.getElementById('q').addEventListener('keydown',function(e){if(e.key==='Enter')doSearch()});
setMode(searchMode, false);

/* Navigation + History */
function hideAll(){document.getElementById('view-home').style.display='none';document.getElementById('view-collections').style.display='none';document.getElementById('view-collection').style.display='none'}
function pushSt(st){history.pushState(st,'','#'+st.v+(st.c?'/'+encodeURIComponent(st.c):''))}
function showHome(push){hideAll();setActiveCollection('');document.getElementById('view-home').style.display='';document.getElementById('nav-home').classList.add('active');document.getElementById('nav-collections').classList.remove('active');curView='home';if(push!==false)pushSt({v:'home'})}
function showCollections(push){hideAll();setActiveCollection('');document.getElementById('view-collections').style.display='';document.getElementById('nav-home').classList.remove('active');document.getElementById('nav-collections').classList.add('active');curView='folders';renderFolders();if(push!==false)pushSt({v:'collections'})}
async function openCollection(name,push){var req=++collectionReqId;hideAll();setActiveCollection(name);document.getElementById('view-collection').style.display='';document.getElementById('nav-home').classList.remove('active');document.getElementById('nav-collections').classList.add('active');curView='collection';curCollIdx=allColl.findIndex(function(c){return c.name===name});document.getElementById('coll-title').textContent=name.split('-').slice(1).join('-');document.getElementById('coll-subtitle').textContent='Loading...';document.getElementById('coll-stats').textContent='';document.getElementById('coll-results').innerHTML='';renderCollPager();if(push!==false)pushSt({v:'collection',c:name});try{var r=await fetch('/api/collection?name='+encodeURIComponent(name)),d=await r.json();if(req!==collectionReqId||activeCollName!==name)return;curResults=d.stickers;document.getElementById('coll-subtitle').textContent=d.stickers.length+' stickers';document.getElementById('coll-stats').textContent=d.stickers.length+' stickers';renderCards()}catch(e){if(req===collectionReqId)document.getElementById('coll-subtitle').textContent='Error'}}
function renderCollPager(){var h=[],cur=curCollIdx,total=allColl.length;if(cur<0||total<=1){document.getElementById('coll-pagination').innerHTML='';return}h.push('<button class="page-btn" onclick="prevCollection()"'+(cur<=0?' disabled':'')+'>‹</button>');var range=[];for(var i=0;i<total;i++){if(i===0||i===total-1||Math.abs(i-cur)<=2)range.push(i)}var last=-1;for(var j=0;j<range.length;j++){var p=range[j];if(last>=0&&p-last>1)h.push('<span class="page-ellipsis">...</span>');h.push('<button class="page-btn'+(p===cur?' active':'')+'" onclick="openCollection(allColl['+p+'].name)">'+(p+1)+'</button>');last=p}h.push('<button class="page-btn" onclick="nextCollection()"'+(cur>=total-1?' disabled':'')+'>›</button>');document.getElementById('coll-pagination').innerHTML=h.join('')}
function prevCollection(){if(curCollIdx>0)openCollection(allColl[curCollIdx-1].name)}
function nextCollection(){if(curCollIdx<allColl.length-1)openCollection(allColl[curCollIdx+1].name)}

/* Browser back/forward */
window.addEventListener('popstate',function(e){var s=e.state;if(!s){routeFromHash();return}if(s.v==='home')showHome(false);else if(s.v==='collections')showCollections(false);else if(s.v==='collection'&&s.c)openCollection(s.c,false)});

function routeFromHash(){var h=location.hash.slice(1);if(!h||h==='home')showHome(false);else if(h==='collections')showCollections(false);else if(h.indexOf('collection/')===0)openCollection(decodeURIComponent(h.slice(11)),false)}

/* Init */
(async function(){try{var r=await fetch('/api/collections'),d=await r.json();allColl=d.collections;document.getElementById('coll-grid-subtitle').textContent=allColl.length+' sticker sets';document.getElementById('coll-list').innerHTML=allColl.map(function(c,i){return'<div class="coll-item" data-name="'+esc(c.name)+'" onclick="openCollectionByIndex('+i+')"><span class="coll-name">'+esc(c.name.split('-').slice(1).join('-'))+'</span><span class="coll-count">'+esc(c.count)+'</span></div>'}).join('');setActiveCollection(activeCollName);if(curView==='folders')renderFolders();routeFromHash()}catch(e){}})();
</script>
</body>
</html>"""

HTML = HTML.replace("__DEFAULT_SEARCH_MODE__", default_search_mode())


class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p = urlparse(self.path); path = unquote(p.path)
        if p.path == "/api/search":
            q = parse_qs(p.query).get("q",[""])[0]
            mode = parse_qs(p.query).get("mode",[default_search_mode()])[0].lower()
            if mode not in VALID_SEARCH_MODES:
                mode = default_search_mode()
            try:
                lim = int(parse_qs(p.query).get("limit",[0])[0])
            except ValueError:
                return self._j({"error":"invalid limit"}, 400)
            if lim < 0:
                return self._j({"error":"invalid limit"}, 400)
            if lim == 0:
                lim = DEFAULT_SEARCH_LIMIT
            if lim > 500:
                lim = 500
            if not q: return self._j({"error":"missing q"}, 400)
            r = search_by_mode(q, mode, lim)
            return self._j({"query":q,"mode":mode,"count":len(r),"results":r})
        if p.path == "/api/stats": return self._j({"total":len(STICKERS)})
        if p.path == "/api/collections": return self._j({"collections":COLLECTIONS})
        if p.path == "/api/collection":
            n = parse_qs(p.query).get("name",[""])[0]; s = STICKERS_BY_SET.get(n,[])
            return self._j({"name":n,"count":len(s),"stickers":s})
        if path.startswith("/gif/"):
            parts = path[5:].split("/",1)
            if len(parts)==2:
                fp = find_gif(parts[0],parts[1])
                if fp:
                    self.send_response(200); self.send_header("Content-Type","image/gif")
                    self.send_header("Cache-Control","public,max-age=86400"); self.end_headers()
                    with open(fp,"rb") as f: self.wfile.write(f.read())
                    return
            return self.send_error(404)
        if path in ("/","/index.html"):
            self.send_response(200); self.send_header("Content-Type","text/html;charset=utf-8")
            self.end_headers(); self.wfile.write(HTML.encode()); return
        self.send_error(404)
    def _j(self,d,status=200):
        self.send_response(status); self.send_header("Content-Type","application/json;charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
        self.wfile.write(json.dumps(d,ensure_ascii=False).encode())


if __name__ == "__main__":
    load_data()
    port = int(os.getenv("PORT","8989"))
    print(f"[start] Capoo Vault on http://localhost:{port}")
    HTTPServer(("0.0.0.0",port),H).serve_forever()
