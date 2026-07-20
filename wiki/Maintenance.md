# 維運手冊

## 執行環境

- **Prod**：RackNerd VPS（Ubuntu 24.04），bot 以 `botuser` 帳號跑在 `/home/botuser/calorie-bot`，由 systemd 服務 `calorie-bot.service` 管理；密鑰經 1Password Service Account 由 `op run` 注入（token 檔 `/etc/calorie-bot/op-token.env`，權限 600、root only）。
- **本機開發**：`op run --env-file .env -- python main.py`（需 1Password 桌面 App 解鎖）。
- **環境鐵律**：
  - Python 一律 `uv run`，不裸呼叫 `python`——跨機器（macOS / Windows）版本不一致，裸呼叫命中的直譯器不可預期。
  - Windows 開發需設 `PYTHONIOENCODING=utf-8`——預設 codepage cp950，輸出中文或 emoji 會炸。
  - DB 查詢凡有 ORDER BY 必含唯一欄位（如 `id`）作 tie-breaker——同 timestamp 排序不確定，會造成間歇性錯資料。

## 排程 / 自動化

全部**台灣時間**（VPS 系統時鐘是 UTC，差 8 小時；看 journalctl 時間戳記得換算）：

| 時間 | 內容 |
|---|---|
| 每日 08:00 | 昨日攝取摘要推播（含最新體重與 7 日均線） |
| 週一 08:05 | API 用量與費用週報 |
| 週一 08:10 | 上週營養週報 |
| 每日 03:00 | 清理過期照片（暫存 24 小時） |
| 每日 03:05 | COROS TDEE 同步（拉過去 7 天，fill-missing-only，不覆寫手動 `/t`） |
| 每日 10:29 / 22:29 | COROS 體重同步（主／fallback，一天一筆，當天已有筆即 SKIP） |
| 每月 1 號 10:30 | claude binary 手動更新提醒（附貼式 prompt） |

## 部署更新

```bash
ssh root@107.175.30.172 "cd /home/botuser/calorie-bot && sudo -u botuser git pull origin main && sudo systemctl restart calorie-bot"
```

首次部署、systemd unit 內容、COROS token 首次部署流程見 [README](https://github.com/huansbox/calorie-bot/blob/main/README.md) 與 [CLAUDE.md 部署段](https://github.com/huansbox/calorie-bot/blob/main/CLAUDE.md)。

## 日常 / 週期 SOP

- **每餐（被動）**：AI 分析回覆的模型標籤（正常 `· gemini-3.1-pro-preview`；出現 `· claude-sonnet-5` ＝ Gemini 掛了走 fallback）＝模型漂移與 fallback 觸發的即時監控。gemini 標籤來自 API 回傳的 `model_version`，preview 模型被 Google 改版重導向時會直接現形。
- **每週一**：確認 API 週報與營養週報有推播（漏發見下方故障排查）。
- **每月 1 號**：收到 Telegram 更新提醒後，手動對 botuser 的 claude binary 執行 `claude update`——訊息附可直接貼給 Claude Code session 的 prompt，內含 smoke 驗證與 prune（保留最新 2 版，每版約 230 MB）。自動更新已用 `DISABLE_AUTOUPDATER=1` 關閉，**binary 唯一會變的時機＝這次手動更新**。

## 已知地雷（Gotchas）

動手前先讀各條標註的出處追蹤檔，以下僅為人類可讀摘要。只收實際踩過的。

**系統面**：

- **op zombie process（決定不修）**：`calorie-bot.service` 穩定掛 1 個 `[op] <defunct>`，源於 op 啟動 daemon 的 double-fork。無害（1 個 PID entry、零 CPU/RAM）、每次重啟重生但不累積；已評估過所有修法都不划算。看到它不要動手「修」。出處：CLAUDE.md「已知無害現象」段。
- **COROS refresh_token rotation**：每次 refresh 都換新 token、舊的立即失效。`services/coros_mcp_core.py` 以 atomic write（tmp file + rename）寫回、`save → fetch` 順序確保 refresh 成功先持久化。refresh 失敗會退用既存 access_token（30 天效期）續撈並發「已續行」警示，不再整體中止。動這段前務必讀 CLAUDE.md 關鍵設計決策段；token 檔壞掉要重跑 bootstrap。
- **COROS 共用核心**：`services/coros_mcp_core.py` 與 strava-sync `lt2_auto/coros_mcp_core.py` 是必須逐字節相同的複本；改任一份後跑 strava-sync `tools/sync_coros_core.py` 同步（其 sync.bat 每小時 drift check + ntfy 告警）。
- **claude CLI `modelUsage` 混入內部小模型**：CLI ≥ 2.1.197 的 stdout envelope 會混入內部 haiku，`ai_model` 必須取 token 用量最大的主模型、不能取第一個 key（舊版單 key 時剛好對，升級後會誤記）。出處：commit `97755c7`、CLAUDE.md「ai_model 追蹤」。
- **`--model` 別名解析 baked 進 binary 版本**：`--model sonnet` 只給「這顆 binary 知道的最新 sonnet」，更新 binary 可能讓模型跳版（如 sonnet-4-6 → Sonnet 5）。出處：[docs/claude-cli-primary-design.md](https://github.com/huansbox/calorie-bot/blob/main/docs/claude-cli-primary-design.md)。
- **DB migrations 是 forward-only**：`scripts/migrate_weight_logs_log_date.sql` 與 `scripts/migrate_meals_add_note.sql` 都已對 prod 執行過，不可重跑。

**決策面**（看起來像 bug 但是刻意設計，不要「好心」修掉）：

- 08:00 昨日摘要跑在 10:29 體重同步**之前**，早上摘要的「最新體重」是前一天的筆——符合「昨日摘要」語意，不需改。
- COROS profile 體重無時間戳，體重自動同步走「日期路線」：當天沒筆就寫，接受偶爾寫入沿用舊值的假點；`/w` 手動記錄是假點修正出口（manual 永遠覆蓋當天）。
- `/b` 補記的餐點事後修正時，累計行顯示今天而非補記日——已知限制，回覆已加註記提示。

## 故障排查

| 症狀 | 先看哪裡 |
|---|---|
| 任何異常 | `ssh root@107.175.30.172` 後 `journalctl -u calorie-bot -f`（時間戳是 UTC） |
| 回覆「分析失敗，請重試。」 | Gemini API 與 fallback claude -p **兩者都掛**才會出現（Gemini 單獨掛會靜默 fallback，log 有 warning、回覆模型標籤變 claude）。先用手動記錄逃生（`@品名 熱量`、快取編號 11-99、`/m`），再查 journalctl 與 VPS 手動跑 `claude -p` |
| 服務起不來 | `systemctl status calorie-bot`；確認 `/etc/calorie-bot/op-token.env` 存在且 1Password Service Account token 有效 |
| COROS 同步告警（昨天沒拉到資料） | 檢查 `data/coros-token.json`（botuser 需有檔案與目錄寫權限）；token rotation 壞掉需本機重跑 `scripts/coros_mcp_bootstrap.py` 再傳上去 |
| COROS token refresh 失敗（已續行）警示 | COROS 端 refresh 故障、資料面正常，同步未中斷；注意 access_token 效期約 30 天（起算＝最後一次成功 rotation＝token 檔 mtime），若故障持續逼近效期，重跑 bootstrap 換新 token |
| 週一 API 週報沒發 | 已知邊界：該週 claude-cli 的 `input_tokens` 全為 0 時整封不發，見 [Tech Debt](Tech-Debt) |
| Bot 完全無回應 | polling 模式，查 VPS 對外網路與 `TELEGRAM_TOKEN`；重啟服務 |
