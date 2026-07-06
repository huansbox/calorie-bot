# 執行中計畫

> 快照日期：2026-07-06。**Source of truth = repo 內 [CLAUDE.md「進行中的設計」段](https://github.com/huansbox/calorie-bot/blob/main/CLAUDE.md) 與 [issues/](https://github.com/huansbox/calorie-bot/tree/main/issues) 目錄**，
> 本頁為導覽快照，衝突時以 repo 為準。

## 主戰場

**claude -p 轉正收尾**（主體已於 2026-07-01 上線）：

- ✅ 已上線：claude-cli 唯一預設路徑、`--model` 走 `CLAUDE_CLI_MODEL`、切 botuser binary、`DISABLE_AUTOUPDATER=1`、每月更新提醒、每餐印實際模型。部署 smoke 抓到並修掉「modelUsage 混入內部 haiku」bug（commit `97755c7`）。
- ✅ **`chmod 700 /root`**（2026-07-06 收）：`/root` 權限已還原，botuser 實跑 claude -p smoke 通過、反向驗證進不去 `/root`——轉正全案完結，無待辦動手項。
- 👀 **上線首週 watch**：確認週一 API 週報照發（`get_weekly_token_usage` 以 `input_tokens > 0` 過濾，claude-cli 全 cache-read 回 0 時該週整封不發，見 [Tech Debt](Tech-Debt)）。

## 其他 active

| 項目 | 狀態 |
|---|---|
| COROS 體重自動同步 | 已全數驗收（issues 001–008），無 active 工作 |

## 被動觀察

不需主動施工、等時間或事件的項目：

- **weight sync 的告警分支實推**：「值同上次輕提醒」與「跳變 >3kg 告警」的 Telegram 實際推送至今未在 prod 觸發（決策邏輯已有單元測試覆蓋），等真實事件出現時瞄一眼 log。
- **`ai_confidence` 欄位**：Gemini 時代就幾乎不回 low/medium，觀察中，未來可能移除。
- **`modelUsage` 缺失邊界**：缺失時 `ai_model=None`、標籤消失，實測一向都有，屬罕見；持續觀察，變常見再加通用標記。
- **VPS 磁碟**：每版 claude binary 約 230 MB，prune 併進每月更新流程，平時不用管。
- **資料量門檻**：滿 2 個月 → 開工月報；滿 6-8 週 → 開工 AI 校正係數（見 [Roadmap](Roadmap)）。

## 開工守則

- 開工先讀 repo 的 CLAUDE.md「進行中的設計」與對應 design doc（docs/）；大型功能走 `/grill-me` 對齊 → PRD → issues 拆解流程。
- 功能開發、重構、bug fix 開 feature branch（feat/xxx, fix/xxx, refactor/xxx），Conventional Commits，小步提交。
- 完工回寫 CLAUDE.md（AI 記憶快照，不留歷史），必要時刷新本 wiki 快照頁。
