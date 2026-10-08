"""对齐器测试。"""

from app.align.aligner import _normalize, align
from app.srt_parser import SrtSegment


def _seg(text, i=0):
    return SrtSegment(index=i, start="00:00:00,000", end="00:00:01,000", text=text)


class TestNormalize:
    def test_normalize(self):
        assert _normalize("Hello, World!") == "helloworld"
        assert _normalize("They're here.") == "theyrehere"
        assert _normalize("I’m up north") == "imupnorth"


class TestAlign:
    def test_one_to_one(self):
        script = ["Hello world", "This is a test", "Goodbye"]
        segs = [_seg("Hello world"), _seg("This is a test"), _seg("Goodbye")]
        assert align(script, segs) == [0, 1, 2]

    def test_split_across_segments(self):
        script = ["Callan, help me! My uncle betrayed me.", "Next line"]
        segs = [
            _seg("Callan, help me!"),
            _seg("My uncle betrayed me."),
            _seg("Next line"),
        ]
        assert align(script, segs) == [0, 0, 1]

    def test_case_and_punct_insensitive(self):
        script = ["Hello world"]
        segs = [_seg("HELLO, world!")]
        assert align(script, segs) == [0]

    def test_unmatched(self):
        script = ["Hello world"]
        segs = [_seg("completely different content")]
        assert align(script, segs) == [None]

    def test_empty_segment(self):
        script = ["Hello world"]
        segs = [_seg("")]
        assert align(script, segs) == [None]

    def test_skipped_line(self):
        # 达芬奇漏识别了第一句 "Hello"
        script = ["Hello", "World"]
        segs = [_seg("World")]
        assert align(script, segs) == [1]

    def test_zh_one_to_one(self):
        script = ["你好世界", "这是一段测试"]
        segs = [_seg("你好世界"), _seg("这是一段测试")]
        assert align(script, segs, lang="zh") == [0, 1]

    def test_zh_typo_align(self):
        # 中文错别字仍能对齐（逐字 LCS）
        script = ["你好世界"]
        segs = [_seg("你好世办")]
        assert align(script, segs, lang="zh") == [0]
