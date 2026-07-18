# 技術債

> 快照日期：2026-07-18。依**利息**排序——利息高 = 平常就在付出成本；
> 利息低 = 特定情境才痛。技術債 = 已知的權衡，記錄成本與償還條件，
> **不代表馬上要處理**。Review 節奏：每次 /repo-wiki refresh 重看本頁，
> 過期項目移除或降級。

## 高利息（每天都在付成本）

目前無——repo 維護乾淨，日常運行沒有持續付息的債。

## 中利息（特定操作就會痛）

目前無——「claude -p 單點依賴」已於 2026-07-18 償還（見歷史償還紀錄）。

## 低利息（記錄在案）

| 債 | 成本（利息） | 償還策略／條件 |
|---|---|---|
| `data/media/` 孤兒照片（疑似 bug，**待查**） | 3–6 月舊照片殘留與「24 小時過期」設計認知不符，除錯時誤導；磁碟緩慢累積 | 查 03:00 清理排程邏輯（疑只刪 DB 有記錄的檔案，分析失敗等路徑產生的孤兒永久殘留）；補孤兒清掃，或確認 by-design 後明文記錄 |
| API 週報以 `input_tokens > 0` 判斷有無資料 | 該週全無正 token 時整封不發；gemini 主路徑 token 恆 >0，邊界只剩「整週全走 claude-cli fallback 且全 cache-read」的複合罕見情境 | 某週漏發再改判準；`services/db.py` get_weekly_token_usage |
| Claude API 分支（`AI_PROVIDER=claude`）保留但不接線 | 死碼：改 `services/ai.py` 要繞著保留分支走，且無 prod 驗證會逐漸 rot | 確定永不回頭時整段刪除；重啟用前需先補驗證 |
| `ai_confidence` 欄位【觀察轉向】 | v1 時代近乎無效；v2 ＋ 3.1-pro 已見合理分佈，但權威捏造時連帶標 high、不可單獨盡信 | 觀察期後決定留用或移除；區分 AI vs 手動仍用 `input_tokens=0` |
| op zombie process【接受現狀】 | 1 個 PID entry，零 CPU/RAM；每次看 process list 會困惑一下 | 明文決定不修（根治代價 > 收益），見 CLAUDE.md「已知無害現象」 |
| `/b` 補記餐點修正後累計顯示今天而非補記日【接受現狀】 | 修正補記餐點時累計行語意不準 | 已加註記提示；使用頻率極低，不投資 |
| 修正按鈕覆寫營養素後 `note` 仍為原「推估：」內容【接受現狀】 | 校正係數若不排除人工修正筆，校正資料會誤含人工值 | 修正功能幾乎未用；AI 校正係數開工時一併處理（prompt v2 實作 review #16），見 [docs/prompt-v2-design.md](https://github.com/huansbox/calorie-bot/blob/main/docs/prompt-v2-design.md) |

## 記帳原則

- **入場資格**：新債必須寫明「成本（利息）→ 償還策略或條件」——
  沒有成本描述的不收，防止清單變垃圾場
- **接受現狀要明文標註**，避免每次盤點重新吵一遍
- **修完即刪**：償還後刪除條目，摘要移入歷史償還紀錄

## 歷史償還紀錄

- 2026-07-18：償還「claude -p 單點依賴」——AI provider 切回 Gemini（`gemini-3.1-pro-preview`）主路徑＋claude -p fallback 鏈，即原償還策略中的「反向 fallback」方案；60s timeout hardcode 殘留於 fallback 路徑，利息已可忽略。切換全程見 [docs/agy-cli-exploration.md](https://github.com/huansbox/calorie-bot/blob/main/docs/agy-cli-exploration.md)。
- 2026-07-06：補上「note 關鍵字宣稱供機讀、卻無資料路徑」缺口——`meals.note` 欄位落庫（prompt v2 實作 review #2 抓到；forward-only migration `scripts/migrate_meals_add_note.sql` 已對 prod 執行）。
- 2026-07-01（commit `97755c7`）：修掉「CLI ≥ 2.1.197 `modelUsage` 混入內部 haiku 導致 `ai_model` 誤記」——部署 smoke 當場抓到。
- 2026-07-01：收掉「botuser 憑證 × root binary」安裝順序留下的意外耦合——bot 改用 botuser 自己的 claude binary；2026-07-06 執行 `chmod 700 /root` 完成權限還原。
- 2026-06-01：weight_logs 同日多筆壓成一天一筆——`log_date` UNIQUE migration（forward-only，已對 prod 執行），所有寫入改 upsert。
