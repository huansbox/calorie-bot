"""decide_weight_sync 真值表測試（純函式，無 I/O）。

風格比照 tests/test_dates.py / tests/test_backfill.py：給定輸入、斷言輸出，
逐條覆蓋 PRD「同步決策核心」真值表 + 閾值邊界。
"""
from services.weight_sync import (
    ALERT_NO_WRITE,
    SKIP,
    WRITE_ALERT,
    WRITE_SILENT,
    decide_weight_sync,
)


class TestDecideWeightSync:
    # 1. today_has_row → SKIP（且優先於所有其他條件）
    def test_today_has_row_skips(self):
        d = decide_weight_sync(70.5, 71.0, today_has_row=True)
        assert d.action == SKIP
        assert d.message is None
        assert d.should_write is False

    def test_today_has_row_dominates_even_when_fetch_failed(self):
        # 抓取失敗但當天已有筆 → 仍 SKIP，不發告警
        d = decide_weight_sync(None, 71.0, today_has_row=True)
        assert d.action == SKIP
        assert d.message is None

    def test_today_has_row_dominates_even_on_big_jump(self):
        d = decide_weight_sync(200.0, 71.0, today_has_row=True)
        assert d.action == SKIP

    # 2. fetched is None → ALERT_NO_WRITE
    def test_fetch_failed_alerts_no_write(self):
        d = decide_weight_sync(None, 71.0, today_has_row=False)
        assert d.action == ALERT_NO_WRITE
        assert d.message is not None
        assert d.should_write is False

    def test_fetch_failed_with_no_baseline_still_alerts(self):
        d = decide_weight_sync(None, None, today_has_row=False)
        assert d.action == ALERT_NO_WRITE

    # 3. last_weight is None（冷啟動）→ WRITE_SILENT
    def test_cold_start_writes_silently(self):
        d = decide_weight_sync(70.0, None, today_has_row=False)
        assert d.action == WRITE_SILENT
        assert d.message is None
        assert d.should_write is True

    # 4. |fetched − last| > 3 → ALERT_NO_WRITE
    def test_big_jump_up_alerts_no_write(self):
        d = decide_weight_sync(75.0, 71.0, today_has_row=False)  # diff 4
        assert d.action == ALERT_NO_WRITE
        assert d.should_write is False

    def test_absurd_value_treated_as_jump(self):
        # 離譜壞值（0、200）本質就是極端跳變，走同一條
        assert decide_weight_sync(0.0, 71.0, today_has_row=False).action == ALERT_NO_WRITE
        assert decide_weight_sync(200.0, 71.0, today_has_row=False).action == ALERT_NO_WRITE

    # 5. fetched == last（嚴格相等）→ WRITE_ALERT
    def test_same_as_last_writes_and_alerts(self):
        d = decide_weight_sync(71.0, 71.0, today_has_row=False)
        assert d.action == WRITE_ALERT
        assert d.message is not None
        assert d.should_write is True

    # 6. 正常新值 → WRITE_SILENT
    def test_normal_new_value_writes_silently(self):
        d = decide_weight_sync(70.5, 71.0, today_has_row=False)
        assert d.action == WRITE_SILENT
        assert d.message is None

    # ── 閾值邊界 ──────────────────────────────────────────
    def test_diff_exactly_3_does_not_trigger(self):
        # 差剛好 3.0 不算「超過」→ 正常寫入
        d = decide_weight_sync(74.0, 71.0, today_has_row=False)
        assert d.action == WRITE_SILENT

    def test_diff_3_01_triggers(self):
        d = decide_weight_sync(73.01, 70.0, today_has_row=False)
        assert d.action == ALERT_NO_WRITE

    def test_negative_jump_3_01_triggers(self):
        d = decide_weight_sync(66.99, 70.0, today_has_row=False)  # diff -3.01
        assert d.action == ALERT_NO_WRITE

    def test_negative_jump_exactly_3_does_not_trigger(self):
        d = decide_weight_sync(68.0, 71.0, today_has_row=False)  # diff -3.0
        assert d.action == WRITE_SILENT
