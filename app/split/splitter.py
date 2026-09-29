"""字幕拆分器：按「每行 23 字符、每片段 2 行」规则拆分。

时间轴策略（与达芬奇时间轴保持一致）：
- 原始 SRT 每个片段都带有自己的 start/end 时间码，拆分时必须原样保留，绝不因文本
  换行/纠错而重新分配整体时间轴。
- 当一条剧本台词命中多个相邻原始片段时（达芬奇把一句话拆成多段），先把正确文本
  按「词级对齐」分配回各原始片段，再对每个原始片段独立换行；每个原始片段的
  start/end 保持不变。只有单个原始片段换行后仍超过 2 行时，才在其内部按字符占比
  细分时间（这是强制 2 行不可避免的情况）。
- 未命中片段保持原时间码，仅做换行规范化。

规则（剪辑师规范）：
- 每行 ≤ 23 字符（英文半角，含空格 + 标点）。
- 超长在逗号/空格（单词）边界换行。
- 每片段最多 2 行。
- 不增删改词，只做换行。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Tuple

from app.correct.corrector import AlignedGroup
from app.srt_parser import SrtSegment, format_timestamp, parse_timestamp

# 句子边界：句末标点（. ! ?）后跟空格
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_COMMA = ","
_SPACE = " "


def _normalize_word(word: str) -> str:
    """归一化单词：小写 + 去所有非字母数字字符，用于词级对齐比较。"""
    return re.sub(r"[^a-z0-9]", "", word.lower())


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


def _distribute_correct_text(
    segments: List[SrtSegment], correct_text: str
) -> List[str]:
    """把正确文本按词级对齐分配回各原始片段，返回每个片段对应的正确文本。

    一条剧本台词可能对应多个相邻原始片段（达芬奇把一句话拆成多段）。此函数利用
    SequenceMatcher 把正确文本的词对齐回原始片段的词，从而每个片段只得到它本应
    包含的词，保证后续换行不跨片段、时间码不变。
    """
    n = len(segments)
    if n == 1:
        return [correct_text]

    # 原始词序列，记录每个词属于哪个片段
    orig_words: List[Tuple[str, int]] = []
    for si, seg in enumerate(segments):
        for w in seg.text.split():
            orig_words.append((w, si))

    correct_words = correct_text.split()

    if not orig_words:
        # 原始片段无词（罕见），把整段文本放第一段
        result = ["" for _ in range(n)]
        result[0] = correct_text
        return result

    matcher = SequenceMatcher(
        None,
        [_normalize_word(w) for w, _ in orig_words],
        [_normalize_word(w) for w in correct_words],
        autojunk=False,
    )

    seg_words: List[List[str]] = [[] for _ in range(n)]

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                seg_words[orig_words[i1 + k][1]].append(correct_words[j1 + k])
        elif tag in ("replace", "insert"):
            # 纠错后新增/替换的词，分配到该区间起始位置所在的片段
            seg_idx = orig_words[i1][1] if i1 < len(orig_words) else n - 1
            for k in range(j2 - j1):
                seg_words[seg_idx].append(correct_words[j1 + k])
        # "delete"：原始识别多出的词被删除，无需处理

    return [" ".join(ws) for ws in seg_words]


def _emit_range(
    lines: List[str], start_ms: int, end_ms: int, max_lines: int
) -> List[SrtSegment]:
    """把一组行（属于同一个原始片段）拆成 ≤ max_lines 行的片段。

    绝大多数情况下 lines 不超过 max_lines，此时直接返回单个片段，时间码完全等于
    原始片段。只有当单个原始片段换行后仍超 2 行时，才在其内部按字符占比细分时间。
    """
    total_chars = sum(len(ln) for ln in lines) or 1
    duration = max(end_ms - start_ms, 0)

    segments: List[SrtSegment] = []
    seg_start = start_ms
    i = 0
    while i < len(lines):
        seg_lines = lines[i : i + max_lines]
        seg_chars = sum(len(ln) for ln in seg_lines)
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


def split_group(
    group: AlignedGroup, max_chars: int = 23, max_lines: int = 2
) -> List[SrtSegment]:
    """把一个纠错组拆分为新的 SRT 片段，保留原始片段时间轴。

    - 把正确文本按词分配回各原始片段；
    - 每个原始片段独立换行，保持其原始 start/end 时间码；
    - 仅当单个原始片段换行后超 max_lines 行时才在其内部细分时间。
    """
    segments = group.segments
    texts = _distribute_correct_text(segments, group.correct_text)

    out: List[SrtSegment] = []
    for seg, seg_text in zip(segments, texts):
        seg_text = (seg_text or "").strip()
        if not seg_text:
            # 分配结果为空（如原始片段全部是识别多余词被删除）时回退为原文本
            seg_text = seg.text

        start_ms = parse_timestamp(seg.start)
        end_ms = parse_timestamp(seg.end)
        lines = wrap_lines(seg_text, max_chars)
        if not lines:
            lines = [""]
        out.extend(_emit_range(lines, start_ms, end_ms, max_lines))

    return out
