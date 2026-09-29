"""持久化模块测试。"""

import json

from app.correct.corrector import AlignedGroup
from app.extraction.dialogue_extractor import Dialogue, Episode, Scene
from app.srt_parser import SrtSegment
from app.storage import dump_state, restore_state, save_state, load_state


def _seg(text, i=0):
    return SrtSegment(index=i, start="00:00:00,000", end="00:00:01,000", text=text)


def _group(text, di=0):
    return AlignedGroup(
        dialogue_index=di,
        segments=[_seg(text)],
        correct_text=text,
    )


def _sample_state():
    ep = Episode(
        episode_no=1,
        scenes=[Scene(scene_no="1-1", dialogues=[Dialogue(text_zh="你好", text_en="Hello world")])],
    )
    return {
        "episodes": [ep],
        "srts": {1: [_seg("hello world")]},
        "groups": {1: [_group("Hello world")]},
        "srt_filenames": {1: "1.srt"},
    }


class TestStorage:
    def test_roundtrip(self):
        state = _sample_state()
        restored = restore_state(dump_state(state))
        assert restored["srt_filenames"] == {1: "1.srt"}
        assert restored["episodes"][0].episode_no == 1
        assert restored["episodes"][0].scenes[0].dialogues[0].text_en == "Hello world"
        assert restored["srts"][1][0].text == "hello world"
        assert restored["groups"][1][0].correct_text == "Hello world"
        assert restored["groups"][1][0].segments[0].start == "00:00:00,000"

    def test_save_load_file(self, tmp_path):
        state = _sample_state()
        p = tmp_path / "state.json"
        save_state(state, path=p)
        loaded = load_state(path=p)
        assert loaded is not None
        assert loaded["srt_filenames"] == {1: "1.srt"}
        assert loaded["groups"][1][0].correct_text == "Hello world"

    def test_load_missing_returns_none(self, tmp_path):
        assert load_state(path=tmp_path / "nope.json") is None

    def test_load_corrupt_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert load_state(path=p) is None

    def test_dump_is_json_serializable(self):
        assert json.dumps(dump_state(_sample_state()))  # 不抛异常即可
