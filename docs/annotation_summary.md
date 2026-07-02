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
4. 关键：验证帧目录是否存在（遍历gifs/gifs_webp/gifs_tgs三个source）
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

## 5. 两级Subagent协同设计

### 架构
```
主进程 (Main)
  ├── Coordinator 0 → sets 001-090
  │     ├── Level-2 Agent 0 (标注1张GIF)
  │     ├── Level-2 Agent 1 (标注1张GIF)
  │     └── ... (20个并行level-2 agents)
  ├── Coordinator 1 → sets 091-180
  │     ├── Level-2 Agent 20 (标注1张GIF)
  │     ├── Level-2 Agent 21 (标注1张GIF)
  │     └── ... (20个并行level-2 agents)
  ├── Coordinator 2 → sets 181-270
  │     └── ... (20个并行level-2 agents)
  └── Coordinator 3 → sets 271-354
        └── ... (20个并行level-2 agents)
```

### Level-1 Coordinator职责
- 接收set编号范围（如sets 001-090）
- 从batches.json筛选该范围内的未标注GIF
- spawn 20个level-2 agents并行标注
- 收集20个result，验证输出
- 遇到错误irc DM通知Main
- 完成后返回进度给Main

### Level-2 Agent职责
- 接收assignment（包含1张GIF的帧目录和输出路径）
- 读取帧目录所有PNG帧
- 调用视觉模型生成标注JSON
- 写入输出文件
- 遇到错误irc DM通知Coordinator

### Main进程职责
- spawn 4个coordinators，每个负责一个set编号范围
- 收集coordinator的result，统计总进度
- 处理irc消息（来自coordinators的错误报告）
- 错误重试（自动或手动）
- 记录checkpoint到文件

### 通信机制
```
Level-2 → Coordinator：irc DM（错误报告）
Coordinator → Main：irc DM（进度更新、错误报告）
Main → Coordinator：irc broadcast（停止信号）
Coordinator ← Level-2：task result（自动返回）
Main ← Coordinator：task result（自动返回）
```

### 并发控制
- **总并发数**：4 coordinators × 20 level-2 agents = 80并发标注任务
- **单Coordinator完成判断**：20个level-2 result返回
- **异步调度**：Main不阻塞，可同时处理4个coordinator
- **超时机制**：单任务60s超时，自动重试

### 错误隔离
- 单个level-2 agent失败不影响其他agent
- 单个coordinator失败不影响其他coordinator
- Main根据irc消息决定是否重试
- 错误记录到error.md

## 6. 多层Task提高并发

### 单层限制
- 单层并发：每次只能dispatch一个batch，等全部完成再dispatch下一批
- 瓶颈：prompt构建慢（20个task × 每个~500字 = 10K字prompt）
- 解决：多层task设计，Main只调度，具体工作由coordinators完成

### 多路Task设计
- **20路**：最佳平衡点，prompt构建快，任务30-60s完成
- **50路**：prompt构建慢，单次分发耗时长，整体反而慢
- **8-10路**：吞吐量不够

### 分发策略
```
每批20个GIF → 并发20个task → 等待全部完成 → 验证 → 下一批
```

### 异步调度
```python
# Main进程不阻塞，可同时处理多个batch
while True:
    tasks = get_next_batch(20)
    if not tasks:
        break
    dispatch_tasks(tasks)
    # 不等待，立即处理下一批
    # 验证由irc消息触发
```

## 7. 错误与解法

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

### 错误4：路径错误写到其他Bot目录
- **问题**：agent把标注写到了错误的set目录（如SigStick3Bot写到SigStick19Bot）
- **后果**：标注文件存在但路径不对
- **解法**：用glob搜索所有annotations目录，找到后shutil.copy2到正确路径

## 8. 验证检查清单
- [ ] JSON可正确解析
- [ ] 必填字段完整（emotion, description, tags）
- [ ] tags数量5-8个
- [ ] 标注路径与帧目录对齐
- [ ] 无重复标注

## 9. 补充经验

### 9.1 幽灵写入（Late-return Agent）
- 任务超时后agent可能继续运行，稍后写入文件
- 写入的路径可能是错的（因为agent基于过时的信息）
- 验证时用glob搜索所有annotations目录，而非只检查预期路径
- 发现幽灵写入后shutil.copy2到正确路径

### 9.2 Session长度管理
- 单session超过200K tokens后上下文会截断
- 关键状态（进度、skip列表）必须持久化到文件
- 长任务应在文档中记录checkpoint
- 每完成一批就更新进度，便于新session接手

### 9.3 标注质量标准
- emotion：1-3字，如"开心"、"甜蜜"、"生气"
- description：15-25字，适合聊天搜索匹配
- tags：5-8个，覆盖情绪、动作、场景
- 如果帧里有文字，必须在scene和description中体现

### 9.4 JSON安全指令
- 在task prompt中加入："JSON中引号用「」代替"
- 防止agent输出无效JSON
- tags数组每个元素必须用双引号包裹
