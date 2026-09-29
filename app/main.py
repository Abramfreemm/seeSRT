"""seeSRT FastAPI 入口：REST API + 静态前端（端口 8877）。

采用 JSON 文件持久化（`data/state.json`），重启后恢复进度（中途退出续做）。
所有处理均为确定性算法，零幻觉。
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.correct.corrector import AlignedGroup
from app.correct.diff import diff_words
from app.pipeline import build_report, episode_en_lines, export_srt, extract_script, process_episode
from app.split.splitter import split_group
from app.srt_parser import is_sound_marker, read_srt_file
from app.storage import clear_state, load_state, save_state

# 本地桌面应用：前端与后端同源（127.0.0.1:8877），无需 CORS。
# 刻意不启用 CORSMiddleware，避免任意网页跨域读取本地剧本数据（安全最佳实践）。
app = FastAPI(title="seeSRT")

# 内存态：启动时从磁盘恢复，运行中随关键操作持久化
STATE: Dict = load_state() or {
    "episodes": [],       # List[Episode]
    "srts": {},           # episode_no -> List[SrtSegment]
    "groups": {},         # episode_no -> List[AlignedGroup]（correct_text 含用户编辑）
    "srt_filenames": {},  # episode_no -> 原始文件名
}


def _persist() -> None:
    save_state(STATE)


def _episode_by_no() -> Dict[int, object]:
    return {e.episode_no: e for e in STATE["episodes"]}


def _episode_no_from_filename(filename: str) -> int:
    m = re.search(r"(\d+)", filename)
    if not m:
        raise HTTPException(400, "无法从文件名解析集数（应为 1.srt / 01.srt 等）")
    return int(m.group(1))


def _group_to_dict(g: AlignedGroup, idx: int) -> dict:
    return {
        "id": idx,
        "matched": g.matched,
        "dialogue_index": g.dialogue_index,
        "start": g.start,
        "end": g.end,
        "original": g.original_text,
        "corrected": g.correct_text,
        "reviewed": g.reviewed,
        "diff": diff_words(g.original_text, g.correct_text),
        "is_sound_marker": is_sound_marker(g.correct_text),
        "split": [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in split_group(g)
        ],
    }


def _episode_to_dict(ep) -> dict:
    return {
        "episode_no": ep.episode_no,
        "scenes": [
            {
                "scene_no": sc.scene_no,
                "dialogues": [
                    {"text_zh": d.text_zh, "text_en": d.text_en} for d in sc.dialogues
                ],
            }
            for sc in ep.scenes
        ],
    }


def _run_episode(ep_no: int, threshold: float = 0.55) -> dict:
    """对单集执行「对齐 → 纠错」，写回 STATE 并返回处理摘要。"""
    episode = _episode_by_no().get(ep_no)
    segments = STATE["srts"].get(ep_no)
    if episode is None:
        raise HTTPException(400, f"未找到第 {ep_no} 集的剧本台词，请先上传剧本")
    if segments is None:
        raise HTTPException(400, f"未找到第 {ep_no} 集的 SRT，请先上传")

    groups = process_episode(episode, segments, threshold=threshold)
    STATE["groups"][ep_no] = groups

    matched = sum(1 for g in groups if g.matched)
    return {
        "episode_no": ep_no,
        "total": len(groups),
        "matched": matched,
        "unmatched": len(groups) - matched,
        "groups": [_group_to_dict(g, i) for i, g in enumerate(groups)],
        "report": build_report(episode, groups),
    }


@app.post("/api/script")
async def upload_script(file: UploadFile = File(...)):
    """上传剧本（.docx/.txt/.fountain），提取台词库。"""
    suffix = Path(file.filename or "script.docx").suffix.lower()
    if suffix not in (".docx", ".txt", ".fountain"):
        raise HTTPException(400, "仅支持 .docx / .txt / .fountain")
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        episodes = extract_script(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    STATE["episodes"] = episodes
    # 上传新剧本视为全新项目：清空旧 SRT 与处理结果，台词库自动拆分新剧本
    STATE["srts"] = {}
    STATE["groups"] = {}
    STATE["srt_filenames"] = {}
    _persist()
    return {
        "count": len(episodes),
        "total_en_lines": sum(len(episode_en_lines(e)) for e in episodes),
        "episodes": [_episode_to_dict(e) for e in episodes],
    }


@app.post("/api/srt")
async def upload_srt(file: UploadFile = File(...)):
    """上传一集 SRT（文件名即集数），解析并暂存片段。"""
    ep_no = _episode_no_from_filename(file.filename or "")
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        segments = read_srt_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    STATE["srts"][ep_no] = segments
    STATE["srt_filenames"][ep_no] = file.filename or f"{ep_no}.srt"
    STATE["groups"].pop(ep_no, None)  # 重新上传后使旧处理结果失效
    _persist()
    return {"episode_no": ep_no, "segments": len(segments)}


class ProcessPayload(BaseModel):
    episode_no: int
    threshold: float = 0.55


@app.post("/api/process")
def process(payload: ProcessPayload):
    """对指定集执行「对齐 → 纠错 → 拆分」，返回带差异的纠错组与完整度报告。"""
    result = _run_episode(payload.episode_no, threshold=payload.threshold)
    _persist()
    return result


class BatchPayload(BaseModel):
    threshold: float = 0.55


@app.post("/api/process_batch")
def process_batch(payload: BatchPayload):
    """批量处理所有已上传 SRT 的集，返回每集摘要。"""
    results = []
    for ep_no in sorted(STATE["srts"].keys()):
        episode = _episode_by_no().get(ep_no)
        if episode is None:
            continue
        groups = process_episode(episode, STATE["srts"][ep_no], threshold=payload.threshold)
        STATE["groups"][ep_no] = groups
        matched = sum(1 for g in groups if g.matched)
        results.append(
            {
                "episode_no": ep_no,
                "total": len(groups),
                "matched": matched,
                "unmatched": len(groups) - matched,
                "report": build_report(episode, groups),
            }
        )
    _persist()
    return {"results": results}


class EditPayload(BaseModel):
    episode_no: int
    group_id: int
    text: str


@app.post("/api/edit")
def edit(payload: EditPayload):
    """保存用户对某组纠错文本的修改，并返回更新后的该组数据。"""
    groups = STATE["groups"].get(payload.episode_no)
    if groups is None or not (0 <= payload.group_id < len(groups)):
        raise HTTPException(400, "该集尚未处理或组号无效")
    groups[payload.group_id].correct_text = payload.text
    _persist()
    return _group_to_dict(groups[payload.group_id], payload.group_id)


class ReviewPayload(BaseModel):
    episode_no: int
    group_id: int
    reviewed: bool = True


@app.post("/api/review")
def review(payload: ReviewPayload):
    """标记某组（未命中片段）为已复核 / 取消复核。"""
    groups = STATE["groups"].get(payload.episode_no)
    if groups is None or not (0 <= payload.group_id < len(groups)):
        raise HTTPException(400, "该集尚未处理或组号无效")
    groups[payload.group_id].reviewed = payload.reviewed
    _persist()
    return _group_to_dict(groups[payload.group_id], payload.group_id)


class ReviewBatchPayload(BaseModel):
    episode_no: int


@app.post("/api/review_batch")
def review_batch(payload: ReviewBatchPayload):
    """一键复核：把某集所有未命中（非音效）片段标记为已复核。"""
    groups = STATE["groups"].get(payload.episode_no)
    if groups is None:
        raise HTTPException(400, "该集尚未处理，请先执行对齐/纠错")
    count = 0
    for g in groups:
        if not g.matched and not is_sound_marker(g.correct_text) and not g.reviewed:
            g.reviewed = True
            count += 1
    _persist()
    return {"episode_no": payload.episode_no, "reviewed": count}


class ExportPayload(BaseModel):
    episode_no: int


@app.post("/api/export")
def export(payload: ExportPayload):
    """导出修正后 SRT（导出时删除音效标记）。"""
    groups = STATE["groups"].get(payload.episode_no)
    if groups is None:
        raise HTTPException(400, "尚未处理该集，请先执行对齐/纠错")
    srt_text = export_srt(groups, remove_sound_markers=True)
    return {
        "episode_no": payload.episode_no,
        "filename": STATE["srt_filenames"].get(payload.episode_no, f"{payload.episode_no}.srt"),
        "srt": srt_text,
    }


@app.post("/api/export_batch")
def export_batch():
    """批量导出所有已处理集的修正后 SRT，打包为 zip（导出时删除音效标记）。"""
    groups_map = STATE["groups"]
    if not groups_map:
        raise HTTPException(400, "尚未处理任何集，请先执行批量处理或对齐/纠错")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ep_no in sorted(groups_map.keys()):
            srt_text = export_srt(groups_map[ep_no], remove_sound_markers=True)
            filename = STATE["srt_filenames"].get(ep_no, f"{ep_no}.srt")
            zf.writestr(filename, srt_text)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="seeSRT_export.zip"'},
    )


@app.get("/api/dialogues")
def dialogues():
    """返回台词库（供未命中片段复制粘贴）。"""
    return {"episodes": [_episode_to_dict(e) for e in STATE["episodes"]]}


@app.get("/api/state")
def state():
    """返回当前完整状态（启动恢复 / 续做用）。"""
    by_no = _episode_by_no()
    return {
        "episodes": [_episode_to_dict(e) for e in STATE["episodes"]],
        "srts": {str(ep): fn for ep, fn in STATE["srt_filenames"].items()},
        "groups": {
            str(ep): [_group_to_dict(g, i) for i, g in enumerate(groups)]
            for ep, groups in STATE["groups"].items()
        },
        "reports": {
            str(ep): build_report(by_no[ep], groups)
            for ep, groups in STATE["groups"].items()
            if ep in by_no
        },
    }


@app.post("/api/reset")
def reset():
    """清空所有进度（剧本/SRT/处理结果）。"""
    STATE["episodes"] = []
    STATE["srts"] = {}
    STATE["groups"] = {}
    STATE["srt_filenames"] = {}
    clear_state()
    return {"ok": True}


# 静态前端（放在最后，避免覆盖 /api 路由）
def _static_dir() -> Path:
    """静态资源目录：开发时在 app/static，打包后在 <解压目录>/app/static。

    spec 里 datas 将 app/static 收集到 <解压目录>/app/static，因此直接以本文件
    （app/main.py）所在目录为基准取 static 即可，开发/打包两种场景都正确。
    """
    return Path(__file__).resolve().parent / "static"


_STATIC_DIR = _static_dir()
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
