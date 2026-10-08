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
- 每行 ≤ 23 字符（英文半角，含空格 + 标点）或 ≤ 12 字（中文）。
- 超长在逗号/空格（英文单词）或中文标点（中文）边界换行。
- 每片段：英文最多 2 行，中文单行。
- 不增删改词，只做换行（纠错文本已在此前阶段确定）。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from app.correct.corrector import AlignedGroup
from app.lang import join_tokens, max_chars_for, tokenize_pairs, zh_units
from app.srt_parser import SrtSegment, format_timestamp, parse_timestamp

# 句子边界：英文句末标点（. ! ?）后跟空格
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
# 句子边界：中文句末标点（。！？；）
_SENTENCE_RE_ZH = re.compile(r"(?<=[。！？；])")

# 破折号：双连字符 "--" 或全角破折号 "—"，表示被打断/另起一段，作为硬分句边界。
# 用捕获组，使 re.split 结果中保留破折号本身，便于挂到前一句末尾。
_DASH_RE = re.compile(r"(--|—)")

_COMMA = ","
_SPACE = " "
# 中文换行优先断点：在逗号/顿号/分号等标点处换行
_ZH_BREAKS = "，、；。！？"
# 成对括号：换行时不允许拆开（书名号《》等）
_OPEN_BRACKETS = "《「『（【“‘"
_CLOSE_BRACKETS = "》」』）】”’"


def split_sentences(text: str, lang: str = "en") -> List[str]:
    """按句末标点切分句子，保留标点（中文用 。！？；）。"""
    if lang == "zh":
        return [s for s in _SENTENCE_RE_ZH.split(text.strip()) if s and s.strip()]
    return [s for s in _SENTENCE_RE.split(text.strip()) if s]


def _safe_zh_break(text: str, max_chars: int) -> int:
    """返回 ≤ max_chars 的安全断点：优先在中文标点处，且不拆开括号对（书名号等）。

    若候选断点落在未闭合的括号对内（如《书名》中间），则前移到最外层开括号之前，
    保证书名号及其中的书名保持完整。
    """
    chunk = text[:max_chars]
    pos = -1
    for ch in _ZH_BREAKS:
        idx = chunk.rfind(ch)
        if idx > pos:
            pos = idx
    if pos < 0:
        pos = max_chars - 1

    # 检测 pos 是否落在未闭合的括号对内；若是，前移到最外层开括号之前
    stack: List[int] = []
    for i in range(pos + 1):
        ch = text[i]
        if ch in _OPEN_BRACKETS:
            stack.append(i)
        elif ch in _CLOSE_BRACKETS:
            if stack:
                stack.pop()
    if stack and stack[0] > 0:
        pos = stack[0] - 1
    return pos


def _wrap_long_sentence_zh(sent: str, max_chars: int) -> List[str]:
    """把超长中文句在标点处换行，每行 ≤ max_chars 字，且不拆开括号对（书名号）。"""
    lines: List[str] = []
    remaining = sent.strip()
    while len(remaining) > max_chars:
        pos = _safe_zh_break(remaining, max_chars)
        lines.append(remaining[: pos + 1])
        remaining = remaining[pos + 1 :].lstrip()
    if remaining:
        lines.append(remaining)
    return lines


def _wrap_long_sentence(sent: str, max_chars: int, lang: str = "en") -> List[str]:
    """把超长句换行，每行 ≤ max_chars（英文在逗号/空格边界，中文在标点边界）。"""
    if lang == "zh":
        return _wrap_long_sentence_zh(sent, max_chars)

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


def wrap_lines(text: str, max_chars: int = 23, lang: str = "en") -> List[str]:
    """把一段文本按语义换行，每行 ≤ max_chars 字符。"""
    # 未命中片段的原文可能含达芬奇自带的换行符，先规范化空白：
    # 英文压成单个空格，中文直接去除空白，避免内嵌 \n 破坏「每片段 ≤ 2 行」的固定格式。
    if lang == "zh":
        text = re.sub(r"\s+", "", text).strip()
    else:
        text = re.sub(r"\s+", " ", text).strip()
    lines: List[str] = []
    for sent in split_sentences(text, lang):
        if len(sent) <= max_chars:
            lines.append(sent)
        else:
            lines.extend(_wrap_long_sentence(sent, max_chars, lang))
    return lines


def _split_dash_clauses(text: str) -> List[str]:
    """在破折号（-- / —）处把文本切成硬分句，破折号保留在前一句末尾。

    例："I didn't mean to-- I mean, I did" → ["I didn't mean to--", "I mean, I did"]。
    这样破折号后面的内容会单独成段，不再和破折号挤在同一段里。
    """
    text = text.strip()
    if not text:
        return [""]

    clauses: List[str] = []
    for i, part in enumerate(_DASH_RE.split(text)):
        if i % 2 == 1:
            # 破折号本身，挂到前一句末尾
            if clauses:
                clauses[-1] += part
            else:
                clauses.append(part)
        else:
            part = part.strip()
            if part:
                clauses.append(part)

    clauses = [c.strip() for c in clauses if c.strip()]
    return clauses or [""]


def _distribute_correct_text(
    segments: List[SrtSegment], correct_text: str, lang: str = "en"
) -> List[str]:
    """把正确文本按词/字级对齐分配回各原始片段，返回每个片段对应的正确文本。

    一条剧本台词可能对应多个相邻原始片段（达芬奇把一句话拆成多段）。此函数利用
    SequenceMatcher 把正确文本的 token 对齐回原始片段的 token，从而每个片段只得到
    它本应包含的内容，保证后续换行不跨片段、时间码不变。英文按词对齐，中文按字对齐。
    """
    n = len(segments)
    if n == 1:
        return [correct_text]

    if lang == "zh":
        return _distribute_correct_text_zh(segments, correct_text)

    # 原始 token 序列，记录每个 token 属于哪个片段
    orig_tokens: List[Tuple[str, int]] = []
    orig_norm: List[str] = []
    for si, seg in enumerate(segments):
        ot, on = tokenize_pairs(seg.text, lang)
        for tok, norm in zip(ot, on):
            orig_tokens.append((tok, si))
            orig_norm.append(norm)

    correct_tokens, correct_norm = tokenize_pairs(correct_text, lang)

    if not orig_tokens:
        # 原始片段无内容（罕见），把整段文本放第一段
        result = ["" for _ in range(n)]
        result[0] = correct_text
        return result

    matcher = SequenceMatcher(None, orig_norm, correct_norm, autojunk=False)

    seg_tokens: List[List[str]] = [[] for _ in range(n)]

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                seg_tokens[orig_tokens[i1 + k][1]].append(correct_tokens[j1 + k])
        elif tag in ("replace", "insert"):
            # 纠错后新增/替换的 token，分配到该区间起始位置所在的片段
            seg_idx = orig_tokens[i1][1] if i1 < len(orig_tokens) else n - 1
            for k in range(j2 - j1):
                seg_tokens[seg_idx].append(correct_tokens[j1 + k])
        # "delete"：原始识别多出的 token 被删除，无需处理

    return [join_tokens(ts, lang) for ts in seg_tokens]


def _distribute_correct_text_zh(
    segments: List[SrtSegment], correct_text: str
) -> List[str]:
    """中文版：内容逐字对齐后，再把正确文本里的标点重新附加回片段。

    中文 SRT 常缺标点，而剧本原文带标点。直接做字对齐时标点会干扰匹配，因此：
    1) 先忽略标点做内容 token 对齐，得到每个内容 token 归属的片段；
    2) 再按顺序扫描正确文本，把标点附加到它前面的内容 token 所在片段，
       保证剧本原文的标点（，。！？… 等）完整保留。
    """
    n = len(segments)

    orig_tokens: List[Tuple[str, int]] = []
    orig_norm: List[str] = []
    for si, seg in enumerate(segments):
        ot, on = tokenize_pairs(seg.text, "zh")
        for tok, norm in zip(ot, on):
            orig_tokens.append((tok, si))
            orig_norm.append(norm)

    correct_tokens, correct_norm = tokenize_pairs(correct_text, "zh")

    if not orig_tokens:
        result = ["" for _ in range(n)]
        result[0] = correct_text
        return result

    matcher = SequenceMatcher(None, orig_norm, correct_norm, autojunk=False)

    # 每个正确文本的内容 token → 归属片段索引
    token_seg: List[int] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                token_seg.append(orig_tokens[i1 + k][1])
        elif tag in ("replace", "insert"):
            seg_idx = orig_tokens[i1][1] if i1 < len(orig_tokens) else n - 1
            for _ in range(j2 - j1):
                token_seg.append(seg_idx)
        # "delete"：丢弃

    if not token_seg:
        # 正确文本无内容 token（如纯标点），整体放第一段
        result = ["" for _ in range(n)]
        result[0] = correct_text
        return result

    seg_parts: List[List[str]] = [[] for _ in range(n)]
    idx = 0
    pending_punct = ""
    for is_content, unit_text in zh_units(correct_text):
        if is_content:
            if pending_punct:
                # 标点附加到它前面的内容 token 所在片段（开头标点归第一个片段）
                seg_parts[token_seg[0] if idx == 0 else token_seg[idx - 1]].append(
                    pending_punct
                )
                pending_punct = ""
            seg_parts[token_seg[idx]].append(unit_text)
            idx += 1
        else:
            pending_punct += unit_text
    if pending_punct:
        seg_parts[token_seg[-1]].append(pending_punct)

    return ["".join(p) for p in seg_parts]


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


def _emit_segments(
    clause_lines: List[List[str]], start_ms: int, end_ms: int, max_lines: int
) -> List[SrtSegment]:
    """把多个「硬分句」各自换行后拆成片段，分句之间强制分段。

    每个分句（如被破折号切开的两段）至少对应一个片段，绝不跨分句合并；
    分句内部若仍超过 max_lines 行，再按字符占比在其内部细分时间。
    """
    total_chars = sum(len(ln) for lines in clause_lines for ln in lines) or 1
    duration = max(end_ms - start_ms, 0)

    segments: List[SrtSegment] = []
    seg_start = start_ms
    for idx, lines in enumerate(clause_lines):
        clause_chars = sum(len(ln) for ln in lines) or 0
        if idx == len(clause_lines) - 1:
            seg_end = end_ms
        else:
            seg_end = seg_start + round(duration * clause_chars / total_chars)
        segments.extend(_emit_range(lines, seg_start, seg_end, max_lines))
        seg_start = seg_end
    return segments


def split_group(
    group: AlignedGroup,
    max_chars: Optional[int] = None,
    max_lines: Optional[int] = None,
    lang: Optional[str] = None,
) -> List[SrtSegment]:
    """把一个纠错组拆分为新的 SRT 片段，保留原始片段时间轴。

    - 把正确文本按词/字分配回各原始片段；
    - 每个原始片段独立换行，保持其原始 start/end 时间码；
    - 破折号（-- / —）作为硬分句边界，破折号后的内容单独成段；
    - 仅当单个原始片段（或单个分句）换行后超 max_lines 行时才在其内部细分时间。

    语言优先取显式参数，其次取 group.lang。每行字符上限与行数上限都按语言自动决定：
    中文每行 ≤ 12 字且单行（每片段 1 行），英文每行 ≤ 23 字符且每片段 ≤ 2 行。
    """
    lang = lang or getattr(group, "lang", "en")
    if max_chars is None:
        max_chars = max_chars_for(lang)
    if max_lines is None:
        max_lines = 1 if lang == "zh" else 2

    segments = group.segments

    # 中文短句合并：正确文本若只是一个短分句（无破折号、无句末切分、≤ 一行），
    # 却命中了多个相邻原始片段（达芬奇/识别把一句话拆成了多段），应合并为单个片段，
    # 而不是被原始片段边界拆散。时间跨度取首片段 start → 末片段 end，整体时间轴不变。
    if lang == "zh" and len(segments) > 1:
        stripped = (group.correct_text or "").strip()
        if stripped and len(_split_dash_clauses(stripped)) == 1:
            lines = wrap_lines(stripped, max_chars, lang)
            if len(lines) == 1:
                return [
                    SrtSegment(
                        index=1,
                        start=segments[0].start,
                        end=segments[-1].end,
                        text=lines[0],
                    )
                ]

    texts = _distribute_correct_text(segments, group.correct_text, lang)

    out: List[SrtSegment] = []
    for seg, seg_text in zip(segments, texts):
        seg_text = (seg_text or "").strip()
        if not seg_text:
            # 分配结果为空（如原始片段全部是识别多余词被删除）时回退为原文本
            seg_text = seg.text

        start_ms = parse_timestamp(seg.start)
        end_ms = parse_timestamp(seg.end)
        clauses = _split_dash_clauses(seg_text)
        clause_lines = [wrap_lines(c, max_chars, lang) or [""] for c in clauses]
        out.extend(_emit_segments(clause_lines, start_ms, end_ms, max_lines))

    return out
