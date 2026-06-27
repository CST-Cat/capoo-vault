# 🐱 Capoo Vault

**10000+ BugCat Capoo (貓貓蟲咖波) sticker annotations with semantic search.**

Capoo Vault 是一个 Capoo 贴纸语义标注数据集，包含 10238 张 GIF 贴纸的结构化标注（情绪、动作、场景、描述、标签），可用于聊天机器人、表情推荐、向量搜索等场景。

## 数据规模

| 来源 | 数量 | 状态 |
|------|------|------|
| gifs_webp | 3982 | ✅ 100% |
| gifs | 5843 | ✅ 100% |
| gifs_tgs | 413 | ✅ 100% |
| **合计** | **10238** | **100%** |

## 标注格式

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

## 目录结构

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

## 快速开始

### 1. Docker 部署（推荐）

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入你的 Embedding API Key
# 支持 OpenAI / Jina / 自定义兼容接口

# 构建并启动
docker compose up -d

# 访问 http://localhost:8989
```

### 2. 本地运行

```bash
cp .env.example .env
# 编辑 .env 填入 API Key

pip install -r requirements.txt
python build_index.py     # 构建索引（需要 API Key）
python search_server.py   # 启动服务
```

### 3. 仅 TF-IDF（不需要 API Key）

```bash
pip install scikit-learn
python build_index.py     # 只构建 TF-IDF 索引
SEARCH_MODE=tfidf python search_server.py
```

## 搜索模式

| 模式 | 说明 | 需要 API | 质量 |
|------|------|----------|------|
| `tfidf` | 字符 n-gram 关键词匹配 | ❌ | ⭐⭐⭐ |
| `embedding` | 语义向量搜索 | ✅ | ⭐⭐⭐⭐⭐ |
| `hybrid` | TF-IDF + Embedding 融合 | ✅ | ⭐⭐⭐⭐⭐ |

在 `.env` 中设置 `SEARCH_MODE=tfidf / embedding / hybrid`

## 支持的 Embedding Provider

| Provider | 环境变量 | 免费额度 |
|----------|----------|----------|
| OpenAI | `OPENAI_API_KEY` | $5 新用户 |
| Jina AI | `JINA_API_KEY` | 100M tokens/月 |
| 自定义 | `OPENAI_BASE_URL` | 取决于提供商 |
| 本地模型 | `EMBEDDING_PROVIDER=local` | 无限（需 GPU） |

## 标注规范

详见 [spec.md](spec.md)

## 数据来源

贴纸来自 Telegram Stickers，通过 AI 视觉模型自动标注。

## License

MIT
