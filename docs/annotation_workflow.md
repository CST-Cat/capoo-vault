# 咖波贴纸自动标注系统 - 工作流程文档

## 1. 项目概述

使用 MiMo 2.5 视觉模型自动标注咖波(BugCat Capoo)贴纸GIF，生成语义标注JSON，用于后续的文本嵌入向量检索。

## 2. 目录结构

```
~/capoo/
├── gifs/                    # 源GIF目录（gifs_webp的同级）
├── gifs_webp/               # webp格式GIF
├── gifs_tgs/                # Telegram贴纸GIF
├── frames/                  # 预提取帧目录
│   ├── gifs/                # 对应gifs/的帧
│   │   └── {set_name}/
│   │       └── {gif_stem}/
│   │           ├── frame_0001.png
│   │           ├── frame_0002.png
│   │           └── ...
│   ├── gifs_webp/           # 对应gifs_webp/的帧
│   └── gifs_tgs/            # 对应gifs_tgs/的帧
├── annotations/             # 标注输出
│   ├── gifs/                # 所有标注JSON统一存放
│   │   └── {set_name}/
│   │       ├── {gif_stem}.json
│   │       └── ...
│   ├── batches.json         # 批次列表
│   └── error.md             # 错误日志
└── annotation_workflow.md   # 本文档
```

## 3. 帧目录说明

帧目录是预提取的GIF帧，每个GIF的每帧作为一个PNG文件。

### 帧目录命名规则
```
frames/{source}/{set_name}/{gif_stem}/frame_{NNNN}.png
```

- `source`: gifs, gifs_webp, gifs_tgs 之一
- `set_name`: 贴纸包目录名（如 `005-Bugcat-Capoo-...`）
- `gif_stem`: GIF文件名去掉.gif后缀（如 `001-file_146`）
- `frame_{NNNN}.png`: 帧序号，4位数字

### 帧目录验证
分发任务前必须验证帧目录存在：
```python
frame_dir = os.path.expanduser(f'~/capoo/frames/{src}/{b["set"]}/{gif_stem}')
if not os.path.isdir(frame_dir):
    continue  # 跳过不存在的GIF
```

## 4. 标注JSON格式

```json
{
  "gif": "001-file_146.gif",
  "set": "005-Bugcat-Capoo-p_k79nrVSD9Bz0xJznxXOA_by_SigStick11Bot",
  "emotion": "开心",
  "action": "角色动作描述",
  "scene": "场景/道具/文字描述，无文字写'无文字'",
  "description": "一句话自然语言描述（15-25字），适合聊天匹配",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"]
}
```

### 必填字段
| 字段 | 说明 | 示例 |
|------|------|------|
| gif | GIF文件名 | `001-file_146.gif` |
| set | 贴纸包全名 | `005-Bugcat-Capoo-...` |
| emotion | 角色情绪（1-3字） | `开心`、`生气`、`甜蜜` |
| action | 角色动作描述 | `张嘴大笑`、`挥手告别` |
| scene | 场景/道具/文字 | `文字「Hi」`、`无文字` |
| description | 一句话描述（15-25字） | `咖波开心地挥手说Hi打招呼` |
| tags | 标签数组（5-8个） | `["开心", "打招呼", "挥手"]` |

### 注意事项
- JSON中引号用「」代替
- tags数组每个元素必须用双引号包裹
- 如果帧里有文字，必须在scene和description中体现
- description要适合聊天搜索匹配

## 5. Task模板

### Agent Prompt（系统提示词）
```
你是咖波(BugCat Capoo)贴纸标注专家。你只负责标注**1张GIF**。

## 工作流程
1. 用 read 工具读取 assignment 中指定的帧目录下的所有 .png 文件
2. 根据帧内容生成标注
3. 用 write 工具写入 JSON 文件

## 标注 JSON 格式
{
  "gif": "文件名.gif",
  "set": "贴纸包全名",
  "emotion": "角色情绪（1-3字）",
  "action": "角色动作描述",
  "scene": "场景/道具/文字描述，无文字写'无文字'",
  "description": "一句话自然语言描述（15-25字），适合聊天匹配",
  "tags": ["标签1", "标签2", ...5-8个]
}

## 规范
- description 要简洁精准，能用于搜索匹配
- tags 覆盖情绪、动作、场景，5-8个
- 全部中文
- 如果帧里有文字，必须在 scene 和 description 中体现
- **重要**：JSON 中的值如果包含引号，用「」代替，不要用 ""
- **重要**：tags 数组中每个元素都必须用双引号包裹，例如 ["tag1", "tag2"]
```

### Task Assignment模板
```json
{
  "id": "G4XXX",
  "role": "贴纸标注专家",
  "assignment": "标注1张GIF\n\nGIF: {gif_stem}.gif\n贴纸包: {set_name}\n\n帧目录: ~/capoo/frames/{source}/{set_name}/{gif_stem}/\n输出文件: ~/capoo/annotations/gifs/{set_name}/{gif_stem}.json"
}
```

## 6. 分发脚本

### 获取下一批未标注GIF
```python
import json, os, glob

annot_base = os.path.expanduser('~/capoo/annotations/gifs')
frames_base = os.path.expanduser('~/capoo/frames/gifs')

tasks = []
skip_sets = {'046', '062', '079', '081', '104'}
skip_gifs = {...}  # 已知有问题的GIF

with open(os.path.expanduser('~/capoo/annotations/batches.json')) as f:
    batches = json.load(f)

for b in batches:
    src = b.get('source', 'gifs')
    if any(s in b['set'] for s in skip_sets):
        continue
    for gif in b['gifs']:
        if gif in skip_gifs:
            continue
        gif_stem = gif.replace('.gif', '')
        annot_path = os.path.expanduser(f'~/capoo/annotations/{src}/{b["set"]}/{gif_stem}.json')
        if os.path.exists(annot_path):
            continue
        matches = glob.glob(os.path.expanduser(f'~/capoo/annotations/gifs/*/{gif_stem}.json'))
        if matches:
            continue
        # 关键：验证帧目录存在
        frame_dir = os.path.expanduser(f'~/capoo/frames/{src}/{b["set"]}/{gif_stem}')
        if not os.path.isdir(frame_dir):
            continue
        tasks.append((gif, b['set'], src))
        if len(tasks) >= 20:
            break
    if len(tasks) >= 20:
        break
```

## 7. 验证脚本

### 每批完成后验证
```python
import os

annot_base = os.path.expanduser('~/capoo/annotations/gifs')
frames_base = os.path.expanduser('~/capoo/frames')

# 检查标注-帧目录对齐
total_annot = 0
total_frames = 0
wrong_count = 0

for src in ['gifs', 'gifs_webp', 'gifs_tgs']:
    src_frames = os.path.join(frames_base, src)
    if not os.path.isdir(src_frames):
        continue
    for d in os.listdir(src_frames):
        frame_dir = os.path.join(src_frames, d)
        if not os.path.isdir(frame_dir):
            continue
        frame_count = len([x for x in os.listdir(frame_dir) 
                          if os.path.isdir(os.path.join(frame_dir, x))])
        total_frames += frame_count
        
        annot_dir = os.path.join(annot_base, d)
        if not os.path.isdir(annot_dir):
            continue
        
        for f in os.listdir(annot_dir):
            if not f.endswith('.json'):
                continue
            total_annot += 1
            gif_stem = f.replace('.json', '')
            if not os.path.isdir(os.path.join(frame_dir, gif_stem)):
                wrong_count += 1

print(f"标注: {total_annot}/{total_frames} ({total_annot/total_frames*100:.1f}%)")
print(f"错误路径: {wrong_count}")
```

## 8. 错误处理

### 常见错误类型
1. **JSON语法错误**：引号未转义 → 用「」代替
2. **路径错误**：标注写到了错误的set目录 → 验证帧目录存在
3. **空返回**：agent未生成输出 → 重试
4. **超时**：API请求超时 → 降低并发或重试

### 错误日志
所有错误记录到 `~/capoo/error.md`

## 9. 并发配置

- **推荐并发数**：20路
- **每批数量**：20个GIF
- **预估速度**：每批约1-2分钟
- **总预估时间**：剩余GIF数 / 20 * 1.5 分钟

## 10. 重要注意事项

1. **帧目录是唯一依据**：分发前必须验证帧目录存在
2. **标注统一存放**：所有标注JSON放在 `annotations/gifs/{set_name}/` 下
3. **不要手动清理**：避免误删有效标注
4. **每批验证**：完成后检查JSON有效性、字段完整性、路径正确性
5. **错误记录**：所有错误写入 error.md
