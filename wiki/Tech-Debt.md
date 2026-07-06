# 技術債

> 快照日期：2026-07-06。依**利息**排序——利息高 = 平常就在付出成本；
> 利息低 = 特定情境才痛。技術債 = 已知的權衡，記錄成本與償還條件，
> **不代表馬上要處理**。Review 節奏：每次 /repo-wiki refresh 重看本頁，
> 過期項目移除或降級。

## 高利息（每天都在付成本）

目前無——repo 維護乾淨，日常運行沒有持續付息的債。

## 中利息（特定操作就會痛）

| 債 | 成本（利息） | 償還策略／條件 | 追蹤 |
|---|---|---|---|
| claude -p 單點依賴 + 60s timeout hardcode【接受現狀】 | CLI 掛掉或超時該餐直接「分析失敗」，需手動記錄逃生；timeout 調整要改 code | 失敗頻率變高時：timeout 提成 env 旋鈕，或接回「claude -p 主、Gemini 反向 fallback」 | [docs/claude-cli-primary-design.md](https://github.com/huansbox/calorie-bot/blob/main/docs/claude-cli-primary-design.md) watch #3/#4 |
| API 週報以 `input_tokens > 0` 判斷有無資料 | claude-cli 某週全 cache-read 回 0 → 該週 API 週報整封不發；同一判準也用來區分 AI vs 手動記錄 | 上線首週（2026-07 第一週）觀察；真發生就改判準 | 同上 watch #2，`services/db.py` get_weekly_token_usage |

## 低利息（記錄在案）

| 債 | 成本（利息） | 償還策略／條件 |
|---|---|---|
| Gemini / Claude API 分支保留但不接線 | 死碼：改 `services/ai.py` 要繞著保留分支走，且無 prod 驗證會逐漸 rot | 確定永不回頭時整段刪除；重啟用前需先補驗證 |
| `ai_confidence` 欄位無效【接受現狀】 | DB 冗欄位；區分 AI vs 手動已由 `input_tokens=0` 取代 | 觀察期結束後移除欄位 |
| op zombie process【接受現狀】 | 1 個 PID entry，零 CPU/RAM；每次看 process list 會困惑一下 | 明文決定不修（根治代價 > 收益），見 CLAUDE.md「已知無害現象」 |
| `/b` 補記餐點修正後累計顯示今天而非補記日【接受現狀】 | 修正補記餐點時累計行語意不準 | 已加註記提示；使用頻率極低，不投資 |

## 記帳原則

- **入場資格**：新債必須寫明「成本（利息）→ 償還策略或條件」——
  沒有成本描述的不收，防止清單變垃圾場
- **接受現狀要明文標註**，避免每次盤點重新吵一遍
- **修完即刪**：償還後刪除條目，摘要移入歷史償還紀錄

## 歷史償還紀錄

- 2026-07-01（commit `97755c7`）：修掉「CLI ≥ 2.1.197 `modelUsage` 混入內部 haiku 導致 `ai_model` 誤記」——部署 smoke 當場抓到。
- 2026-07-01：收掉「botuser 憑證 × root binary」安裝順序留下的意外耦合——bot 改用 botuser 自己的 claude binary；2026-07-06 執行 `chmod 700 /root` 完成權限還原。
- 2026-06-01：weight_logs 同日多筆壓成一天一筆——`log_date` UNIQUE migration（forward-only，已對 prod 執行），所有寫入改 upsert。
