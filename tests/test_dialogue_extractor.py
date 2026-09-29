"""台词提取测试：集/场景识别、中英配对、过滤、中文数字转换。"""

from app.extraction.dialogue_extractor import cn_num_to_int, extract_dialogues


def _text() -> str:
    # 真实剧本格式：场景号、场景位置、人物表、舞台提示、台词分行
    return "\n".join(
        [
            "作品名称：xxx",
            "大纲：故事梗概",
            "",
            "剧本",
            "第一集",
            "1-1",
            "场景：夜，外，禁忌森林。",
            "1-1 NIGHT - EXT. FORBIDDEN FOREST",
            "主要人物：Alyria、Callan",
            "Characters: ALYRIA, CALLAN",
            "△漆黑的夜晚，下着雨。",
            "△ A dark, rainy night.",
            "【闪回】",
            "Alyria：救我！",
            "Alyria: Help me!",
            "1-2",
            "场景：夜，内，外。",
            "1-2 NIGHT - INT./EXT.",
            "人物：Callan",
            "Characters: CALLAN",
            "Callan OS：我正在北境",
            "Callan (O.S.): I'm up north.",
            "第二集",
            "2-1",
            "场景：夜，外，森林。",
            "2-1 NIGHT - EXT. FOREST",
            "Rainer：别怕",
            "Rainer: Don't be afraid.",
        ]
    )


class TestCnNum:
    def test_basic(self):
        assert cn_num_to_int("一") == 1
        assert cn_num_to_int("十") == 10
        assert cn_num_to_int("十五") == 15
        assert cn_num_to_int("二十") == 20
        assert cn_num_to_int("五十") == 50


class TestExtract:
    def test_structure(self):
        eps = extract_dialogues(_text().splitlines())
        assert len(eps) == 2
        assert eps[0].episode_no == 1
        assert eps[1].episode_no == 2

    def test_scenes(self):
        eps = extract_dialogues(_text().splitlines())
        ep1 = eps[0]
        assert [s.scene_no for s in ep1.scenes] == ["1-1", "1-2"]
        assert [s.scene_no for s in eps[1].scenes] == ["2-1"]

    def test_dialogues(self):
        eps = extract_dialogues(_text().splitlines())
        ep1 = eps[0]
        assert (ep1.scenes[0].dialogues[0].text_zh, ep1.scenes[0].dialogues[0].text_en) == (
            "救我！",
            "Help me!",
        )
        assert (
            ep1.scenes[1].dialogues[0].text_zh,
            ep1.scenes[1].dialogues[0].text_en,
        ) == ("我正在北境", "I'm up north.")
        assert eps[1].scenes[0].dialogues[0].text_en == "Don't be afraid."

    def test_filters_meta_and_stage(self):
        eps = extract_dialogues(_text().splitlines())
        ep1 = eps[0]
        # 元信息、人物行、舞台提示、标记均不应进入台词
        all_zh = [d.text_zh for s in ep1.scenes for d in s.dialogues]
        assert "故事梗概" not in all_zh
        assert "漆黑的夜晚" not in all_zh
        assert "闪回" not in all_zh

    def test_no_episode_no_dialogue(self):
        eps = extract_dialogues(["作品名称：xxx", "Alyria：救我！", "Alyria: Help me!"])
        assert eps == []


def _b_format() -> str:
    """格式 B：中文台词用半角冒号，英文台词紧随其后且无冒号。"""
    return "\n".join(
        [
            "第七集",
            "7-1 街道 夜 外",
            "人物:露西、伊森",
            "▲突然一阵雷声。",
            "伊森:现在！立刻！马上放开她！",
            "Now! Right now! Let her go!",
            "▲伊森的眼神锋利。",
            "黑手党领头:我不信你有种真开枪！",
            "I don't believe you've got the balls to shoot!",
            "第八集",
            "8-1 伊森车内 夜 内",
            "人物:露西、伊森",
            "伊森：你还好吗？Are you okay?",
            "露西:谢谢您救了我。Thank you for saving me.",
        ]
    )


def _c_format() -> str:
    """格式 C：集标题用阿拉伯数字 + EPISODE，英文台词含括号情绪。"""
    return "\n".join(
        [
            "五、剧本正文",
            "第1集",
            "EPISODE 1",
            "1-1 日 内 学校走廊",
            "1-1 DAY - INT. CROSSWOOD ACADEMY - HALLWAY",
            "人物：凯尔、艾文",
            "Characters: KYLE, EVAN",
            "△学生们三五成群聚在走廊两侧谈笑。",
            "△ Students gather in small groups.",
            "学生甲（压低声音）：天呐，是比利尔斯家族继承人。",
            "STUDENT A (lowering his voice): Oh my God, that's the Beliers heir.",
            "第2集",
            "EPISODE 2",
            "2-1 夜 内 客厅",
            "艾文：你是谁？",
            "EVAN: Who are you?",
        ]
    )


class TestAltFormats:
    def test_b_format_pairs_half_colon_and_standalone_en(self):
        eps = extract_dialogues(_b_format().splitlines())
        assert [e.episode_no for e in eps] == [7, 8]
        ep7 = eps[0]
        dlg = ep7.scenes[0].dialogues
        assert (dlg[0].text_zh, dlg[0].text_en) == ("现在！立刻！马上放开她！", "Now! Right now! Let her go!")
        assert (dlg[1].text_zh, dlg[1].text_en) == (
            "我不信你有种真开枪！",
            "I don't believe you've got the balls to shoot!",
        )

    def test_c_format_arabic_episode_and_paren_en(self):
        eps = extract_dialogues(_c_format().splitlines())
        assert [e.episode_no for e in eps] == [1, 2]
        ep1 = eps[0]
        dlg = ep1.scenes[0].dialogues
        assert dlg[0].text_en == "Oh my God, that's the Beliers heir."
        assert dlg[0].text_zh == "天呐，是比利尔斯家族继承人。"
        assert eps[1].scenes[0].dialogues[0].text_en == "Who are you?"

    def test_mixed_line_splits_zh_and_en(self):
        eps = extract_dialogues(
            [
                "第十二集",
                "12-1 走廊 日 内",
                "伊森（皱眉）：里面在干什么？What's going on in there?",
                "珍妮（慌乱）：没、没什么！洗、洗手间在检修！N-nothing! The restroom is under repair.",
                "伊森：让开。Move.",
                "露西：谢谢您救了我。Thank you for saving me.",
            ]
        )
        dlg = eps[0].scenes[0].dialogues
        assert dlg[0].text_zh == "里面在干什么？"
        assert dlg[0].text_en == "What's going on in there?"
        assert dlg[1].text_en == "N-nothing! The restroom is under repair."
        assert dlg[2].text_zh == "让开。"
        assert dlg[2].text_en == "Move."
        assert dlg[3].text_en == "Thank you for saving me."
