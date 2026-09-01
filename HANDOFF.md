# HANDOFF

- Status: idle
- Task/issue: no tracker entry — 9/01 月更新提醒觸發的 claude CLI 維護，過程中發現並修復 claude -p fallback 的認證失效
- Branch: main
- Updated: 2026-09-01

## Progress

- **claude binary 更新**：VPS botuser 的 CLI `2.1.197 → 2.1.252`，symlink 自動重指，prune 掉 `2.1.96`（versions 目錄留 2.1.197 + 2.1.252，439M）。`--model sonnet` 仍解析到 `claude-sonnet-5`，沒跳版
- **發現 fallback 認證早已失效**：smoke 回 `OAuth session expired and could not be refreshed`，`~/.claude/.credentials.json` 的 token 被 CLI 清成空字串。根因不是這次更新——journal 顯示最後一次成功的 `claude -p` 是 **2026-07-18 05:07**（切 gemini 當天一次 429 fallback），之後 6 週零呼叫；那份短期 token 只在 `claude -p` 實際執行時才會 refresh，沒被呼叫就靜靜過期。credentials 被清空的時點（09:42:56 UTC）早於新 binary 寫入，是 CLI 啟動時 refresh 失敗所致，更新只是把它暴露出來
- **改用長效 OAuth token**（`b9e013b`）：`claude setup-token` 產生的 1 年期 token（**2027-09-01 到期**）存進 1Password `Developer / Calorie Bot` 的 `CLAUDE_CODE_OAUTH_TOKEN` 欄位，VPS `.env` 加 `op://` 參照注入（舊檔備份 `.env.bak.20260901`）。關鍵事實：`setup-token` **不會**寫回 credentials 檔，它產的 token 只能透過環境變數使用。長效 token 沒有「不用就壞」的性質
- **月提醒改寫兩輪**（`3d6b9d4` → `b9e013b`）：① 開頭「唯讀報告」與 step 2/5 實際會寫入矛盾，改成「不要 restart bot、不要改 .env 或 systemd 設定」；② step 3 補失敗分支與**必要的 token 注入指令**——SSH 進去直接跑 `claude -p` 必定失敗（credentials 檔是空的），提醒現在直接給注入三行；③ 補 `< /dev/null`（heredoc 餵 bash 時 claude 會把剩下的 script 當 stdin 吃掉，症狀是完全無輸出，本次實際踩到）；④ step 4 警告 ping 這種極短輸入下內部 haiku 用量會反超 sonnet，別直接取 modelUsage 用量最大者
- **`services/ai.py` 的取模型邏輯經檢視無誤**：真實判讀時 SYSTEM_PROMPT 2415 字，sonnet 的 inputTokens 穩壓 haiku 的約 900，「取用量最大者」成立；問題只在 ping smoke 測不出來，已寫進提醒
- **驗證過上一個 session 的 COROS 觀察項**：8/31 19:05 UTC（台北 9/01 03:05）的 TDEE 同步 log 顯示 `refresh_token rotated` 成功、抓到 8 天 daily health、寫入 8/31 = 3550 kcal。COROS 的 refresh 500 已自行修復，rotation 恢復正常，帳密自動重新授權因此從未真的觸發（journal 8/20 起無相關事件）
- **文件**：`CLAUDE.md` 新增「claude -p 認證＝長效 OAuth token」設計決策（含 2027-09 換發流程、為何不再用 credentials 檔、`ANTHROPIC_API_KEY` 註解狀態使 OAuth 成為唯一認證來源），1Password 欄位清單補 `CLAUDE_CODE_OAUTH_TOKEN`

## Next step

None。本 session 提出但**使用者未表態、故未建立 tracker 項目**的一件事：fallback 的健康度目前只有每月 1 號的手動提醒會檢出，中間任何時候壞掉都不會告警（這次就是壞了 6 週沒人知道）。若要補，最省的做法是加一個定期跑 `claude -p` smoke、失敗推 Telegram 的排程 job；這超出本次範圍，下個 session 應把它當「要不要做」的問題問，而不是當已核可的任務。其餘查過的地方：`issues/` 001–008 全數完成、GitHub 無 open issue、`CLAUDE.md`「進行中的設計」的 gemini／prompt v2 觀察清單都是持續觀察性質，沒有待辦動作。

## Validation

- `uv run pytest -q` 231 passed（兩次：改提醒文字後、改 CLAUDE.md 後）
- `uv run python -c "import scheduler; print(UPDATE_REMINDER_TEXT)"` 確認提醒可正常組出，長度 1486 字元（Telegram 上限 4096）
- **VPS 實測 claude -p**：注入 `CLAUDE_CODE_OAUTH_TOKEN` 後 `exit=0`、`is_error=false`、`result` 回合法 JSON、`modelUsage` 含 `claude-sonnet-5`
- **VPS 環境驗證**：restart 後確認 bot 子行程 environ 內有 `CLAUDE_CODE_OAUTH_TOKEN`；service `active`，排程正常註冊
- 已部署：VPS `git log -1` = `143b49b`
- 未跑：真實 fallback 端到端（要 gemini 失敗才會觸發，無法自造）；圖片路徑 smoke（下一餐真實照片會驗）

## Blockers

None
