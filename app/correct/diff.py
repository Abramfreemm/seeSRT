"""词级 diff：产出「差异标红」所需的结构化差异操作。

把「原始字幕文本」与「纠错后文本」做逐词比较，供前端以红色高亮展示改动：
- equal：不变；
- replace：单词被改写（大小写/拼写修正），旧词删除线 + 新词标红；
- insert：新增词（漏词补全），标红；
- delete：删除词，删除线。

仅依赖标准库 difflib，确定性，零幻觉。
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, List


def diff_words(old: str, new: str) -> List[Dict[str, str]]:
    """逐词比较 old 与 new，返回差异操作列表。

    每个元素为 {"op": "equal|delete|insert|replace", "old": str, "new": str}。
    """
    a = old.split()
    b = new.split()
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    ops: List[Dict[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for w in a[i1:i2]:
                ops.append({"op": "equal", "old": w, "new": w})
        elif tag == "delete":
            for w in a[i1:i2]:
                ops.append({"op": "delete", "old": w, "new": ""})
        elif tag == "insert":
            for w in b[j1:j2]:
                ops.append({"op": "insert", "old": "", "new": w})
        elif tag == "replace":
            old_words = a[i1:i2]
            new_words = b[j1:j2]
            for k in range(max(len(old_words), len(new_words))):
                ow = old_words[k] if k < len(old_words) else ""
                nw = new_words[k] if k < len(new_words) else ""
                ops.append({"op": "replace", "old": ow, "new": nw})

    return ops
