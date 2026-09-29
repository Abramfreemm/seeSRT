"""字幕片段与剧本英文台词的对齐器。

把达芬奇识别的 SRT 片段按时间顺序对齐到剧本台词，用于后续纠错。
采用「词级最长公共子序列（LCS）对齐」：把整集 SRT 与剧本台词都展开为词序列，
做全局 diff，再把每个片段映射到其命中的台词行。相比贪心前缀匹配，它能天然处理：
- 一句台词拆成多个片段；
- 达芬奇漏识别（丢词）导致的错位；
- 识别错误（错词/多词/少词，如 "Will" vs "Windsor"、"grand major" vs "Grand Mage"）；
- 音效标记 [MUSIC PLAYING] 等（跳过，不干扰对齐）。

仅依赖标准库，确定性算法，零幻觉。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import List, Optional

from app.srt_parser import SrtSegment, is_sound_marker


def _normalize(s: str) -> str:
    """归一化：小写 + 去所有非字母数字字符，用于相似度比较。"""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _words(text: str) -> List[str]:
    """把文本切分为归一化词元（收缩形式如 "don't" → "dont" 保持为单个词元）。"""
    return [w for w in (_normalize(tok) for tok in text.split()) if w]


def align(
    script_en_lines: List[str],
    srt_segments: List[SrtSegment],
    threshold: float = 0.55,
) -> List[Optional[int]]:
    """把 SRT 片段对齐到剧本英文台词。

    返回与 srt_segments 等长的列表，每项为该片段命中的台词索引（None 表示未命中）。

    算法：词级 LCS 对齐。
    1. 剧本台词展开为词序列，记录每个词属于哪一句台词。
    2. SRT（跳过音效标记）展开为词序列，记录每个词属于哪个片段。
    3. 用 SequenceMatcher 求两个词序列的最长公共子序列（匹配块）。
    4. 对每个片段，统计其词中命中各台词的数量，占比达到 threshold 者即认定命中该台词。
    """
    result: List[Optional[int]] = [None] * len(srt_segments)

    # 剧本词序列 + 词 → 台词索引
    script_seq: List[str] = []
    script_line_of: List[int] = []
    for li, line in enumerate(script_en_lines):
        for w in _words(line):
            script_seq.append(w)
            script_line_of.append(li)

    # SRT 词序列 + 词 → 片段索引（跳过音效标记）
    srt_seq: List[str] = []
    srt_seg_of: List[int] = []
    for i, seg in enumerate(srt_segments):
        if is_sound_marker(seg.text):
            continue
        for w in _words(seg.text):
            srt_seq.append(w)
            srt_seg_of.append(i)

    if not script_seq or not srt_seq:
        return result

    # 词级 LCS 匹配块：把 SRT 词位置映射到命中的台词索引
    matcher = SequenceMatcher(None, srt_seq, script_seq, autojunk=False)
    srt_word_line: dict = {}
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            srt_word_line[a + k] = script_line_of[b + k]

    # 每个片段：统计命中的台词，按占比投票
    seg_positions: dict = defaultdict(list)
    for pos, sidx in enumerate(srt_seg_of):
        seg_positions[sidx].append(pos)

    for sidx, positions in seg_positions.items():
        votes = Counter(srt_word_line[p] for p in positions if p in srt_word_line)
        if not votes:
            continue
        line_idx, matched = votes.most_common(1)[0]
        if matched / len(positions) >= threshold:
            result[sidx] = line_idx

    return result
