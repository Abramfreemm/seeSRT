"""词级 diff 测试。"""

from app.correct.diff import diff_words


def _old_ops(ops):
    return [(o["op"], o["old"]) for o in ops]


def _new_ops(ops):
    return [(o["op"], o["new"]) for o in ops]


def test_equal():
    assert diff_words("Hello world", "Hello world") == [
        {"op": "equal", "old": "Hello", "new": "Hello"},
        {"op": "equal", "old": "world", "new": "world"},
    ]


def test_replace_word():
    # 拼写修正
    ops = diff_words("evening", "even")
    assert ops == [{"op": "replace", "old": "evening", "new": "even"}]


def test_case_change():
    ops = diff_words("hello world", "Hello world")
    assert ops[0] == {"op": "replace", "old": "hello", "new": "Hello"}
    assert ops[1]["op"] == "equal"


def test_insert_word():
    # 漏词补全
    ops = diff_words("I love you", "I really love you")
    assert ops[1] == {"op": "insert", "old": "", "new": "really"}


def test_delete_word():
    ops = diff_words("I really love you", "I love you")
    assert ops[1] == {"op": "delete", "old": "really", "new": ""}


def test_zh_char_replace():
    # 中文错别字逐字标红
    ops = diff_words("你好世界", "你好世办", lang="zh")
    assert ops == [
        {"op": "equal", "old": "你", "new": "你"},
        {"op": "equal", "old": "好", "new": "好"},
        {"op": "equal", "old": "世", "new": "世"},
        {"op": "replace", "old": "界", "new": "办"},
    ]


def test_zh_equal():
    assert diff_words("你好世界", "你好世界", lang="zh") == [
        {"op": "equal", "old": "你", "new": "你"},
        {"op": "equal", "old": "好", "new": "好"},
        {"op": "equal", "old": "世", "new": "世"},
        {"op": "equal", "old": "界", "new": "界"},
    ]
