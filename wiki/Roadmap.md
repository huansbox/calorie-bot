# 路線圖

> 快照日期：2026-07-06。長期方向在此；逐項執行狀態見 [Plan](Plan)。

## 已完成里程碑

| 時間 | 里程碑 |
|---|---|
| 2026 上半年 | 核心食物記錄上線：文字／照片 AI 分析、手動記錄三管道、修正按鈕、食物快取、補記 `/b` |
| 2026 上半年 | 週報體系：`/r` 六區塊週報、週一自動推播、API 費用追蹤（每筆 meal 記 tokens + provider） |
| 2026-04 | API key 洩漏事件 → 衍生 `ai_model` 逐筆稽核追蹤 |
| 2026 上半年 | COROS TDEE 每日自動同步（免手動 `/t`），MCP 管線 + OAuth token rotation |
| 2026-06-01 | COROS 體重每日自動同步上線（免手動 `/w`），一天一筆 + 同步決策真值表；06-02 全數驗收（issues 001–008、PRD 22 條 User Story 全覆蓋） |
| 2026-07-01 | **claude -p 轉正**：Gemini 停用（code 保留）、claude-cli 成唯一預設路徑、切 botuser 自己的 binary、關自動更新改每月提醒、每餐回覆印實際模型 |

## 進行中主軸

claude-cli-only 運行觀察期：上線首週確認週報照發、模型標籤穩定；部署收尾（`chmod 700 /root`）已於 2026-07-06 收掉，全案完結。逐項狀態見 [Plan](Plan)，設計全文見 [docs/claude-cli-primary-design.md](https://github.com/huansbox/calorie-bot/blob/main/docs/claude-cli-primary-design.md)。

## 未來方向（尚未排程）

- **月報統計**——等資料滿 2 個月。
- **AI 校正係數**：用體重趨勢反推 AI 估值的系統性偏差，套用在非 cache 的估值上——等資料滿 6-8 週。
- **Web Dashboard**。
- **食物資料庫**：衛福部 TFDA API、自訂食物別名。
- **COROS 深化**：sport records / training load 整合，週報加入訓練量視角。

## 非目標（Non-goals）

刻意不做的事，防止未來「好心」加回來：

- **webhook 模式**——polling 夠用，不想維護公開 URL 與憑證。
- **多使用者支援**——單人 Bot 是頂層約束，auth_check 綁死單一 chat_id。
- **自動 `claude update`**——設計定案改「每月提醒 + 手動更新」：自動換 binary 的所有痛點（hang、排程卡死、無人時 envelope 漂移靜默壞掉）皆源於無人值守，手動更新讓漂移發生在有人看著的時候。理由全文見 docs/claude-cli-primary-design.md。
- **claude -p 的 fallback 鏈**——claude-cli-only 刻意無 fallback，掛掉靠手動記錄逃生；Max 訂閱穩定度可接受。日後失敗頻率變高才重新評估。
- **修 op zombie process**——已評估，唯一根治要犧牲「secret 不落地」，為一顆無害 zombie 不划算。
- **Gemini 重新接線**——已停用，程式碼保留但不投資維護；重啟用是明確決策，不是順手改。

## 收斂點

無固定 deadline，個人專案持續維運。未來方向由**資料累積門檻**驅動：滿 2 個月 → 月報；滿 6-8 週 → 校正係數。
