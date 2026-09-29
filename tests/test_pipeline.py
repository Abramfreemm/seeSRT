"""流水线编排器测试。"""

from app.correct.corrector import AlignedGroup
from app.extraction.dialogue_extractor import Dialogue, Episode, Scene
from app.pipeline import build_report, export_srt, groups_to_segments
from app.srt_parser import SrtSegment, is_sound_marker, parse_srt


def _group(text, start="00:00:00,000", end="00:00:02,000", di=0):
    return AlignedGroup(
        dialogue_index=di,
        segments=[SrtSegment(index=1, start=start, end=end, text=text)],
        correct_text=text,
    )


def test_is_sound_marker():
    assert is_sound_marker("[MUSIC PLAYING]")
    assert is_sound_marker("[GASPING]")
    assert not is_sound_marker("Hello world")
    assert not is_sound_marker("[abc] def")


def test_export_removes_sound_markers():
    groups = [
        _group("Hello world"),
        _group("[MUSIC PLAYING]"),
        _group("Goodbye"),
    ]
    segments = groups_to_segments(groups, remove_sound_markers=True)
    texts = [s.text for s in segments]
    assert texts == ["Hello world", "Goodbye"]


def test_export_keeps_sound_markers_when_requested():
    groups = [_group("Hello"), _group("[MUSIC PLAYING]")]
    segments = groups_to_segments(groups, remove_sound_markers=False)
    assert [s.text for s in segments] == ["Hello", "[MUSIC PLAYING]"]


def test_export_srt_format():
    groups = [_group("Hello world")]
    out = export_srt(groups)
    assert out.startswith("1\n")
    assert "Hello world" in out
    # 可再次解析
    parsed = parse_srt(out)
    assert len(parsed) == 1
    assert parsed[0].text == "Hello world"


def _episode(en_lines):
    return Episode(
        episode_no=1,
        scenes=[Scene(scene_no="1-1", dialogues=[Dialogue(text_zh="", text_en=t) for t in en_lines])],
    )


def test_build_report_missing_and_extra():
    ep = _episode(["Hello world", "Goodbye", "Missing line"])
    # 命中台词 0、1；台词 2 缺失；另有未命中片段 + 音效标记
    groups = [
        _group("Hello world", di=0),
        _group("Goodbye", di=1),
        _group("unmatched extra", di=None),
        _group("[MUSIC PLAYING]", di=None),
    ]
    report = build_report(ep, groups)
    assert report["total_dialogues"] == 3
    assert report["matched_dialogues"] == 2
    assert report["missing_dialogues"] == ["Missing line"]
    assert report["extra_segments"] == ["unmatched extra"]
    assert report["sound_markers"] == 1

