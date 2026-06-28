# Capoo Vault

[简体中文](#简体中文) | [繁體中文](#繁體中文) | [English](#English)

---

## 简体中文

**10000+ 张 BugCat Capoo (貓貓蟲咖波) 贴纸语义标注，支持语义搜索。**

Capoo Vault 是一个 Capoo 贴纸语义标注数据集，包含 10238 张 GIF 贴纸的结构化标注（情绪、动作、场景、描述、标签），可用于聊天机器人、表情推荐、向量搜索等场景。

### 数据规模

| 来源 | 数量 | 状态 |
|------|------|------|
| gifs_webp | 3982 | ✅ 100% |
| gifs | 5843 | ✅ 100% |
| gifs_tgs | 413 | ✅ 100% |
| **合计** | **10238** | **100%** |

### 标注格式

每张贴纸对应一个 JSON 文件：

```json
{
  "gif": "001-file_457.gif",
  "set": "013-CAPOO-SP-capoo_sp_animated",
  "emotion": "开心",
  "action": "挥手打招呼",
  "scene": "白色背景",
  "description": "咖波举起小爪子热情挥手打招呼",
  "tags": ["咖波", "打招呼", "挥手", "开心", "可爱", "问候", "蓝色猫", "表情包"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `gif` | string | GIF 文件名 |
| `set` | string | 所属贴纸包名称 |
| `emotion` | string | 主要情绪 |
| `action` | string | 动作描述 |
| `scene` | string | 场景描述 |
| `description` | string | 15-25字中文描述 |
| `tags` | string[] | 5-8个中文标签 |

### 目录结构

```
capoo-vault/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── .env.example          # 环境变量模板
├── requirements.txt
├── build_index.py        # 构建搜索索引
├── search_server.py      # 搜索服务（TF-IDF + Embedding）
├── spec.md               # 标注规范
└── annotations/
    ├── gifs/             # 10238 个标注 JSON
    └── batches.json
```

### 快速开始

#### 1. Docker 部署（推荐）

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入你的 Embedding API Key
# 支持 OpenAI / Jina / 自定义兼容接口

# 构建并启动
docker compose up -d

# 访问 http://localhost:8989
```

#### 2. 本地运行

```bash
cp .env.example .env
# 编辑 .env 填入 API Key

pip install -r requirements.txt
python build_index.py     # 构建索引（需要 API Key）
python search_server.py   # 启动服务
```

#### 3. 仅 TF-IDF（不需要 API Key）

```bash
pip install scikit-learn
python build_index.py     # 只构建 TF-IDF 索引
SEARCH_MODE=tfidf python search_server.py
```

### 使用说明

- 更推荐先使用 Collections/合集浏览功能，按贴纸包直接翻找通常更直观。
- 常用贴纸建议直接 Download 下载到本地收藏，后续使用会更方便。
- Copy 适合静态表情包，会将图片作为 PNG 复制到剪贴板。
- 动态 GIF 建议使用 Download，浏览器通常不支持把 animated GIF 直接写入剪贴板。
- 如果这个项目对你有帮助，欢迎点一个 Star。

### 搜索模式

| 模式 | 说明 | 需要 API | 质量 |
|------|------|----------|------|
| `tfidf` | 字符 n-gram 关键词匹配 | ❌ | ⭐⭐⭐ |
| `embedding` | 语义向量搜索 | ✅ | ⭐⭐⭐⭐⭐ |
| `hybrid` | TF-IDF + Embedding 融合 | ✅ | ⭐⭐⭐⭐⭐ |

在 `.env` 中设置 `SEARCH_MODE=tfidf / embedding / hybrid`

当前三种搜索模式的实现方式：

- `tfidf`：纯本地字符 n-gram TF-IDF 关键词匹配，适合 `开心`、`摸鱼`、`崩溃` 这类明确短词。
- `embedding`：用 `Qwen/Qwen3-Embedding-0.6B` 生成查询向量，与本地 `data/embeddings.npy` 做 cosine similarity，返回语义相近的 Top 结果。
- `hybrid`：默认推荐模式，先分别召回 TF-IDF Top 500 和 Embedding Top 500，再按下面的本地 rerank 分数重新排序：

```text
final_score =
  0.55 * embedding_score
+ 0.30 * tfidf_score
+ 0.15 * field_match_score
```

`field_match_score` 会优先考虑 `emotion`、`action`、`tags`、`description`、`scene` 等字段是否命中查询词。默认搜索接口最多返回 Top 120，避免 embedding 模式返回过长的低相关结果。

Embedding 索引是预先把所有贴纸描述转换成向量后保存到 `data/embeddings.npy`。
运行搜索时不需要重新给全部贴纸建索引，只需要用同一个模型给用户查询生成向量。
如果更换 `OPENAI_EMBEDDING_MODEL`，需要重新运行 `python build_index.py` 生成新的 embedding 索引。

### 支持的 Embedding Provider

| Provider | 环境变量 | 免费额度 |
|----------|----------|----------|
| OpenAI | `OPENAI_API_KEY` | $5 新用户 |
| Jina AI | `JINA_API_KEY` | 100M tokens/月 |
| 自定义 | `OPENAI_BASE_URL` | 取决于提供商 |
| 本地模型 | `EMBEDDING_PROVIDER=local` | 无限（需 GPU） |

### 标注规范

详见 [spec.md](spec.md)

标注工作流与经验总结见 [annotation_workflow.md](annotation_workflow.md)、[annotation_summary.md](annotation_summary.md)。

### 数据来源

贴纸来自 Telegram Stickers，通过 MiMo v2.5 批注。

<details>
<summary>📦 表情包来源（点击展开）</summary>

以下列出本项目收录的所有 Capoo 贴纸合集来源（355 个合集，354 个成功下载），包含 SigStick 网站链接和 Telegram 下载链接。

👉 完整列表见 [capoo-all-sticker-links-combined.md](capoo-all-sticker-links-combined.md)

</details>

### 友情链接

- [Linux.do](https://linux.do/) — 开源社区，感谢社区支持与交流
- [MiMo](https://github.com/XiaoMi/MiMo) — 小米 MiMo 视觉模型，本项目标注所用

### License

MIT

---

## 繁體中文

**10000+ 張 BugCat Capoo (貓貓蟲咖波) 貼紙語義標註，支援語義搜尋。**

Capoo Vault 是一個 Capoo 貼紙語義標註資料集，包含 10238 張 GIF 貼紙的結構化標註（情緒、動作、場景、描述、標籤），可用於聊天機器人、表情推薦、向量搜尋等場景。

### 資料規模

| 來源 | 數量 | 狀態 |
|------|------|------|
| gifs_webp | 3982 | ✅ 100% |
| gifs | 5843 | ✅ 100% |
| gifs_tgs | 413 | ✅ 100% |
| **合計** | **10238** | **100%** |

### 標註格式

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

### 快速開始

#### 1. Docker 部署（推薦）

```bash
cp .env.example .env
# 編輯 .env，填入你的 Embedding API Key
docker compose up -d
# 瀏覽器開啟 http://localhost:8989
```

#### 2. 本機執行

```bash
cp .env.example .env
pip install -r requirements.txt
python build_index.py     # 建構索引
python search_server.py   # 啟動服務
```

### 搜尋模式

| 模式 | 說明 | 需要 API | 品質 |
|------|------|----------|------|
| `tfidf` | 字元 n-gram 關鍵字比對 | ❌ | ⭐⭐⭐ |
| `embedding` | 語義向量搜尋 | ✅ | ⭐⭐⭐⭐⭐ |
| `hybrid` | TF-IDF + Embedding 融合 | ✅ | ⭐⭐⭐⭐⭐ |

### 資料來源

貼紙來自 Telegram Stickers，透過 MiMo v2.5 標註。

完整合集來源見 [capoo-all-sticker-links-combined.md](capoo-all-sticker-links-combined.md)

### 友情連結

- [Linux.do](https://linux.do/) — 開源社群，感謝社群支持與交流
- [MiMo](https://github.com/XiaoMi/MiMo) — 小米 MiMo 視覺模型，本項目標註所用

### License

MIT

---

## English

**10,000+ BugCat Capoo (貓貓蟲咖波) sticker annotations with semantic search.**

Capoo Vault is a semantic annotation dataset for Capoo stickers, containing structured annotations (emotion, action, scene, description, tags) for 10,238 GIF stickers. Suitable for chatbots, sticker recommendation, vector search, and more.

### Dataset Size

| Source | Count | Status |
|--------|-------|--------|
| gifs_webp | 3,982 | ✅ 100% |
| gifs | 5,843 | ✅ 100% |
| gifs_tgs | 413 | ✅ 100% |
| **Total** | **10,238** | **100%** |

### Annotation Format

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

### Quick Start

#### 1. Docker (Recommended)

```bash
cp .env.example .env
# Edit .env and fill in your Embedding API Key
docker compose up -d
# Open http://localhost:8989
```

#### 2. Local

```bash
cp .env.example .env
pip install -r requirements.txt
python build_index.py     # Build index (requires API Key)
python search_server.py   # Start server
```

### Search Modes

| Mode | Description | Requires API | Quality |
|------|-------------|:------------:|---------|
| `tfidf` | Character n-gram keyword matching | ❌ | ⭐⭐⭐ |
| `embedding` | Semantic vector search | ✅ | ⭐⭐⭐⭐⭐ |
| `hybrid` | TF-IDF + Embedding fusion | ✅ | ⭐⭐⭐⭐⭐ |

### Data Source

Stickers from Telegram Stickers, annotated with MiMo v2.5.

Full pack listing: [capoo-all-sticker-links-combined.md](capoo-all-sticker-links-combined.md)

### Acknowledgements

- [Linux.do](https://linux.do/) — Open source community, thanks for the support
- [MiMo](https://github.com/XiaoMi/MiMo) — Xiaomi MiMo vision model used for annotation

### License

MIT
