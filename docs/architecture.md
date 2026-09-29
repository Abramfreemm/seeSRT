# seeSRT 技术架构文档

## 1. 总体架构

采用分层架构，前端与后端分离，模型能力通过「适配层」抽象，便于在本地 Ollama 与免费 API 之间切换。

```
┌─────────────────────────────────────────────┐
│              前端 Web UI（端口 8877）          │
└──────────────────────┬──────────────────────┘
                       │ HTTP / JSON
┌──────────────────────▼──────────────────────┐
│            FastAPI 后端（Python）             │
│  ┌───────────┬───────────┬───────────────┐  │
│  │ parsers   │ extraction│ align/correct │  │
│  │ 解析器     │ 台词提取   │ 对齐/纠错      │  │
│  └───────────┴───────────┴───────┬───────┘  │
│                        ┌──────────▼───────┐  │
│                        │   LLM 适配层       │  │
│                        └──────────┬───────┘  │
└───────────────────────────────────┼──────────┘
                   ┌────────────────┼────────────────┐
                   │                │                │
              Ollama(本地)    硅基流动/智谱     其他 OpenAI 兼容
                              (免费 API)
```

## 2. 技术选型

| 类别 | 选型 | 说明 |
| --- | --- | --- |
| 语言 | Python 3.11+ | 用户熟悉，生态完善 |
| Web 框架 | FastAPI + Uvicorn | 异步、自动生成接口文档 |
| 前端 | 静态 HTML + JS（或 Vue/React） | 后续确定，M4 阶段实现 |
| docx 解析 | python-docx | 读取段落与样式 |
| 模糊匹配 | rapidfuzz / difflib | 对齐与逐字 diff |
| 模型调用 | openai SDK（兼容层）+ ollama SDK | 统一 base_url 切换 provider |
| 数据持久化 | SQLite（或 JSON 文件） | 任务/配置存储 |

## 3. 模块划分

```
app/
├── main.py                 # FastAPI 入口
├── api/                    # REST 路由
├── parsers/
│   ├── srt_parser.py       # SRT 解析/写出
│   └── script_parser.py    # docx / txt / fountain 解析
├── extraction/
│   └── dialogue_extractor.py  # 台词提取（集→场景→台词，规则 + LLM）
├── align/
│   └── aligner.py          # 台词↔字幕对齐
├── correct/
│   └── corrector.py        # 纠错 + 完整度报告
├── split/
│   └── splitter.py         # 字幕拆分（每行23字符、每片段2行）
├── batch/
│   └── task_manager.py     # 任务队列 + 并行 + 集数定位
├── llm/
│   ├── base.py             # 抽象接口
│   ├── ollama_provider.py  # 本地 Ollama
│   └── openai_provider.py  # OpenAI 兼容免费 API
└── schemas/
    └── models.py           # 数据模型（Pydantic）
```

## 4. 核心数据模型

```
Project      { id, name }                          # 一部剧/一个项目
Episode      { id, project_id, episode_no }        # 剧本文件中的一集
Scene        { id, episode_id, scene_no }          # 一集内的场景（如 1-1）
Dialogue     { id, scene_id, text_zh, text_en }    # 中英对照台词对（归到场景下）
EpisodeSrt   { id, episode_id, segments[] }        # 该集的 SRT（文件名 = 集数）
SrtSegment   { index, start, end, text }           # 字幕片段
Alignment    { srt_id, srt_index, dialogue_id?, score, status }  # 命中/未命中
Correction   { srt_id, srt_index, old_text, new_text, changed_fields[], status }
Task         { id, episode_id, status, created_at }  # 一次集的处理任务
Result       { task_id, srt_id, corrected_srt, report }  # 每集独立结果
Report       { missing[], extra[], low_confidence[], stats }
```

## 5. API 设计（草案）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/script/upload` | 上传剧本文件 |
| POST | `/api/script/extract` | 提取台词库 |
| GET | `/api/dialogues` | 获取台词库（可编辑） |
| PUT | `/api/dialogues/{id}` | 人工修正单条台词 |
| POST | `/api/srt/upload` | 上传 SRT 文件 |
| POST | `/api/align` | 执行对齐 |
| POST | `/api/correct` | 执行纠错 |
| GET | `/api/report` | 获取完整度报告 |
| GET | `/api/export/srt` | 导出修正后 SRT |
| POST | `/api/srts/upload` | 批量上传各集 SRT（文件名=集数，自动定位） |
| POST | `/api/tasks` | 创建任务（对齐 + 纠错 + 导出） |
| GET | `/api/tasks/{id}` | 查询任务状态 |
| POST | `/api/tasks/batch` | 并行提交多个剧本任务 |

## 6. 关键算法设计

### 6.1 台词提取（集 → 场景 → 台词，规则优先 + LLM 兜底）
1. 解析出文档的所有文本行。
2. 规则阶段：
   - 识别「集标题」（如「第一集」）确定当前集。
   - 识别「场景编号标题」（如 `1-1`）确定当前场景。
   - 利用「一行中文、一行英文」交替结构按行配对成台词对，归入当前集 + 场景。
   - 过滤角色名（单独行）、舞台提示、镜头说明等非台词内容。
3. LLM 兜底：对规则无法确定的行，调用模型判断「是否台词 + 语言 + 归属场景」。

### 6.2 对齐引擎（顺序约束 + 模糊匹配）
1. **归一化**：去标点、统一大小写（英文）、合并空白、全半角统一。
2. **顺序假设**：字幕顺序与剧本台词顺序大体一致。
3. 使用 `rapidfuzz` 计算字幕片段与候选台词（滑动窗口内）的相似度，选择最高分且超过阈值的匹配；支持「多片段→一句台词」的合并匹配。
4. 输出每个片段的 `命中台词` 或 `未命中`。

### 6.3 纠错（确定性 diff，零幻觉）
1. 对命中片段，用 `difflib` 做逐字 diff，识别大小写/拼写/漏词差异。
2. 以剧本台词原文替换字幕文本（保留时间轴与序号）。
3. 未命中片段不改动，标记进入人工复核。

### 6.4 集数定位与批量
1. **文件名解析（优先）**：SRT 文件名即集数（如 `1.srt`、`01.srt`），直接解析出集号。
2. **内容兜底**：文件名无法解析时，取 SRT 文本与各集台词库做相似度匹配，归入最高分那一集。
3. **每集独立纠错**：每个 SRT（一集）独立执行「对齐 + 纠错 + 拆分」，产出修正后 SRT 与报告。
4. **任务并行**：多个集/项目的任务通过任务队列并发执行，互不阻塞。

### 6.5 拆分引擎（每行 ≤ 23 字符、每片段 ≤ 2 行）
1. 输入纠错后的台词文本（含时间轴）。
2. 按语义/标点断句，优先在逗号/连接词/介词短语/从句边界换行，每行 ≤ 23 字符。
3. 每片段最多 2 行；超过 2 行则拆成新片段，时间轴按字符数占比分配。
4. 不增删改词，标点保持英文半角。

## 7. 依赖清单（初步）

```
fastapi, uvicorn, python-multipart,
python-docx, rapidfuzz,
openai, ollama,
pydantic
```
