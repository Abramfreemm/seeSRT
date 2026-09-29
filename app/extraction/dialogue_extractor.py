"""台词提取：从剧本文本行识别「集 → 场景 → 台词对」。

支持多种真实剧本格式：
- 集标题：`第X集`（中文数字，如「第一集」）/ `第X集`（阿拉伯数字，如「第1集」）/ `EPISODE X`。
- 场景号：`N-N`（单独一行）或 `N-N 场景位置`（编号与位置同行）。
- 场景位置：`场景：…`（中文）或 `N-N DAY - INT. …`（英文，行首 `N-N ` 开头），非台词。
- 人物表：`人物：…` / `主要人物：…`（中文）或 `Characters: …`（英文），非台词。
- 舞台提示：`△…` / `▲…` / `【…】` / `#…` 开头，非台词。
- 中文台词：全角冒号 `：` 或半角冒号 `:` 之后的中文内容（角色名在前）。
- 英文台词：半角冒号 `:` 之后的内容（角色名在前），或紧跟在中文台词后的纯英文行。
- 过滤：集标题之前的元信息（标题/大纲/人物小传等）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Dialogue:
    """中英对照台词对。"""

    text_zh: str
    text_en: str


@dataclass
class Scene:
    """一集内的一个场景。"""

    scene_no: str  # 如 "1-1"
    dialogues: List[Dialogue] = field(default_factory=list)


@dataclass
class Episode:
    """一集。"""

    episode_no: int
    scenes: List[Scene] = field(default_factory=list)


# 集标题：第一集 / 第十集 / 第五十集（中文数字）
_EPISODE_CN_RE = re.compile(r"^第([一二三四五六七八九十]+)集")
# 集标题：第1集（阿拉伯数字）
_EPISODE_AR_RE = re.compile(r"^第(\d+)集")
# 集标题：EPISODE 1（英文）
_EPISODE_EN_RE = re.compile(r"^EPISODE\s+(\d+)", re.IGNORECASE)
# 场景号 + 位置同行："1-1 夜 外" / "7-1 街道 夜 外" / "1-1 DAY - INT. …"
_LOCATION_RE = re.compile(r"^(\d+)-(\d+)\s")
# 纯场景号行：单独一行的 "1-1"
_SCENE_RE = re.compile(r"^(\d+)-(\d+)$")
# 英文括号舞台指示（如 "(takes out a communication crystal)"）
_PAREN_RE = re.compile(r"\([^)]*\)")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
# 中英混排拆分：中文句末标点（。！？…）之后紧跟英文字母处切开
_MIXED_SPLIT_RE = re.compile(r"(?<=[。！？…])\s*(?=[A-Za-z])")

_CN_DIGIT = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}


def cn_num_to_int(s: str) -> int:
    """中文数字（一~九十九）转整数。"""
    if s == "十":
        return 10
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _CN_DIGIT.get(left, 1) if left else 1
        ones = _CN_DIGIT.get(right, 0) if right else 0
        return tens * 10 + ones
    return _CN_DIGIT.get(s, 0)


def _strip_stage_directions(en: str) -> str:
    """去除英文台词中的括号舞台指示 ( ... )，并压缩空白。"""
    en = _PAREN_RE.sub(" ", en)
    return " ".join(en.split()).strip()


def _split_mixed(text: str) -> tuple:
    """把中英混排台词拆成 (中文, 英文)；无法拆分时英文为空串。"""
    parts = _MIXED_SPLIT_RE.split(text, maxsplit=1)
    if len(parts) == 2:
        zh = parts[0].strip()
        en = _strip_stage_directions(parts[1])
        return zh, en
    return text, ""


def _is_non_dialogue(line: str) -> bool:
    """判断是否为非台词行（舞台提示/标记/场景位置/人物表）。"""
    if line.startswith(("△", "▲", "【", "#")):
        return True
    if line.startswith(("场景", "人物", "主要人物")):
        return True
    if line.lower().startswith("characters"):
        return True
    return False


def extract_dialogues(lines: List[str]) -> List[Episode]:
    """从剧本文本行提取「集 → 场景 → 台词对」结构。"""
    episodes: List[Episode] = []
    cur_ep: Optional[Episode] = None
    cur_scene: Optional[Scene] = None
    pending_zh: Optional[str] = None

    def flush_zh() -> None:
        nonlocal pending_zh
        if pending_zh is not None and cur_scene is not None:
            cur_scene.dialogues.append(Dialogue(text_zh=pending_zh, text_en=""))
        pending_zh = None

    def add_pair(zh: str, en: str) -> None:
        cur_scene.dialogues.append(Dialogue(text_zh=zh, text_en=en))

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # 集标题（中文数字 / 阿拉伯数字 / 英文）
        ep_no: Optional[int] = None
        m = _EPISODE_CN_RE.match(line)
        if m:
            ep_no = cn_num_to_int(m.group(1))
        else:
            m = _EPISODE_AR_RE.match(line)
            if m:
                ep_no = int(m.group(1))
            else:
                m = _EPISODE_EN_RE.match(line)
                if m:
                    ep_no = int(m.group(1))
        if ep_no is not None:
            if cur_ep is not None and cur_ep.episode_no == ep_no:
                continue  # 同一集的重复标题（如「第1集」+「EPISODE 1」）
            flush_zh()
            cur_ep = Episode(episode_no=ep_no)
            episodes.append(cur_ep)
            cur_scene = None
            continue

        # 尚未进入正文（未遇到集标题），跳过元信息
        if cur_ep is None:
            continue

        # 场景号 + 位置同行（"1-1 夜 外 …"）
        m = _LOCATION_RE.match(line)
        if m:
            scene_no = f"{m.group(1)}-{m.group(2)}"
            if cur_scene is None or cur_scene.scene_no != scene_no:
                flush_zh()
                cur_scene = Scene(scene_no=scene_no)
                cur_ep.scenes.append(cur_scene)
            continue

        # 纯场景号 "1-1"
        m = _SCENE_RE.match(line)
        if m:
            scene_no = f"{m.group(1)}-{m.group(2)}"
            if cur_scene is None or cur_scene.scene_no != scene_no:
                flush_zh()
                cur_scene = Scene(scene_no=scene_no)
                cur_ep.scenes.append(cur_scene)
            continue

        if cur_scene is None:
            continue

        # 非台词行：舞台提示 / 标记 / 场景位置 / 人物表
        if _is_non_dialogue(line):
            continue

        # 中文台词（全角冒号）
        if "：" in line:
            flush_zh()
            text = line.split("：", 1)[1].strip()
            zh, en = _split_mixed(text)
            if en:
                add_pair(zh, en)
            else:
                pending_zh = zh
            continue

        # 半角冒号：中文台词（角色:中文）或英文台词（Role: English）
        if ":" in line:
            _, _, text = line.partition(":")
            text = _strip_stage_directions(text)
            if _CJK_RE.search(text):
                flush_zh()
                zh, en = _split_mixed(text)
                if en:
                    add_pair(zh, en)
                else:
                    pending_zh = zh
            elif pending_zh is not None:
                add_pair(pending_zh, text)
                pending_zh = None
            else:
                add_pair("", text)
            continue

        # 无冒号：纯英文行视为紧邻中文台词的英译
        if _ASCII_LETTER_RE.search(line) and not _CJK_RE.search(line):
            text = _strip_stage_directions(line)
            if pending_zh is not None:
                add_pair(pending_zh, text)
                pending_zh = None
            else:
                add_pair("", text)
            continue

    flush_zh()

    # 合并重复集号（如目录 + 正文 + EPISODE 标题重复造成的同一集多次出现），
    # 按首次出现的顺序保留，重复集的场景追加到已有集。
    merged: dict = {}
    for ep in episodes:
        if ep.episode_no in merged:
            merged[ep.episode_no].scenes.extend(ep.scenes)
        else:
            merged[ep.episode_no] = ep
    return list(merged.values())
