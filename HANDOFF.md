# HANDOFF

- Status: idle
- Task/issue: no tracker entry — 使用者從「9/4 起判讀模型變成 claude、且時而 haiku 時而 sonnet」的觀察起手，展開診斷 → 修復 → VPS 維運的一連串工作
- Branch: main
- Updated: 2026-09-06

## Progress

- **診斷 haiku/sonnet 交替**：實際判讀一直是 sonnet，錯的是 `ai_model` 記錄。`services/ai.py` 挑「用量最大模型」的計分只算 `inputTokens + outputTokens`，而 CLI 2.1.222 把整份 system prompt 走 prompt cache，主模型 `inputTokens` 只剩個位數（實測 sonnet 2/88 + cacheRead 18543 + cacheCreation 21219 vs 內部 haiku 911/15）→ 計分變成只比 output，臨界值 ≈ 926。DB 完全吻合：haiku 那批 output 122–759、sonnet 那批 970–1428，零重疊。**注意這推翻了 9/01 HANDOFF 的結論**——當時「真實判讀時 sonnet inputTokens 穩壓 haiku 約 900」在無 cache 的舊版成立，prompt cache 上線後失效
- **修復並部署**（`903e5e2`）：計分改為含 `cacheReadInputTokens` + `cacheCreationInputTokens`，差距從 90:926 變 39852:926
- **DB 回填**：`meals.ai_model` 誤記的 11 筆全部 UPDATE 回 `claude-sonnet-5`（9/4–9/5 共 9 筆為本次 bug；另 2 筆 7/01 是 `97755c7` 修 `next(iter())` 之前的舊 bug，`input_tokens` 2653/2655 的無 cache 形狀可佐證）。查詢 `ai_model=like.*haiku*` 現回 `[]`
- **診斷 Gemini 失效**：2026-09-04 01:52 UTC 起 VPS 對 `generativelanguage.googleapis.com` 全數 400 `User location is not supported`，是 Google 對 datacenter IP 的封鎖，非 key／專案／tier／抵免額問題。詳見 `issues/carryover-gemini-ip-block.md`
- **主路徑失敗告警**（`7d5ac16`）：gemini 的 fallback 原本完全靜默（只有 `logger.warning`），15 次呼叫全滅兩天沒被發現。改為只記狀態**轉換**、各推一則 Telegram，持續失敗不重複。`services` 不碰 Telegram：`push_primary_alert(send)` 收可 await 的送訊息函式，由 `handlers/meal.py`、`handlers/backfill.py` 傳入
- **孤兒圖片兜底**（`eb1cbc7` + `32d96fd`）：`cleanup_expired_images` 是 DB 驅動的，`/u` 撤銷 `delete_meal` 與 AI 分析失敗兩條路徑會斷開關聯讓檔案永久殘留（VPS 實測 15 個檔案有 13 個是孤兒）。加 `sweep_orphan_media` 掃 mtime > 48h。**第一版部署後在 prod 把 `data/media/.gitkeep` 掃掉了**（它永遠是最舊的），已還原並補 dotfile 跳過
- **VPS housekeeping**：刪 5 個 2026-03-11 扁平結構遺留的 `.py`、3 個 `.env.bak*`（逐檔驗過無明文密鑰）、1 個過期 COROS token 備份、13 個孤兒圖片
- **SSH 加固 + log 降噪**（`39c0bb1`、`027220a`）：實測 24h 內 9,612 次 Failed password／174 個來源 IP，sshd 佔 journal 78.7%、httpx getUpdates 佔 17.6%。三項處置見 `CLAUDE.md`「SSH 加固與 log 噪音」段
- **安全事件（本 session 造成）**：SA token 明文洩進 VPS `/var/log/auth.log`，見 `issues/carryover-op-token-rotation.md`

## Next step

兩件都在 `issues/` 有 carry-over 項目，皆待使用者決定或動手，**都不是已規格化的任務**：

1. `issues/carryover-op-token-rotation.md` —— **優先**。輪替 1Password SA token（使用者在 1Password 產生 → 寫入 VPS `/etc/calorie-bot/op-token.env` → restart → 驗證）
2. `issues/carryover-gemini-ip-block.md` —— Gemini 路線三選一（換 IP／驗 Vertex／先觀察兩週）

另外**繼續 carry 9/01 HANDOFF 未表態的一項、仍未建 entry**：fallback（`claude -p`）本身的健康度只有每月 1 號手動提醒會檢出。本 session 做的是**主路徑**失敗告警，方向相反，沒有涵蓋它。目前 gemini 全掛使 `claude -p` 天天被呼叫，問題暫時不顯；gemini 一恢復就會回來。下個 session 應把它當「要不要做」的問題問，不要當已核可任務。

已查過、無待辦動作：`issues/` 001–008 全數完成（COROS 體重同步 PRD）、GitHub issues 為空（此 repo 用本地 `issues/` 當 tracker）。

## Validation

- `uv run pytest -q` **256 passed**（本 session 新增 20 個 case：`test_ai.py` 12、`test_scheduler.py` 12 減去重構；全套跑過多次，含連跑 3 次確認無 flaky）
- **prod smoke（模型記錄）**：VPS 實跑 `_analyze_claude_cli("葡式蛋塔 1顆")` → `ai_model = claude-sonnet-5`，output 356 tokens（舊邏輯必記成 haiku）
- **prod smoke（告警狀態機）**：第一次呼叫產生含真實 400 錯誤的告警訊息、第二次回 `None`（抑制生效）
- **prod 驗證（兜底掃描）**：`swept = 0`，`.gitkeep` 與 2 張未滿 48h 的照片都保留
- **prod 驗證（httpx 降噪）**：restart 後 90 秒內 getUpdates INFO **0 筆**
- **prod 驗證（SSH 加固）**：`sshd -T` 顯示 `passwordauthentication no`；新連線 key 登入 OK；密碼登入回 `Permission denied (publickey)`；加固後所有 `Accepted` 均為同一把 ED25519 + 使用者 IP
- **DB 驗證**：UPDATE 回傳 9 + 2 筆，事後查詢 haiku 殘留為 `[]`
- 已部署：VPS `git log -1` = `027220a`，service `active`
- **未跑**：真實 fallback 端到端（要 gemini 恢復才測得到 `_mark_primary_ok` 的恢復通知分支）；`/u` 撤銷造成孤兒後被兜底掃描回收的完整循環（需等 48h）；Vertex AI 可行性（需先建 GCP service account）

## Blockers

None
