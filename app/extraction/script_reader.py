"""剧本文件读取：docx / txt / fountain → 文本行列表。"""

from pathlib import Path
from typing import List

from app.srt_parser import _detect_encoding


def read_script_lines(path) -> List[str]:
    """读取剧本文件，返回去除空行的文本行列表（保留每行原始文本）。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".docx":
        lines = _read_docx(p)
    else:
        lines = _read_text(p)
    return [ln.rstrip("\n").rstrip("\r") for ln in lines if ln.strip()]


def _read_docx(path: Path) -> List[str]:
    from docx import Document

    doc = Document(str(path))
    return [p.text for p in doc.paragraphs]


def _read_text(path: Path) -> List[str]:
    data = path.read_bytes()
    enc = _detect_encoding(data)
    text = data.decode(enc, errors="replace")
    return text.splitlines()
