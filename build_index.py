#!/usr/bin/env python3
"""构建搜索索引：TF-IDF + Embedding（支持 API / 本地）"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("EMBEDDING_PROVIDER", "")  # openai / jina / local / 空=跳过


def load_annotations(annot_dir="annotations/gifs"):
    """加载所有标注 JSON"""
    stickers = []
    for root, dirs, files in os.walk(annot_dir):
        for f in sorted(files):
            if f.endswith(".json"):
                path = os.path.join(root, f)
                try:
                    with open(path) as fh:
                        d = json.load(fh)
                    d["_path"] = os.path.relpath(path, annot_dir)
                    stickers.append(d)
                except (json.JSONDecodeError, KeyError):
                    print(f"[warn] 跳过无效文件: {path}")
    return stickers


def build_tfidf_index(stickers, output="data/tfidf_index.json"):
    """构建 TF-IDF 索引"""
    from sklearn.feature_extraction.text import TfidfVectorizer

    corpus = []
    for s in stickers:
        text = f"{s.get('emotion','')} {s.get('action','')} {s.get('scene','')} {s.get('description','')} {' '.join(s.get('tags',[]))}"
        corpus.append(text)

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 4), max_features=50000)
    tfidf_matrix = vectorizer.fit_transform(corpus)

    rows = []
    for i in range(tfidf_matrix.shape[0]):
        row = tfidf_matrix[i]
        rows.append({"c": [int(x) for x in row.indices], "v": [round(float(x), 6) for x in row.data]})

    index_data = {
        "vocab": {k: int(v) for k, v in vectorizer.vocabulary_.items()},
        "idf": [round(float(x), 6) for x in vectorizer.idf_],
        "rows": rows,
    }

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False)

    size_mb = os.path.getsize(output) / 1024 / 1024
    print(f"[ok] TF-IDF 索引: {output} ({size_mb:.1f}MB, {len(stickers)} 条)")


def build_embedding_index(stickers, output="data/embeddings.npy"):
    """构建 embedding 向量索引（需要 API key + httpx）"""
    try:
        import httpx
    except ImportError:
        print("[warn] 跳过 embedding 索引（httpx 未安装）")
        return

    import numpy as np

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("JINA_API_KEY")
    if not api_key:
        print("[warn] 跳过 embedding 索引（未配置 API key）")
        return

    corpus = [
        f"{s.get('emotion','')} {s.get('action','')} {s.get('scene','')} {s.get('description','')} {' '.join(s.get('tags',[]))}"
        for s in stickers
    ]

    if PROVIDER == "jina":
        model = os.getenv("JINA_EMBEDDING_MODEL", "jina-embeddings-v3")
        url = "https://api.jina.ai/v1/embeddings"
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/embeddings"
        headers = {"Authorization": f"Bearer {api_key}"}

    all_vectors = []
    default_batch_size = 16 if "qwen3-embedding-8b" in model.lower() else 128
    try:
        batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", default_batch_size))
    except ValueError:
        batch_size = default_batch_size
    batch_size = max(1, batch_size)
    for i in range(0, len(corpus), batch_size):
        batch = corpus[i : i + batch_size]
        resp = httpx.post(url, headers=headers, json={"model": model, "input": batch}, timeout=60)
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda x: x["index"])
        all_vectors.extend([item["embedding"] for item in data])
        print(f"  embedding: {min(i+batch_size, len(corpus))}/{len(corpus)}")

    os.makedirs(os.path.dirname(output), exist_ok=True)
    arr = np.array(all_vectors, dtype=np.float32)
    np.save(output, arr)
    size_mb = os.path.getsize(output) / 1024 / 1024
    print(f"[ok] Embedding 索引: {output} ({size_mb:.1f}MB, {arr.shape})")


def build_metadata(stickers, output="data/stickers.json"):
    """保存元数据"""
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "gif": s["gif"],
                    "set": s["set"],
                    "emotion": s["emotion"],
                    "action": s["action"],
                    "scene": s["scene"],
                    "description": s["description"],
                    "tags": s["tags"],
                    "telegram_url": s.get("telegram_url", ""),
                    "source_url": s.get("source_url", ""),
                    "path": s["_path"],
                }
                for s in stickers
            ],
            f,
            ensure_ascii=False,
        )
    print(f"[ok] 元数据: {output}")


if __name__ == "__main__":
    stickers = load_annotations()
    print(f"[load] 加载 {len(stickers)} 条标注")

    build_tfidf_index(stickers)
    build_embedding_index(stickers)
    build_metadata(stickers)
