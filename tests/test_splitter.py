"""拆分器测试。"""

from app.correct.corrector import AlignedGroup
from app.srt_parser import SrtSegment
from app.split.splitter import split_group, wrap_lines


def _group(text, start="00:00:00,000", end="00:00:04,000"):
    seg = SrtSegment(index=1, start=start, end=end, text="x")
    return AlignedGroup(dialogue_index=0, segments=[seg], correct_text=text)


class TestWrapLines:
    def test_short(self):
        assert wrap_lines("Hello world") == ["Hello world"]

    def test_long_sentence_wraps_at_comma(self):
        lines = wrap_lines("Hello, my friend, how are you today?")
        for ln in lines:
            assert len(ln) <= 23

    def test_no_line_exceeds_max(self):
        text = (
            "This is a very long piece of dialogue that will definitely "
            "span more than two lines and need multiple segments to display properly"
        )
        for ln in wrap_lines(text):
            assert len(ln) <= 23

    def test_newlines_normalized_to_space(self):
        # 未命中片段的原文可能含达芬奇自带的换行符，应规范化为空格而非内嵌换行
        lines = wrap_lines("HELLO WORLD\nTHIS IS A VERY LONG TEST LINE HERE")
        for ln in lines:
            assert "\n" not in ln
            assert len(ln) <= 23


class TestSplitGroup:
    def test_short_single_line(self):
        segs = split_group(_group("Hello world"))
        assert len(segs) == 1
        assert segs[0].text == "Hello world"

    def test_two_lines_one_segment(self):
        text = "This is a longer sentence that wraps"
        segs = split_group(_group(text))
        assert len(segs) == 1
        assert segs[0].text.count("\n") == 1  # 2 行

    def test_multiple_segments(self):
        text = (
            "This is a very long piece of dialogue that will definitely "
            "span more than two lines and need multiple segments to display properly"
        )
        segs = split_group(_group(text))
        assert len(segs) > 1
        for s in segs:
            assert s.text.count("\n") <= 1  # 每片段最多 2 行
            for line in s.text.split("\n"):
                assert len(line) <= 23  # 每行 ≤ 23 字符

    def test_time_range_preserved(self):
        segs = split_group(_group("Hello world", start="00:00:01,000", end="00:00:04,000"))
        assert segs[0].start == "00:00:01,000"
        assert segs[0].end == "00:00:04,000"

    def test_time_distributed_by_chars(self):
        text = "This is a longer sentence that wraps"
        segs = split_group(_group(text, end="00:00:04,000"))
        assert len(segs) == 1
        assert segs[0].end == "00:00:04,000"
