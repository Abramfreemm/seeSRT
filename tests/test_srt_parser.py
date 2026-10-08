"""SRT 解析器测试：覆盖解析、编码检测、无损写出闭环。"""

from app.srt_parser import (
    SrtSegment,
    _detect_encoding,
    format_timestamp,
    parse_srt,
    parse_timestamp,
    read_srt_file,
    write_srt,
    write_srt_file,
)


class TestTimestamp:
    def test_parse_comma(self):
        assert parse_timestamp("00:00:01,500") == 1500

    def test_parse_dot(self):
        assert parse_timestamp("00:01:02.500") == 62500

    def test_parse_short_ms(self):
        assert parse_timestamp("00:00:01,5") == 1500

    def test_format(self):
        assert format_timestamp(1500) == "00:00:01,500"
        assert format_timestamp(0) == "00:00:00,000"

    def test_roundtrip(self):
        for ts in ["00:00:01,000", "01:02:03,999", "12:34:56,789"]:
            assert format_timestamp(parse_timestamp(ts)) == ts


class TestParseSrt:
    def test_basic(self):
        content = (
            "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nThis is a test\n"
        )
        segs = parse_srt(content)
        assert len(segs) == 2
        assert segs[0].text == "Hello world"
        assert segs[1].start == "00:00:04,000"

    def test_multiline_text(self):
        content = "1\n00:00:01,000 --> 00:00:04,000\nLine one\nLine two\n"
        segs = parse_srt(content)
        assert len(segs) == 1
        assert segs[0].text == "Line one\nLine two"

    def test_missing_index(self):
        content = "00:00:01,000 --> 00:00:04,000\nHello\n"
        segs = parse_srt(content)
        assert len(segs) == 1
        assert segs[0].index == 1

    def test_bom(self):
        content = "\ufeff1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        segs = parse_srt(content)
        assert segs[0].text == "Hello"

    def test_crlf(self):
        content = "1\r\n00:00:01,000 --> 00:00:04,000\r\nHello\r\n"
        segs = parse_srt(content)
        assert segs[0].text == "Hello"

    def test_ignore_non_subtitle_blocks(self):
        content = "Some title\n\n1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        segs = parse_srt(content)
        assert len(segs) == 1

    def test_empty_content(self):
        assert parse_srt("") == []

    def test_strip_html_tags(self):
        content = "1\n00:00:01,000 --> 00:00:04,000\n<b>Hello</b> <i>world</i>\n"
        segs = parse_srt(content)
        assert segs[0].text == "Hello world"

    def test_strip_html_tags_keeps_plain_less_than(self):
        # 只删除形如 <b> 的 HTML 标签，保留普通小于号
        content = "1\n00:00:01,000 --> 00:00:04,000\n2 < 3\n"
        segs = parse_srt(content)
        assert segs[0].text == "2 < 3"


class TestWriteSrt:
    def test_roundtrip(self):
        content = (
            "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\n第二行\nLine two\n"
        )
        segs = parse_srt(content)
        written = write_srt(segs)
        segs2 = parse_srt(written)
        assert [(s.start, s.end, s.text) for s in segs] == [
            (s.start, s.end, s.text) for s in segs2
        ]

    def test_renumber(self):
        segs = [
            SrtSegment(index=5, start="00:00:01,000", end="00:00:02,000", text="a"),
            SrtSegment(index=9, start="00:00:02,000", end="00:00:03,000", text="b"),
        ]
        written = write_srt(segs)
        assert written.startswith("1\n")


class TestEncoding:
    def test_detect_utf8(self):
        assert _detect_encoding("你好".encode("utf-8")) == "utf-8"

    def test_detect_gb18030(self):
        assert _detect_encoding("你好世界".encode("gbk")) == "gb18030"

    def test_detect_bom(self):
        data = b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:04,000\nhi\n"
        assert _detect_encoding(data) == "utf-8-sig"


class TestFileIO:
    def test_read_write_roundtrip(self, tmp_path):
        src = tmp_path / "1.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nHello\n", encoding="utf-8"
        )
        segs = read_srt_file(src)
        assert segs[0].text == "Hello"

        dst = tmp_path / "out.srt"
        write_srt_file(dst, segs)
        assert dst.read_text(encoding="utf-8") == (
            "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        )
