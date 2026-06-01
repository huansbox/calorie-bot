"""體重同步決策核心（純函式，無 I/O）。

decide_weight_sync 封裝「該不該寫 / 寫什麼 / 要不要告警」的所有判斷，依 PRD
「同步決策核心」真值表。scheduler 的 sync_coros_weight（issues/005、006）消費其
輸出：依 action 決定是否 upsert、依 message 決定是否推 Telegram。

真值表（順序即優先序）：

    today_has_row=True          → SKIP            （當天已有筆，含晚班 fallback；晨重優先）
    fetched is None             → ALERT_NO_WRITE  （抓取/解析失敗）
    last_weight is None         → WRITE_SILENT    （DB 冷啟動，第一筆不擋）
    |fetched − last_weight| > 3 → ALERT_NO_WRITE  （跳變過大，含離譜壞值如 0/200）
    fetched == last_weight      → WRITE_ALERT     （值同上次，寫入並提醒可能是假點）
    其他（正常新值）            → WRITE_SILENT
"""
from __future__ import annotations

from dataclasses import dataclass

# |fetched − last_weight| 超過此值視為跳變過大 → 不自動寫入。
# 固定閾值同時涵蓋「離譜壞值」與「真實大跳變」——離譜值本質就是極端跳變。
JUMP_THRESHOLD_KG = 3.0

# action 常數
SKIP = "SKIP"                      # 不寫、不通知
WRITE_SILENT = "WRITE_SILENT"      # 寫入、不通知
WRITE_ALERT = "WRITE_ALERT"        # 寫入 + 推假點輕提醒
ALERT_NO_WRITE = "ALERT_NO_WRITE"  # 不寫、推告警


@dataclass(frozen=True)
class Decision:
    """同步決策結果。

    action：上述四個常數之一。
    message：需推 Telegram 的文字（WRITE_ALERT / ALERT_NO_WRITE）；其餘為 None。
    """
    action: str
    message: str | None = None

    @property
    def should_write(self) -> bool:
        return self.action in (WRITE_SILENT, WRITE_ALERT)


def decide_weight_sync(
    fetched: float | None,
    last_weight: float | None,
    today_has_row: bool,
) -> Decision:
    """依真值表決定體重同步動作。純函式，無 I/O。

    參數：
        fetched: 這次從 COROS 抓到的體重（parse 失敗為 None）。
        last_weight: DB 最近一筆體重（冷啟動為 None）。
        today_has_row: 今天台灣日期是否已有任何體重筆。
    """
    # 1. 當天已有筆 → 一律不動（手動或早班已寫；晚班 fallback 也走這條 → 晨重優先）
    if today_has_row:
        return Decision(SKIP)

    # 2. 抓取 / 解析失敗 → 告警不寫
    if fetched is None:
        return Decision(
            ALERT_NO_WRITE,
            "⚠️ COROS 體重同步失敗：抓不到或解析不到體重，請手動 /w 補上。",
        )

    # 3. 無基準（DB 冷啟動）→ 第一筆不擋，靜默寫入
    if last_weight is None:
        return Decision(WRITE_SILENT)

    # 4. 跳變過大（含離譜壞值如 0 / 200）→ 告警不寫
    if abs(fetched - last_weight) > JUMP_THRESHOLD_KG:
        return Decision(
            ALERT_NO_WRITE,
            f"⚠️ COROS 體重 {fetched} kg 與上次 {last_weight} kg 差超過 "
            f"{JUMP_THRESHOLD_KG:g} kg，未自動寫入。若正確請手動 /w {fetched} 確認。",
        )

    # 5. 值與上次完全相同（嚴格相等，一位小數）→ 寫入但提醒可能是沒量、沿用舊值
    if fetched == last_weight:
        return Decision(
            WRITE_ALERT,
            f"⚖️ COROS 體重與上次相同（{fetched} kg）。若今天還沒量，請手動 /w 更新。",
        )

    # 6. 正常新值 → 靜默寫入
    return Decision(WRITE_SILENT)
