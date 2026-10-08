"""流水线编排：剧本 → 台词库 → 对齐 → 纠错 → 拆分 → 导出。

把各阶段模块串起来，供 Web API 调用。均为确定性函数，零幻觉。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.align.aligner import align
from app.correct.corrector import AlignedGroup, group_corrections
from app.extraction.dialogue_extractor import Episode, extract_dialogues
from app.extraction.script_reader import read_script_lines
from app.split.splitter import split_group
from app.srt_parser import SrtSegment, is_sound_marker, read_srt_file, write_srt


def extract_script(path) -> List[Episode]:
    """读取剧本文件并提取「集 → 场景 → 台词对」结构。"""
    lines = read_script_lines(path)
    return extract_dialogues(lines)


def episode_en_lines(episode: Episode) -> List[str]:
    """取一集内所有非空英文台词（作为对齐的标准答案）。"""
    lines: List[str] = []
    for scene in episode.scenes:
        for d in scene.dialogues:
            if d.text_en.strip():
                lines.append(d.text_en.strip())
    return lines


def episode_zh_lines(episode: Episode) -> List[str]:
    """取一集内所有非空中文台词（作为对齐的标准答案）。"""
    lines: List[str] = []
    for scene in episode.scenes:
        for d in scene.dialogues:
            if d.text_zh.strip():
                lines.append(d.text_zh.strip())
    return lines


def episode_lines(episode: Episode) -> Tuple[str, List[str]]:
    """返回该集 (语言, 标准答案台词列表)。

    有英文台词按英文处理，否则按中文处理（识别不到英文即按中文）。
    """
    en_lines = episode_en_lines(episode)
    if en_lines:
        return "en", en_lines
    return "zh", episode_zh_lines(episode)


def process_episode(
    episode: Episode,
    srt_segments: List[SrtSegment],
    threshold: float = 0.55,
) -> List[AlignedGroup]:
    """对一集执行「对齐 → 纠错（分组）」，返回纠错组列表（中英文自动识别）。"""
    lang, lines = episode_lines(episode)
    alignment = align(lines, srt_segments, threshold=threshold, lang=lang)
    return group_corrections(srt_segments, alignment, lines, lang=lang)


def build_report(episode: Episode, groups: List[AlignedGroup]) -> dict:
    """生成一集的完整度报告。

    - missing：剧本中有台词但无任何片段命中（缺失台词）。
    - extra：SRT 中未命中且非音效标记的片段（多余/需复核片段）。
    - sound_markers：音效标记片段数（导出时删除）。
    """
    _, lines = episode_lines(episode)
    matched_indices = {g.dialogue_index for g in groups if g.matched}

    missing = [lines[i] for i in range(len(lines)) if i not in matched_indices]
    extra = [
        g.original_text
        for g in groups
        if not g.matched and not is_sound_marker(g.correct_text)
    ]
    sound_markers = sum(1 for g in groups if is_sound_marker(g.correct_text))

    return {
        "total_dialogues": len(lines),
        "matched_dialogues": len(matched_indices),
        "missing_dialogues": missing,
        "missing_count": len(missing),
        "extra_segments": extra,
        "extra_count": len(extra),
        "sound_markers": sound_markers,
    }


def groups_to_segments(
    groups: List[AlignedGroup],
    max_chars: Optional[int] = None,
    max_lines: int = 2,
    remove_sound_markers: bool = True,
) -> List[SrtSegment]:
    """把纠错组拆分为最终 SRT 片段（可选择性剔除音效标记）。

    max_chars 缺省时按每组语言自动决定（中文 12、英文 23）。
    """
    segments: List[SrtSegment] = []
    for g in groups:
        for seg in split_group(g, max_chars=max_chars, max_lines=max_lines):
            if remove_sound_markers and is_sound_marker(seg.text):
                continue
            segments.append(seg)
    return segments


def export_srt(
    groups: List[AlignedGroup],
    max_chars: Optional[int] = None,
    max_lines: int = 2,
    remove_sound_markers: bool = True,
) -> str:
    """导出最终 SRT 文本（先拆分，再选择性剔除音效标记）。"""
    segments = groups_to_segments(
        groups,
        max_chars=max_chars,
        max_lines=max_lines,
        remove_sound_markers=remove_sound_markers,
    )
    return write_srt(segments)
