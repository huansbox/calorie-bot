# HANDOFF

- Status: idle
- Task/issue: Telegram 相簿合併判讀 + COROS 體重改走 teamapi + MCP token 帳密自動續期（解 7/18 起 refresh 500 導致 8/17 全斷的死線）
- Branch: main
- Updated: 2026-07-30

## Progress

- **相簿合併**（`022a8ff`）：Telegram 相簿被拆成 N 個 message（只有第一張帶 caption），原本逐張各判讀一次 → 3 張同餐照片變 3 筆、caption 涵蓋的菜色被重複計算（實案多算 642 kcal）。改為依 `media_group_id` 緩衝 2 秒收齊後合併送一次 AI、寫一筆；`analyze_food` 改收 `image_paths`（三條 provider 路徑皆支援），相簿路徑逗號串接存 `meals.image_path`、清理排程拆開刪
- **COROS 體重改走 teamapi**（`04ea25a`）：`services/coros_web.py` 帳密登入，`/account/login` 回應直接帶 `weight`（零 OAuth、單一請求），MCP `queryUserInfo` 降 fallback。比照 strava-sync GitHub #31
- **TDEE 搬不動、改讓 MCP 自己續命**：含 NEAT 的每日活動消耗只有 MCP `queryDailyHealthData` 有——teamapi 沒有（2026-07-30 掃過 Training Hub 前端 bundle 完整端點清單、額外命名、`teamcnapi`、`api.coros.com`；teamapi 只有單場活動 calorie，口徑不同）。故新增 `services/coros_oauth.py`：token 剩 < 3 天時用帳密跑完整 OAuth authorize flow 換新 token，**免瀏覽器**（DCR → authorize → openus 表單登入 → 攔 localhost callback 取 code → PKCE 換 token），token 檔存 `redirect_uri` 供之後重用 client。撈取失敗但 token 未到期也會重新授權後重試一次。實測坑：登入表單預設 `country=CN` 回 `result 1001`（要送 `TW`）、POST 缺 `Origin` 或瀏覽器型 UA 同樣 1001
- **告警調整**：有帳密兜底時 refresh 500 只記 log 不推播（原本每天一則噪音）；沒帳密時維持舊警示行為
- **密鑰**：1Password `Developer / Calorie Bot` 新增 `COROS_EMAIL`(text) / `COROS_PASSWORD`(concealed)，本機與 VPS `.env` 加 `op://` 參照（VPS 備份 `.env.bak-20260730`）
- **VPS 已部署**：merge `28cfacb`，service active；token 換成新的一份（效期 8/16 → **8/29**，舊的備份在 `data/coros-token.json.bak-20260730`）
- **觀察項（非阻塞）**：① 自動續期首次真實觸發約 **8/26 03:05**，成功會推「🔑 COROS token 已自動重新授權」——沒收到且隔天 TDEE 缺就要查；② COROS 若修好 refresh，rotation 會自動恢復（程式仍照試）；③ 帳密路徑的失效條件：改密碼（需同步更新 1Password 欄位）、開 2FA、登入頁改版／加 captcha，三者都會先發 Telegram 告警且有 3 天緩衝
- **本次順手處理**：刪除 7/30 16:26–16:27 三筆重複餐點（今日 5938 → 3326 kcal）、刪除誤加的快取 28 排骨飯便當 / 29 白吐司2片+藍莓果醬（剩 17 筆）

## Next step

None

## Validation

- `uv run pytest` 231 passed（新增 test_meal_media_group.py 4、test_coros_web.py 11、test_coros_mcp.py 擴至 38、test_weight_sync.py 擴至 17）
- 本機實測：teamapi 體重 72.0（與 MCP 值一致）、帳密自動授權拿到 exp 8/29 的 token 並撈得到 daily health、第二次續期重用同一 client 成功
- **VPS 實測**：帳密解析成功、teamapi 體重 72.0、`ensure_token` notice 為 None（refresh 500 已靜默）、MCP `queryDailyHealthData` 回 3 天資料、`queryUserInfo` 回 72.0；**VPS 端自動授權實跑一次通過**（寫暫存檔、驗證後刪除）
- **正式環境驗證相簿合併**：使用者重傳同樣三張照片＋說明 → 只產一筆 1911 kcal（原本 3 筆），與舊的第一筆 1970 同量級
- 測試隔離修正：`test_coros_mcp.py` 加 autouse fixture 清空 COROS 帳密，避免測試跟著開發機 `.env` 飄
- 未跑：8/26 自動續期的真實排程觸發（等時間到）

## Blockers

None
