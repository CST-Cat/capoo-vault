<div align="center">

# Capoo Vault

[简体中文](README.md) | **繁體中文** | [English](README.en.md)

</div>

<div align="center">

**10000+ 張 BugCat Capoo (貓貓蟲咖波) 貼紙語義標註，支援語義搜尋。**

</div>

Capoo Vault 是一個 Capoo 貼紙語義標註資料集，包含 10238 張 GIF 貼紙的結構化標註（情緒、動作、場景、描述、標籤），可用於聊天機器人、表情推薦、向量搜尋等場景。

## 線上預覽

可以先在這裡預覽貼紙合集與搜尋體驗：https://cst-cat.github.io/capoo-gallery/

## 資料規模

| 來源 | 數量 | 狀態 |
|------|------|------|
| gifs_webp | 3982 | ✅ 100% |
| gifs | 5843 | ✅ 100% |
| gifs_tgs | 413 | ✅ 100% |
| **合計** | **10238** | **100%** |

## 標註格式

每張貼紙對應一個 JSON 檔案：

```json
{
  "gif": "001-file_457.gif",
  "set": "013-CAPOO-SP-capoo_sp_animated",
  "emotion": "開心",
  "action": "揮手打招呼",
  "scene": "白色背景",
  "description": "咖波舉起小爪子熱情揮手打招呼",
  "tags": ["咖波", "打招呼", "揮手", "開心", "可愛", "問候", "藍色貓", "表情包"]
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `gif` | string | GIF 檔名 |
| `set` | string | 所屬貼紙包名稱 |
| `emotion` | string | 主要情緒 |
| `action` | string | 動作描述 |
| `scene` | string | 場景描述 |
| `description` | string | 15-25字中文描述 |
| `tags` | string[] | 5-8個中文標籤 |

## 目錄結構

```
capoo-vault/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── .env.example          # 環境變數模板
├── requirements.txt
├── build_index.py        # 建構搜尋索引
├── search_server.py      # 搜尋服務（TF-IDF + Embedding）
├── gifs-vault/           # GIF 素材目錄（Docker 執行時掛載，需下載/解壓）
├── data/
│   ├── stickers.json     # 搜尋元資料
│   └── tfidf_index.json  # TF-IDF 搜尋索引
├── docs/
│   ├── spec.md           # 標註規範
│   ├── annotation_workflow.md  # 標註工作流
│   ├── annotation_summary.md   # 經驗總結
│   └── capoo-all-sticker-links-combined.md  # 貼紙來源
└── annotations/
    ├── gifs/             # 10238 個標註 JSON
    └── batches.json
```

## 快速開始

### 1. Docker 部署（推薦）

```bash
# 下載 GIF 素材包後，放到 capoo-vault 專案根目錄
# 下載所有 capoo-vault-gifs-vault-YYYYMMDD.7z.00* 分卷檔案
# 解壓後應得到 ./gifs-vault/<貼紙包>/*.gif
7z x capoo-vault-gifs-vault-YYYYMMDD.7z.001

# 複製環境變數模板
cp .env.example .env

# 編輯 .env，填入你的 Embedding API Key
# 支援 OpenAI / Jina / 自定義相容介面

# 建構並啟動
docker compose up -d

# 瀏覽器開啟 http://localhost:8989
```

Docker Compose 會把宿主機的 `./gifs-vault` 掛載到容器內的 `/app/gifs-vault`。
如果你手動調整路徑，請同步設定 `VAULT_DIR`；預設容器配置為 `VAULT_DIR=/app/gifs-vault`。
注意不要解壓成 `gifs-vault/gifs-vault/` 這種多一層目錄。
Windows 使用者可以用 7-Zip 開啟 `.7z.001` 分卷，Linux 使用者可以安裝 `p7zip-full` 或 `7zip` 後執行上面的命令。

### 2. 本機執行

```bash
cp .env.example .env
# 編輯 .env 填入 API Key

pip install -r requirements.txt
python build_index.py     # 建構索引（需要 API Key）
python search_server.py   # 啟動服務
```

本機執行時，預設會優先讀取專案根目錄下的 `gifs-vault/`。
如果 GIF 素材放在其他位置，可以透過 `VAULT_DIR=/path/to/gifs-vault python search_server.py` 指定。

### 3. 僅 TF-IDF（不需要 API Key）

```bash
pip install scikit-learn
python build_index.py     # 只建構 TF-IDF 索引
SEARCH_MODE=tfidf python search_server.py
```

## 使用說明

- 更推薦先使用 Collections/合集瀏覽功能，按貼紙包直接翻找通常更直觀。
- 常用貼紙建議直接 Download 下載到本機收藏，後續使用會更方便。
- Copy 適合靜態表情包，會將圖片作為 PNG 複製到剪貼簿。
- 動態 GIF 建議使用 Download，瀏覽器通常不支援把 animated GIF 直接寫入剪貼簿。
- 如果這個專案對你有幫助，歡迎點一個 Star。

## 搜尋模式

| 模式 | 說明 | 需要 API | 品質 |
|------|------|----------|------|
| `tfidf` | 字元 n-gram 關鍵字比對 | ❌ | ⭐⭐⭐ |
| `embedding` | 語義向量搜尋 | ✅ | ⭐⭐⭐⭐⭐ |
| `hybrid` | TF-IDF + Embedding 融合 | ✅ | ⭐⭐⭐⭐⭐ |

在 `.env` 中設定 `SEARCH_MODE=tfidf / embedding / hybrid`

三種搜尋模式的實作方式：

- `tfidf`：純本機字元 n-gram TF-IDF 關鍵字比對，適合 `開心`、`摸魚`、`崩潰` 這類明確短詞。
- `embedding`：用 `Qwen/Qwen3-Embedding-0.6B` 生成查詢向量，與本機 `data/embeddings.npy` 做 cosine similarity，返回語義相近的 Top 結果。
- `hybrid`：預設推薦模式，先分別召回 TF-IDF Top 500 和 Embedding Top 500，再按下面的本機 rerank 分數重新排序：

```text
final_score =
  0.55 * embedding_score
+ 0.30 * tfidf_score
+ 0.15 * field_match_score
```

`field_match_score` 會優先考慮 `emotion`、`action`、`tags`、`description`、`scene` 等欄位是否命中查詢詞。預設搜尋介面最多返回 Top 120，避免 embedding 模式返回過長的低相關結果。

Embedding 索引是預先把所有貼紙描述轉換成向量後保存到 `data/embeddings.npy`。
運行搜尋時不需要重新給全部貼紙建索引，只需要用同一個模型給使用者查詢生成向量。
如果更換 `OPENAI_EMBEDDING_MODEL`，需要重新執行 `python build_index.py` 生成新的 embedding 索引。

## 支援的 Embedding Provider

| Provider | 環境變數 | 免費額度 |
|----------|----------|----------|
| OpenAI | `OPENAI_API_KEY` | $5 新使用者 |
| Jina AI | `JINA_API_KEY` | 100M tokens/月 |
| 自定義 | `OPENAI_BASE_URL` | 取決於提供者 |
| 本機模型 | `EMBEDDING_PROVIDER=local` | 無限（需 GPU） |

## 標註規範

詳見 [spec.md](docs/spec.md)

標註工作流與經驗總結見 [annotation_workflow.md](docs/annotation_workflow.md)、[annotation_summary.md](docs/annotation_summary.md)。

## 資料來源

貼紙來自 Telegram Stickers，透過 MiMo v2.5 標註。

<details>
<summary>📦 表情包來源（點擊展開）</summary>

以下列出本專案收錄的所有 Capoo 貼紙合集來源（355 個合集，354 個成功下載），包含 SigStick 網站連結和 Telegram 下載連結。
- [MiMo](https://mimo.xiaomi.com/) — 小米 MiMo 視覺模型，本專案標註所用
👉 完整列表見 [capoo-all-sticker-links-combined.md](docs/capoo-all-sticker-links-combined.md)

</details>

## 友情連結

- [Linux.do](https://linux.do/) — 開源社群，感謝社群支持與交流
- [MiMo](https://github.com/XiaoMi/MiMo) — 小米 MiMo 視覺模型，本專案標註所用

## License

MIT
