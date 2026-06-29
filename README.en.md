<div align="center">

# Capoo Vault

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | **English**

</div>

<div align="center">

**10,000+ BugCat Capoo (貓貓蟲咖波) sticker annotations with semantic search.**

</div>

Capoo Vault is a semantic annotation dataset for Capoo stickers, containing structured annotations (emotion, action, scene, description, tags) for 10,238 GIF stickers. Suitable for chatbots, sticker recommendation, vector search, and more.

## Live Preview

You can preview the sticker collections and search experience here: https://cst-cat.github.io/capoo-gallery/

The preview site uses compressed GIF assets for fast online browsing and search. For the full Docker/local experience, download the `gifs-vault` asset pack.

## GIF Asset Download

The `gifs-vault` asset pack contains the GIF files required by Docker and the local preview server. Download it from either source:

- [GitHub Releases](https://github.com/CST-Cat/capoo-vault/releases/tag/gifs-vault-20260629)
- [Google Drive mirror](https://drive.google.com/drive/folders/17jOZsG6EsqDpFCZP7jKukocQXndHG4Kx?usp=sharing)
- [Quark Cloud mirror](https://pan.quark.cn/s/83a6fbba44c6?pwd=xdU9) (extraction code: `xdU9`)

After downloading, use `capoo-vault-gifs-vault-20260629.sha256` from the release to verify the split archive files.

## Dataset Size

| Source | Count | Status |
|--------|-------|--------|
| gifs_webp | 3,982 | ✅ 100% |
| gifs | 5,843 | ✅ 100% |
| gifs_tgs | 413 | ✅ 100% |
| **Total** | **10,238** | **100%** |

## Annotation Format

Each sticker has a corresponding JSON file:

```json
{
  "gif": "001-file_457.gif",
  "set": "013-CAPOO-SP-capoo_sp_animated",
  "emotion": "happy",
  "action": "waving hello",
  "scene": "white background",
  "description": "Capoo raises its little paw and waves hello enthusiastically",
  "tags": ["capoo", "greeting", "waving", "happy", "cute", "hello", "blue cat", "sticker"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `gif` | string | GIF filename |
| `set` | string | Sticker pack name |
| `emotion` | string | Primary emotion |
| `action` | string | Action description |
| `scene` | string | Scene description |
| `description` | string | 15-25 character description |
| `tags` | string[] | 5-8 tags |

## Directory Structure

```
capoo-vault/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── .env.example          # Environment variable template
├── requirements.txt
├── build_index.py        # Build search index
├── search_server.py      # Search server (TF-IDF + Embedding)
├── gifs-vault/           # GIF assets mounted by Docker; download/extract separately
├── data/
│   ├── stickers.json     # Search metadata
│   └── tfidf_index.json  # TF-IDF search index
├── docs/
│   ├── spec.md           # Annotation specification
│   ├── annotation_workflow.md  # Annotation workflow
│   ├── annotation_summary.md   # Lessons learned
│   └── capoo-all-sticker-links-combined.md  # Sticker sources
└── annotations/
    ├── gifs/             # 10,238 annotation JSONs
    └── batches.json
```

## Quick Start

### 1. Docker (Recommended)

```bash
# Download the GIF asset archive and place it in the capoo-vault project root.
# Download all capoo-vault-gifs-vault-YYYYMMDD.7z.00* volume files from GitHub Releases, Google Drive, or the Quark Cloud mirror.
# After extraction, the layout should be ./gifs-vault/<sticker-pack>/*.gif
7z x capoo-vault-gifs-vault-YYYYMMDD.7z.001

# Copy environment variable template
cp .env.example .env

# Edit .env and fill in your Embedding API Key
# Supports OpenAI / Jina / custom compatible endpoints

# Build and start
docker compose up -d

# Open http://localhost:8989
```

Docker Compose mounts host `./gifs-vault` to container `/app/gifs-vault`.
If you use a custom location, set `VAULT_DIR` accordingly; the default container value is `VAULT_DIR=/app/gifs-vault`.
Do not extract the archive into an extra nested path like `gifs-vault/gifs-vault/`.
Windows users can open the `.7z.001` volume with 7-Zip. On Linux, install `p7zip-full` or `7zip` and run the command above.

### 2. Local

```bash
cp .env.example .env
# Edit .env and fill in your API Key

pip install -r requirements.txt
python build_index.py     # Build index (requires API Key)
python search_server.py   # Start server
```

For local runs, the server first looks for `gifs-vault/` in the project root.
If the GIF assets live elsewhere, start with `VAULT_DIR=/path/to/gifs-vault python search_server.py`.

### 3. TF-IDF Only (No API Key Needed)

```bash
pip install scikit-learn
python build_index.py     # Build TF-IDF index only
SEARCH_MODE=tfidf python search_server.py
```

## Usage Tips

- Use the Collections browser to browse sticker packs directly — it's usually more intuitive.
- Download frequently used stickers to your local collection for easier access.
- Copy works for static stickers (copies PNG to clipboard).
- For animated GIFs, use Download — browsers typically can't write animated GIFs to clipboard.
- If this project is helpful, please give it a Star.

## Search Modes

| Mode | Description | Requires API | Quality |
|------|-------------|:------------:|---------|
| `tfidf` | Character n-gram keyword matching | ❌ | ⭐⭐⭐ |
| `embedding` | Semantic vector search | ✅ | ⭐⭐⭐⭐⭐ |
| `hybrid` | TF-IDF + Embedding fusion | ✅ | ⭐⭐⭐⭐⭐ |

Set `SEARCH_MODE=tfidf / embedding / hybrid` in `.env`

Implementation details:

- `tfidf`: Pure local character n-gram TF-IDF keyword matching, good for short explicit terms like `happy`, `sleepy`, `angry`.
- `embedding`: Uses `Qwen/Qwen3-Embedding-0.6B` to generate query vectors, computes cosine similarity against local `data/embeddings.npy`, returns semantically similar Top results.
- `hybrid` (default): Recalls TF-IDF Top 500 and Embedding Top 500 separately, then reranks by:

```text
final_score =
  0.55 * embedding_score
+ 0.30 * tfidf_score
+ 0.15 * field_match_score
```

`field_match_score` prioritizes `emotion`, `action`, `tags`, `description`, `scene` field matches. The default search API returns at most Top 120 results.

Embedding index is pre-built by converting all sticker descriptions to vectors and saving to `data/embeddings.npy`. No need to rebuild when searching — only the query needs to be encoded. If you change `OPENAI_EMBEDDING_MODEL`, re-run `python build_index.py`.

## Supported Embedding Providers

| Provider | Environment Variable | Free Tier |
|----------|---------------------|-----------|
| OpenAI | `OPENAI_API_KEY` | $5 for new users |
| Jina AI | `JINA_API_KEY` | 100M tokens/month |
| Custom | `OPENAI_BASE_URL` | Depends on provider |
| Local | `EMBEDDING_PROVIDER=local` | Unlimited (requires GPU) |

## Annotation Spec

See [spec.md](docs/spec.md)

Workflow and lessons learned: [annotation_workflow.md](docs/annotation_workflow.md), [annotation_summary.md](docs/annotation_summary.md).

## Data Source

Stickers from Telegram Stickers, annotated with MiMo v2.5.

- [MiMo](https://mimo.xiaomi.com/) — Xiaomi MiMo vision model used for annotation
<summary>📦 Sticker Sources (click to expand)</summary>

Full listing of all Capoo sticker packs collected in this project (355 packs, 354 successfully downloaded), with SigStick website links and Telegram download links.

👉 Full list: [capoo-all-sticker-links-combined.md](docs/capoo-all-sticker-links-combined.md)

</details>

## Acknowledgements

- [Linux.do](https://linux.do/) — Open source community, thanks for the support
- [MiMo](https://github.com/XiaoMi/MiMo) — Xiaomi MiMo vision model used for annotation

## License

MIT
