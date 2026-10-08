"""JSON 持久化：把内存态 STATE 保存到磁盘，重启后恢复（中途退出续做）。

STATE 结构：
    episodes:  List[Episode]                 剧本台词库
    srts:      Dict[int, List[SrtSegment]]   每集 SRT 片段
    groups:    Dict[int, List[AlignedGroup]] 每集处理结果（correct_text 含用户编辑）
    srt_filenames: Dict[int, str]            每集原始文件名（导出命名用）

序列化：dataclass 转 dict；反序列化：dict 转 dataclass。
JSON 中字典键只能是字符串，int 键在保存/读取时做转换。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from app.correct.corrector import AlignedGroup
from app.extraction.dialogue_extractor import Dialogue, Episode, Scene
from app.srt_parser import SrtSegment


def _default_state_path() -> Path:
    """确定 state.json 位置：打包后放 exe 同级 data/，开发时放项目 data/。"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return Path(sys.executable).resolve().parent / "data" / "state.json"
    return Path(__file__).resolve().parent.parent / "data" / "state.json"


DEFAULT_STATE_PATH = _default_state_path()


def _episode_to_dict(ep: Episode) -> dict:
    return {
        "episode_no": ep.episode_no,
        "scenes": [
            {"scene_no": sc.scene_no, "dialogues": [asdict(d) for d in sc.dialogues]}
            for sc in ep.scenes
        ],
    }


def _episode_from_dict(d: dict) -> Episode:
    return Episode(
        episode_no=d["episode_no"],
        scenes=[
            Scene(
                scene_no=sc["scene_no"],
                dialogues=[Dialogue(**di) for di in sc["dialogues"]],
            )
            for sc in d["scenes"]
        ],
    )


def _group_to_dict(g: AlignedGroup) -> dict:
    return {
        "dialogue_index": g.dialogue_index,
        "correct_text": g.correct_text,
        "reviewed": g.reviewed,
        "lang": g.lang,
        "segments": [asdict(s) for s in g.segments],
    }


def _group_from_dict(d: dict) -> AlignedGroup:
    return AlignedGroup(
        dialogue_index=d["dialogue_index"],
        correct_text=d["correct_text"],
        reviewed=d.get("reviewed", False),
        lang=d.get("lang", "en"),
        segments=[SrtSegment(**s) for s in d["segments"]],
    )


def _int_keyed(src: Dict) -> Dict[int, object]:
    return {int(k): v for k, v in src.items()}


def dump_state(state: Dict) -> dict:
    """把内存态 STATE 转为可 JSON 序列化的 dict。"""
    return {
        "episodes": [_episode_to_dict(e) for e in state.get("episodes", [])],
        "srts": {str(k): [asdict(s) for s in v] for k, v in state.get("srts", {}).items()},
        "groups": {
            str(k): [_group_to_dict(g) for g in v]
            for k, v in state.get("groups", {}).items()
        },
        "srt_filenames": {str(k): v for k, v in state.get("srt_filenames", {}).items()},
    }


def restore_state(data: dict) -> Dict:
    """把磁盘 dict 还原为内存态 STATE。"""
    return {
        "episodes": [_episode_from_dict(e) for e in data.get("episodes", [])],
        "srts": {
            int(k): [SrtSegment(**s) for s in v]
            for k, v in data.get("srts", {}).items()
        },
        "groups": {
            int(k): [_group_from_dict(g) for g in v]
            for k, v in data.get("groups", {}).items()
        },
        "srt_filenames": _int_keyed(data.get("srt_filenames", {})),
    }


def save_state(state: Dict, path: Path = DEFAULT_STATE_PATH) -> None:
    """保存 STATE 到磁盘（原子写：先写临时文件再替换）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(dump_state(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_state(path: Path = DEFAULT_STATE_PATH) -> Optional[Dict]:
    """从磁盘加载 STATE；不存在或损坏时返回 None。"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return restore_state(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def clear_state(path: Path = DEFAULT_STATE_PATH) -> None:
    """删除持久化文件（清空任务进度）。"""
    if path.exists():
        path.unlink()
