# seeSRT

双语字幕智能纠错工具：以**双语剧本文本为标准答案**，自动纠错达芬奇（DaVinci Resolve）导出的英文 SRT，并按剪辑师规则拆分，导出可直接回贴的成品字幕。

## 功能特性

- **剧本提取**：自动识别「集 → 场景 → 中英台词」结构（支持 .docx / .txt / .fountain）
- **台词对齐**：SRT 片段与剧本英文台词做词级对齐
- **自动纠错**：以剧本台词为标准答案纠正 SRT 中的英文
- **智能拆分**：每行 ≤ 23 字符、每片段 ≤ 2 行，时间轴按字符占比分配
- **大小写规范化**：全大写文本自动转为句首大写
- **音效标记**：自动识别并在导出时删除
- **未命中复核**：未命中的片段可人工确认复核
- **批量处理 / 批量导出**：多集一键处理、打包 zip 导出
- **双形态**：网页模式 + 原生窗口桌面应用（pywebview）

## 技术原理

纯确定性算法，**不使用任何 AI / 大语言模型**，零幻觉（同样输入永远得到同样输出）：

| 环节 | 实现 |
|------|------|
| 剧本提取 | 正则表达式 |
| 台词对齐 | `difflib.SequenceMatcher` 词级最长公共子序列 |
| 纠错分组 | 词级 diff |
| 拆分 | 规则化（≤23 字符 / ≤2 行） |

## 环境要求

- Python 3.11
- Windows（桌面版依赖系统自带或已安装的 WebView2 Runtime）

## 安装

```bash
pip install -r requirements.txt
```

## 运行

### 网页模式

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8877
```

浏览器访问 http://127.0.0.1:8877/

### 桌面模式

```bash
python run.py
```

## 测试

```bash
pytest
```

## 打包为桌面软件

```bash
python -m PyInstaller seeSRT.spec --noconfirm --clean
```

产物位于 `dist/seeSRT/`，把整个文件夹压缩分发即可，对方解压后双击 `seeSRT.exe` 运行（无需安装 Python）。

## 使用流程

1. 上传剧本（台词库自动拆分）
2. 上传 SRT（文件名 = 集数，如 `1.srt`）
3. 对齐 + 纠错（或批量处理）
4. 审查未命中片段
5. 导出 SRT

## 目录结构

```
app/            应用源码（FastAPI + 各处理模块）
  align/        台词对齐
  correct/      纠错分组
  extraction/   剧本提取
  split/        字幕拆分
  static/       前端（HTML/CSS/JS）
tests/          单元测试
docs/           项目文档
run.py          桌面入口（pywebview）
seeSRT.spec     PyInstaller 打包配置
```
