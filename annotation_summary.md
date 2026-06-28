# 咖波贴纸自动标注 - 小总结

## 1. 单次给AI多张GIF的问题

**问题**：一次性给AI多张GIF，同一批次内不同GIF的标注内容会互相干扰，顺序混乱。

**原因**：AI处理多张图片时，注意力分散，标注质量下降，且输出的JSON可能张冠李戴。

**解法**：**每任务只标注1张GIF**。通过task并发20路，每路处理1张，既保证质量又提高吞吐量。

## 2. Task模板不能写死set

**问题**：如果在task模板中写死`set=xxx`，当set名变更或分发逻辑调整时，需要手动修改每个task。

**解法**：用Python脚本动态生成task assignment，从batches.json读取set名和GIF名，自动拼接帧目录和输出路径。

```python
# 动态生成assignment
assignment = f"""标注1张GIF

GIF: {gif}
贴纸包: {set_name}

帧目录: ~/capoo/frames/{source}/{set_name}/{gif_stem}/
输出文件: ~/capoo/annotations/gifs/{set_name}/{gif_stem}.json"""
```

## 3. Python分发与检验机制

### 分发流程
```
1. 读取 batches.json（包含所有set和GIF列表）
2. 跳过 skip_sets 和 skip_gifs（已知问题）
3. 检查标注是否已存在（annot_path + glob搜索）
4. 关键：验证帧目录是否存在
5. 收集20个未标注GIF
6. 用task工具并发分发
```

### 检验流程（每批完成后）
```
1. 检查JSON有效性（能否正确解析）
2. 检查必填字段（emotion, description, tags）
3. 检查tags数量（5-8个）
4. 检查路径对齐（标注文件 vs 帧目录）
5. 统计总进度
```

### Agent间通知
- 通过irc工具发送消息
- task工具的result自动返回给主进程
- 错误通过irc DM通知，主进程不替agent回复

### 持续运行
```python
while True:
    # 1. 获取下一批20个未标注GIF
    tasks = get_next_batch(20)
    if not tasks:
        break
    
    # 2. 并发分发
    dispatch_tasks(tasks)
    
    # 3. 等待全部完成
    wait_for_completion()
    
    # 4. 验证
    verify_batch()
```

## 4. FFmpeg帧提取与MD5去重

### 帧提取
```bash
ffmpeg -i input.gif -vsync 0 frames/%(set)s/%(gif_stem)s/frame_%04d.png
```

### MD5去重（处理重复帧）
```python
import hashlib

def md5_file(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

# 去重逻辑
seen_hashes = set()
for frame in sorted(os.listdir(frame_dir)):
    frame_path = os.path.join(frame_dir, frame)
    h = md5_file(frame_path)
    if h in seen_hashes:
        os.remove(frame_path)  # 删除重复帧
    else:
        seen_hashes.add(h)
```

## 5. 多层Task提高并发

**单层并发限制**：每次只能dispatch一个task批次，等全部完成再dispatch下一批。

**多层并发设计**：
```
主进程
  ├── dispatch batch 1 (20 tasks)
  │     ├── task 1
  │     ├── task 2
  │     └── ... (20个并行)
  ├── 等待batch 1完成
  ├── dispatch batch 2 (20 tasks)
  │     ├── task 21
  │     ├── task 22
  │     └── ... (20个并行)
  └── ...
```

**实际实现**：通过irc通知+task result回调实现异步调度，主进程不阻塞。

## 6. 错误与解法

### 错误1：写死gif/webp路径
- **问题**：在task assignment中写死了`~/capoo/frames/gifs/...`
- **后果**：gifs_webp和gifs_tgs目录下的GIF找不到帧目录
- **解法**：从batches.json的`source`字段动态获取路径（gifs/gifs_webp/gifs_tgs）

### 错误2：清理脚本误删所有标注
- **问题**：检查frame目录时只查了gifs目录，没查gifs_webp和gifs_tgs
- **后果**：6000+标注全被删掉
- **解法**：检查frame目录时遍历所有3个source目录

### 错误3：批次列表路径错误
- **问题**：batches.json中有些GIF的set名与实际帧目录不匹配
- **后果**：agent找不到帧目录，标注写到错误路径
- **解法**：分发前验证frame_dir是否存在，不存在则跳过

## 7. 多路Task设计

### 并发数选择
- **20路**：最佳平衡点，prompt构建快，任务30-60s完成
- **50路**：prompt构建慢，单次分发耗时长，整体反而慢
- **8-10路**：吞吐量不够

### 分发策略
```
每批20个GIF → 并发20个task → 等待全部完成 → 验证 → 下一批
```

### 错误处理
- JSON语法错误 → 记录到error.md
- 空返回 → 自动重试（task内置）
- 路径错误 → 跳过该GIF
- 超时 → 自动重试

### 验证检查清单
- [ ] JSON可正确解析
- [ ] 必填字段完整（emotion, description, tags）
- [ ] tags数量5-8个
- [ ] 标注路径与帧目录对齐
- [ ] 无重复标注
