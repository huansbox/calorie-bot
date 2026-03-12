import pytest

from handlers.manual_meal import (
    is_at_manual_input,
    is_bot_reply_format,
    parse_at_input,
    parse_bot_reply,
)


class TestIsBotReplyFormat:
    def test_full_reply(self):
        text = (
            "記錄完成\n"
            "🍱 起司蛋餅\n"
            "熱量：350 kcal\n"
            "蛋白質：15g　碳水：30g　脂肪：18g\n"
            "餐別：早餐"
        )
        assert is_bot_reply_format(text) is True

    def test_plain_text(self):
        assert is_bot_reply_format("滷肉飯加蛋") is False

    def test_partial_emoji_only(self):
        assert is_bot_reply_format("🍱 好吃") is False

    def test_partial_calories_only(self):
        assert is_bot_reply_format("熱量：350 kcal") is False


class TestParseBotReply:
    def test_full_reply(self):
        text = (
            "記錄完成\n"
            "🍱 一之軒芝麻麻糬\n"
            "熱量：152 kcal\n"
            "蛋白質：2g　碳水：23g　脂肪：6g\n"
            "餐別：晚餐\n"
            "\n"
            "今日累計：1,999 / 2,000 kcal"
        )
        result = parse_bot_reply(text)
        assert result["description"] == "一之軒芝麻麻糬"
        assert result["calories"] == 152
        assert result["protein_g"] == 2.0
        assert result["carbs_g"] == 23.0
        assert result["fat_g"] == 6.0

    def test_reply_with_note(self):
        text = (
            "記錄完成\n"
            "🍱 自煮火鍋（牛蕃茄、牛肉火鍋肉片、包心白菜）、白飯一碗、烏龍麵175克\n"
            "熱量：1,160 kcal\n"
            "蛋白質：58g　碳水：172g　脂肪：27g\n"
            "餐別：午餐\n"
            "\n"
            "今日累計：1,751 / 2,000 kcal\n"
            "📝 估算基礎：牛蕃茄50kcal"
        )
        result = parse_bot_reply(text)
        assert result["description"] == "自煮火鍋（牛蕃茄、牛肉火鍋肉片、包心白菜）、白飯一碗、烏龍麵175克"
        assert result["calories"] == 1160
        assert result["protein_g"] == 58.0
        assert result["fat_g"] == 27.0

    def test_reply_with_manual_tag(self):
        text = (
            "記錄完成（手動）\n"
            "🍱 御飯糰\n"
            "熱量：280 kcal\n"
            "蛋白質：0g　碳水：0g　脂肪：0g\n"
            "餐別：早餐"
        )
        result = parse_bot_reply(text)
        assert result["description"] == "御飯糰"
        assert result["calories"] == 280

    def test_new_format_with_pct(self):
        text = (
            "記錄完成\n"
            "🍱 起司蛋餅\n"
            "熱量：350 kcal\n"
            "🍗 蛋白質 15g (17%)\n"
            "🍚 碳水 30g (34%)\n"
            "🧈 脂肪 18g (49%)\n"
            "餐別：早餐"
        )
        result = parse_bot_reply(text)
        assert result["description"] == "起司蛋餅"
        assert result["calories"] == 350
        assert result["protein_g"] == 15.0
        assert result["carbs_g"] == 30.0
        assert result["fat_g"] == 18.0

    def test_missing_macro_defaults_zero(self):
        text = "🍱 咖啡\n熱量：50 kcal"
        result = parse_bot_reply(text)
        assert result["calories"] == 50
        assert result["protein_g"] == 0.0
        assert result["carbs_g"] == 0.0
        assert result["fat_g"] == 0.0

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_bot_reply("隨便的文字")


class TestIsAtManualInput:
    def test_at_with_content(self):
        assert is_at_manual_input("@御飯糰 280") is True

    def test_at_alone(self):
        assert is_at_manual_input("@") is False

    def test_plain_text(self):
        assert is_at_manual_input("滷肉飯") is False

    def test_at_in_middle(self):
        assert is_at_manual_input("email@test.com") is False


class TestParseAtInput:
    def test_name_and_calories_only(self):
        result = parse_at_input("@御飯糰 280")
        assert result["description"] == "御飯糰"
        assert result["calories"] == 280
        assert result["protein_g"] == 0.0
        assert result["carbs_g"] == 0.0
        assert result["fat_g"] == 0.0

    def test_full_macros(self):
        result = parse_at_input("@起司蛋餅 350 15 30 18")
        assert result["description"] == "起司蛋餅"
        assert result["calories"] == 350
        assert result["protein_g"] == 15.0
        assert result["carbs_g"] == 30.0
        assert result["fat_g"] == 18.0

    def test_name_with_spaces(self):
        result = parse_at_input("@7-11 御飯糰 鮪魚 280")
        assert result["description"] == "7-11 御飯糰 鮪魚"
        assert result["calories"] == 280

    def test_full_macros_with_spaces_in_name(self):
        result = parse_at_input("@全家 地瓜 120 2 28 0")
        assert result["description"] == "全家 地瓜"
        assert result["calories"] == 120
        assert result["protein_g"] == 2.0
        assert result["carbs_g"] == 28.0
        assert result["fat_g"] == 0.0

    def test_decimal_macros(self):
        result = parse_at_input("@牛奶 150 8.5 12.3 6.2")
        assert result["protein_g"] == 8.5
        assert result["carbs_g"] == 12.3
        assert result["fat_g"] == 6.2

    def test_no_numbers_raises(self):
        with pytest.raises(ValueError):
            parse_at_input("@只有品名沒有數字")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_at_input("@")
