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


class TestWrapLinesZh:
    def test_zh_short(self):
        assert wrap_lines("你好世界", max_chars=12, lang="zh") == ["你好世界"]

    def test_zh_strips_whitespace(self):
        assert wrap_lines("你好 世界", max_chars=12, lang="zh") == ["你好世界"]

    def test_zh_long_wraps_within_max(self):
        text = "这是一段非常长的中文台词，需要换行处理并且保持每行不超过十二个字"
        lines = wrap_lines(text, max_chars=12, lang="zh")
        for ln in lines:
            assert len(ln) <= 12


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


def _multi_group():
    """一条剧本台词命中两个相邻原始片段。"""
    seg1 = SrtSegment(index=1, start="00:00:01,000", end="00:00:02,000", text="Hello world")
    seg2 = SrtSegment(index=2, start="00:00:02,000", end="00:00:03,000", text="how are you")
    return AlignedGroup(
        dialogue_index=0,
        segments=[seg1, seg2],
        correct_text="Hello world how are you",
    )


class TestSplitGroupPreservesBoundaries:
    def test_multi_segment_keeps_original_timecodes(self):
        segs = split_group(_multi_group())
        assert len(segs) == 2
        # 每个原始片段的 start/end 原样保留
        assert (segs[0].start, segs[0].end) == ("00:00:01,000", "00:00:02,000")
        assert (segs[1].start, segs[1].end) == ("00:00:02,000", "00:00:03,000")

    def test_multi_segment_distributes_correct_text(self):
        segs = split_group(_multi_group())
        assert segs[0].text == "Hello world"
        assert segs[1].text == "how are you"

    def test_multi_segment_each_two_lines_max(self):
        segs = split_group(_multi_group())
        for s in segs:
            assert s.text.count("\n") <= 1
            for line in s.text.split("\n"):
                assert len(line) <= 23

    def test_correct_text_typo_fix_stays_in_segment(self):
        # 原片段有拼写错误，正确文本应替换回同一片段，时间码不变
        seg1 = SrtSegment(index=1, start="00:00:01,000", end="00:00:02,000", text="Wll hello")
        seg2 = SrtSegment(index=2, start="00:00:02,000", end="00:00:03,000", text="there")
        g = AlignedGroup(dialogue_index=0, segments=[seg1, seg2], correct_text="Will hello there")
        segs = split_group(g)
        assert len(segs) == 2
        assert segs[0].start == "00:00:01,000"
        assert segs[0].end == "00:00:02,000"
        assert segs[0].text == "Will hello"
        assert segs[1].text == "there"


class TestDashSplit:
    def test_double_hyphen_splits_segments(self):
        text = "I didn't mean to-- I mean, I did"
        segs = split_group(_group(text, end="00:00:04,000"))
        assert len(segs) == 2
        # 破折号保留在前一句末尾
        assert segs[0].text == "I didn't mean to--"
        assert segs[1].text == "I mean, I did"

    def test_em_dash_splits_segments(self):
        text = "I didn't mean to— I mean, I did"
        segs = split_group(_group(text, end="00:00:04,000"))
        assert len(segs) == 2
        assert segs[0].text == "I didn't mean to—"
        assert segs[1].text == "I mean, I did"

    def test_dash_preserves_overall_time_range(self):
        text = "I didn't mean to-- I mean, I did"
        segs = split_group(_group(text, start="00:00:01,000", end="00:00:04,000"))
        assert segs[0].start == "00:00:01,000"
        assert segs[-1].end == "00:00:04,000"
        # 中间切分点落在整体区间内，且不早于起点
        assert segs[1].start >= "00:00:01,000"

    def test_dash_segments_still_two_lines_max(self):
        text = (
            "This is a very long sentence with a dash-- "
            "and then a second very long clause that continues here"
        )
        segs = split_group(_group(text))
        for s in segs:
            assert s.text.count("\n") <= 1
            for line in s.text.split("\n"):
                assert len(line) <= 23

    def test_no_dash_unchanged(self):
        # 无破折号时行为不变：单个片段原样保留
        segs = split_group(_group("Hello world", start="00:00:01,000", end="00:00:04,000"))
        assert len(segs) == 1
        assert segs[0].text == "Hello world"
        assert segs[0].start == "00:00:01,000"
        assert segs[0].end == "00:00:04,000"


class TestSplitGroupZh:
    def test_zh_auto_max_chars_per_line(self):
        seg = SrtSegment(index=1, start="00:00:00,000", end="00:00:04,000", text="x")
        g = AlignedGroup(
            dialogue_index=0,
            segments=[seg],
            correct_text="这是一段超过十二个字符的中文台词内容需要被拆分处理",
            lang="zh",
        )
        segs = split_group(g)
        assert segs
        for s in segs:
            assert s.text.count("\n") <= 1
            for line in s.text.split("\n"):
                assert len(line) <= 12

    def test_zh_typo_fix_stays_in_segment(self):
        # 中文错别字：正确文本替换回同一片段，时间码不变
        seg1 = SrtSegment(index=1, start="00:00:01,000", end="00:00:02,000", text="你好世办")
        seg2 = SrtSegment(index=2, start="00:00:02,000", end="00:00:03,000", text="谢谢")
        g = AlignedGroup(dialogue_index=0, segments=[seg1, seg2], correct_text="你好世界谢谢", lang="zh")
        segs = split_group(g)
        assert len(segs) == 2
        assert (segs[0].start, segs[0].end) == ("00:00:01,000", "00:00:02,000")
        assert segs[0].text == "你好世界"
        assert segs[1].text == "谢谢"
