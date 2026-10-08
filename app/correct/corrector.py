"""纠错器：根据对齐结果，为每个片段组确定正确文本。

- 命中台词：correct_text = 剧本原文（大小写/拼写以剧本为准）。
- 未命中：correct_text = 原文本，标记待人工复核。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.srt_parser import SrtSegment


@dataclass
class AlignedGroup:
    """一组相邻片段的纠错结果（命中同一台词，或未命中）。"""

    dialogue_index: Optional[int]  # 命中台词索引；None = 未命中
    segments: List[SrtSegment] = field(default_factory=list)
    correct_text: str = ""  # 纠错后的正确文本
    reviewed: bool = False  # 未命中片段是否已人工复核确认
    lang: str = "en"  # 本组语言（"en" / "zh"），决定分词/换行/差异展示方式

    @property
    def matched(self) -> bool:
        return self.dialogue_index is not None

    @property
    def original_text(self) -> str:
        """组内片段原始文本拼接（用于差异展示）。"""
        return " ".join(s.text for s in self.segments)

    @property
    def start(self) -> str:
        return self.segments[0].start

    @property
    def end(self) -> str:
        return self.segments[-1].end


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _is_all_caps(text: str) -> bool:
    """判断文本是否整体为大写（忽略标点/数字/空格）。"""
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _sentence_case(text: str) -> str:
    """把全大写文本转为句首大写：先归一化空白，再按句末标点分句。"""
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    return " ".join(s[:1].upper() + s[1:].lower() for s in sentences)


def _normalize_unmatched_case(text: str) -> str:
    """未命中片段的大小写规范化：仅当整体全大写时转为句首大写。"""
    if _is_all_caps(text):
        return _sentence_case(text)
    return text


def group_corrections(
    srt_segments: List[SrtSegment],
    alignment: List[Optional[int]],
    script_lines: List[str],
    lang: str = "en",
) -> List[AlignedGroup]:
    """根据对齐结果分组，产出纠错组。

    - 连续命中同一台词的片段合并为一组，correct_text = 剧本原文。
    - 未命中片段各自成组，correct_text = 原文本（待人工复核）。
    - 中文不做英文大小写规范化，仅保留原文。
    """
    groups: List[AlignedGroup] = []
    i = 0
    n = len(srt_segments)
    while i < n:
        di = alignment[i]
        if di is None:
            unmatched = srt_segments[i].text
            if lang == "en":
                unmatched = _normalize_unmatched_case(unmatched)
            groups.append(
                AlignedGroup(
                    dialogue_index=None,
                    segments=[srt_segments[i]],
                    correct_text=unmatched,
                    lang=lang,
                )
            )
            i += 1
        else:
            segs = [srt_segments[i]]
            j = i + 1
            while j < n and alignment[j] == di:
                segs.append(srt_segments[j])
                j += 1
            groups.append(
                AlignedGroup(
                    dialogue_index=di,
                    segments=segs,
                    correct_text=script_lines[di],
                    lang=lang,
                )
            )
            i = j
    return groups
