"""纠错器测试。"""

from app.correct.corrector import AlignedGroup, group_corrections
from app.srt_parser import SrtSegment


def _seg(text, i=0):
    return SrtSegment(index=i, start="00:00:00,000", end="00:00:01,000", text=text)


class TestGroupCorrections:
    def test_matched_group(self):
        script = ["Hello world"]
        groups = group_corrections([_seg("hello world")], [0], script)
        assert len(groups) == 1
        assert groups[0].matched
        assert groups[0].correct_text == "Hello world"

    def test_unmatched_group(self):
        script = ["Hello world"]
        groups = group_corrections([_seg("unknown")], [None], script)
        assert len(groups) == 1
        assert not groups[0].matched
        assert groups[0].correct_text == "unknown"

    def test_unmatched_all_caps_becomes_sentence_case(self):
        script = ["Hello world"]
        groups = group_corrections([_seg("SOME UNKNOWN\nSECOND LINE HERE")], [None], script)
        assert groups[0].correct_text == "Some unknown second line here"

    def test_unmatched_mixed_case_unchanged(self):
        script = ["Hello world"]
        groups = group_corrections([_seg("already Mixed case")], [None], script)
        assert groups[0].correct_text == "already Mixed case"

    def test_split_merged_into_one_group(self):
        # 一句台词被达芬奇拆成两个片段，应合并为一组
        script = ["Callan, help me! My uncle betrayed me."]
        segs = [_seg("Callan, help me!"), _seg("My uncle betrayed me.")]
        groups = group_corrections(segs, [0, 0], script)
        assert len(groups) == 1
        assert groups[0].correct_text == "Callan, help me! My uncle betrayed me."

    def test_group_time_range(self):
        script = ["Hello world"]
        seg1 = SrtSegment(index=1, start="00:00:01,000", end="00:00:02,000", text="a")
        seg2 = SrtSegment(index=2, start="00:00:02,000", end="00:00:03,000", text="b")
        groups = group_corrections([seg1, seg2], [0, 0], script)
        assert groups[0].start == "00:00:01,000"
        assert groups[0].end == "00:00:03,000"

    def test_mixed(self):
        script = ["Hello world", "Goodbye"]
        segs = [_seg("hello world"), _seg("??? bad"), _seg("goodbye")]
        groups = group_corrections(segs, [0, None, 1], script)
        assert [g.matched for g in groups] == [True, False, True]
        assert groups[0].correct_text == "Hello world"
        assert groups[1].correct_text == "??? bad"
        assert groups[2].correct_text == "Goodbye"
