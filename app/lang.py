"""语言检测与分词工具。

- tokenize: 英文按空格分词并归一化；中文按单字切分（英文/数字片段保留为整体）。
- tokenize_pairs / join_tokens: 用于把正确文本分配回原始片段并重建。

供对齐器、拆分器、diff 等多处复用，保证中英文行为一致。
"""

from __future__ import annotations

import re
from typing import List

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# 中文 token：单个汉字，或连续英文/数字
_ZH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")

# 每行字符上限：中文 12 字，英文 23 字符
MAX_CHARS = {"zh": 12, "en": 23}


def normalize_en(word: str) -> str:
    """英文单词归一化：小写 + 去所有非字母数字字符。"""
    return re.sub(r"[^a-z0-9]", "", word.lower())


def tokenize(text: str, lang: str) -> List[str]:
    """把文本切分为可对齐的 token 序列。

    - 英文：按空格分词，再归一化（小写 + 去标点）。
    - 中文：按单字切分，连续的英文/数字作为一个整体 token（小写归一）。
    """
    if lang == "en":
        return [w for w in (normalize_en(t) for t in text.split()) if w]
    tokens: List[str] = []
    for chunk in _ZH_TOKEN_RE.findall(text):
        if _CJK_RE.match(chunk):
            tokens.append(chunk)
        else:
            tokens.append(chunk.lower())
    return tokens


def tokenize_pairs(text: str, lang: str):
    """返回 (原始 token 列表, 归一化 token 列表)，两者一一对应。

    用于「把正确文本分配回各原始片段」：用归一化 token 做对齐，用原始 token 重建文本。
    """
    if lang == "en":
        orig: List[str] = []
        norm: List[str] = []
        for t in text.split():
            n = normalize_en(t)
            if n:
                orig.append(t)
                norm.append(n)
        return orig, norm
    chunks = _ZH_TOKEN_RE.findall(text)
    norm = [c if _CJK_RE.match(c) else c.lower() for c in chunks]
    return chunks, norm


def join_tokens(tokens: List[str], lang: str) -> str:
    """把 token 列表拼回文本（英文用空格，中文直接拼接）。"""
    return " ".join(tokens) if lang == "en" else "".join(tokens)


def max_chars_for(lang: str) -> int:
    """返回该语言每行字符上限。"""
    return MAX_CHARS.get(lang, MAX_CHARS["en"])
