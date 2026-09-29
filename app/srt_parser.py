"""SRT 字幕解析与写出模块。

实现达芬奇/剪映等工具导出的 SRT 字幕的解析与无损写出。
仅依赖 Python 标准库，无第三方依赖。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class SrtSegment:
    """一条 SRT 字幕片段。

    Attributes:
        index: 片段序号（解析时保留原始序号，写出时按顺序重新编号）。
        start: 开始时间原始字符串，如 "00:00:01,000"。
        end: 结束时间原始字符串。
        text: 字幕文本，可能含换行（多行）。
    """

    index: int
    start: str
    end: str
    text: str


# 时间戳：HH:MM:SS,mmm 或 HH:MM:SS.mmm（毫秒 1~3 位）
_TIMESTAMP_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
# 时间轴行：start --> end（行尾可带 X1/Y1 等位置坐标，坐标忽略）
_TIME_LINE_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
# 音效/环境声标记：整段被方括号包裹，如 "[MUSIC PLAYING]"
_SOUND_MARKER_RE = re.compile(r"^\[[^\]]*\]$")


def is_sound_marker(text: str) -> bool:
    """判断字幕文本是否为音效/环境声标记（如 "[MUSIC PLAYING]"）。"""
    return bool(_SOUND_MARKER_RE.match(text.strip()))


def parse_timestamp(ts: str) -> int:
    """把时间字符串解析为毫秒整数。"""
    m = _TIMESTAMP_RE.fullmatch(ts.strip())
    if not m:
        raise ValueError(f"非法时间戳: {ts!r}")
    h, mm, ss, ms = m.groups()
    ms = ms.ljust(3, "0")
    return int(h) * 3_600_000 + int(mm) * 60_000 + int(ss) * 1_000 + int(ms)


def format_timestamp(ms: int) -> str:
    """把毫秒整数格式化为 SRT 时间字符串 HH:MM:SS,mmm。"""
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms3 = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms3:03d}"


def _detect_encoding(data: bytes) -> str:
    """检测字节流编码：BOM 优先，其次 utf-8 / gb18030（覆盖 GBK/GB2312）。"""
    if data.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
        return "utf-8-sig"
    if data.startswith(b"\xff\xfe"):  # UTF-16 LE
        return "utf-16"
    if data.startswith(b"\xfe\xff"):  # UTF-16 BE
        return "utf-16"
    for enc in ("utf-8", "gb18030"):
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def parse_srt(content: str) -> List[SrtSegment]:
    """解析 SRT 文本为片段列表。

    兼容：序号可缺省、时间轴可带坐标、文本可多行、行尾 \\r\\n、带 BOM。
    """
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]

    segments: List[SrtSegment] = []
    # 按一个或多个空行分块
    blocks = re.split(r"\n[ \t]*\n", text.strip("\n"))
    for block in blocks:
        parsed = _parse_block(block)
        if parsed is None:
            continue
        start, end, seg_text, index = parsed
        if index is None:
            index = len(segments) + 1
        segments.append(SrtSegment(index=index, start=start, end=end, text=seg_text))
    return segments


def _parse_block(block: str) -> Optional[Tuple[str, str, str, Optional[int]]]:
    """解析单个块，返回 (start, end, text, index)；非字幕块返回 None。"""
    lines = block.split("\n")
    # 去块内首尾空行
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None

    idx = 0
    index: Optional[int] = None
    if lines[idx].strip().isdigit():
        index = int(lines[idx].strip())
        idx += 1

    # 查找时间轴行（容忍序号与时间轴之间的异常行）
    time_line_idx = -1
    for i in range(idx, len(lines)):
        if _TIME_LINE_RE.search(lines[i]):
            time_line_idx = i
            break
    if time_line_idx == -1:
        return None  # 非字幕块

    m = _TIME_LINE_RE.search(lines[time_line_idx])
    start, end = m.group(1), m.group(2)
    seg_text = "\n".join(lines[time_line_idx + 1 :]).strip()
    return start, end, seg_text, index


def write_srt(segments: List[SrtSegment]) -> str:
    """把片段列表写为 SRT 文本（序号重编号，时间轴/文本原样保留）。"""
    parts = []
    for i, seg in enumerate(segments, start=1):
        parts.append(f"{i}\n{seg.start} --> {seg.end}\n{seg.text}")
    return "\n\n".join(parts) + "\n"


def read_srt_file(path) -> List[SrtSegment]:
    """读取 SRT 文件（自动检测编码）并解析。"""
    data = Path(path).read_bytes()
    enc = _detect_encoding(data)
    return parse_srt(data.decode(enc, errors="replace"))


def write_srt_file(path, segments: List[SrtSegment]) -> None:
    """把片段列表写为 SRT 文件（UTF-8，\\n 换行）。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(write_srt(segments))
