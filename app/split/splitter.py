"""字幕拆分器：按「每行 23 字符、每片段 2 行」规则拆分，时间轴按字符占比分配。

规则（剪辑师规范）：
- 每行 ≤ 23 字符（英文半角，含空格 + 标点）。
- 超长在逗号/空格（单词）边界换行。
- 每片段最多 2 行。
- 超过 2 行拆新片段，时间轴按字符数占比分配。
- 不增删改词，只做换行。
"""

from __future__ import annotations

import re
from typing import List

from app.correct.corrector import AlignedGroup
from app.srt_parser import SrtSegment, format_timestamp, parse_timestamp

# 句子边界：句末标点（. ! ?）后跟空格
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_COMMA = ","
_SPACE = " "


def split_sentences(text: str) -> List[str]:
    """按句末标点切分句子，保留标点。"""
    return [s for s in _SENTENCE_RE.split(text.strip()) if s]


def _wrap_long_sentence(sent: str, max_chars: int) -> List[str]:
    """把超长句在逗号/空格边界换行，每行 ≤ max_chars。"""
    lines: List[str] = []
    remaining = sent.strip()
    while len(remaining) > max_chars:
        chunk = remaining[:max_chars]
        # 优先在逗号处换行，其次空格
        pos = chunk.rfind(_COMMA)
        if pos == -1:
            pos = chunk.rfind(_SPACE)
        if pos <= 0:
            pos = max_chars - 1
        lines.append(remaining[: pos + 1].strip())
        remaining = remaining[pos + 1 :].strip()
    if remaining:
        lines.append(remaining)
    return lines


def wrap_lines(text: str, max_chars: int = 23) -> List[str]:
    """把一段文本按语义换行，每行 ≤ max_chars 字符。"""
    # 未命中片段的原文可能含达芬奇自带的换行符，先把连续空白规范化为单个空格，
    # 避免内嵌 \n 破坏「每片段 ≤ 2 行」的固定格式。
    text = re.sub(r"\s+", " ", text).strip()
    lines: List[str] = []
    for sent in split_sentences(text):
        if len(sent) <= max_chars:
            lines.append(sent)
        else:
            lines.extend(_wrap_long_sentence(sent, max_chars))
    return lines


def split_group(
    group: AlignedGroup, max_chars: int = 23, max_lines: int = 2
) -> List[SrtSegment]:
    """把一个纠错组拆分为新的 SRT 片段（含时间轴按字符占比分配）。"""
    lines = wrap_lines(group.correct_text, max_chars)
    if not lines:
        lines = [""]

    start_ms = parse_timestamp(group.start)
    end_ms = parse_timestamp(group.end)
    duration = max(end_ms - start_ms, 0)
    total_chars = sum(len(l) for l in lines) or 1

    segments: List[SrtSegment] = []
    seg_start = start_ms
    i = 0
    while i < len(lines):
        seg_lines = lines[i : i + max_lines]
        seg_chars = sum(len(l) for l in seg_lines)
        if i + max_lines >= len(lines):
            seg_end = end_ms
        else:
            seg_end = seg_start + round(duration * seg_chars / total_chars)
        segments.append(
            SrtSegment(
                index=len(segments) + 1,
                start=format_timestamp(seg_start),
                end=format_timestamp(seg_end),
                text="\n".join(seg_lines),
            )
        )
        seg_start = seg_end
        i += max_lines

    return segments
