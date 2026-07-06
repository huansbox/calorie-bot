# Calorie Bot — 專案 Wiki

個人用 Telegram 體重管理 Bot：傳食物照片或文字，AI Vision 自動分析三大營養素並記錄至 Supabase；搭配 COROS 手錶自動同步 TDEE 與體重，週報追蹤熱量收支。單人使用、已於 VPS 穩定運行。

## 頂層約束

以下約束 gate 所有後續決策：

- **單人 Bot、單人維護**：所有 handler 統一以 chat_id 驗證（auth_check decorator），不做多使用者；方案取捨一律「優先簡單方案」。
- **AI 分析成本壓零**：預設唯一路徑是 `claude -p` CLI（走 Max 訂閱、零 API 費用），**無 fallback**——CLI 掛掉該餐直接「分析失敗」，靠手動記錄逃生。Gemini / Claude API 程式碼保留可切換，但不接線。
- **polling 模式（非 webhook）**：不需公開 URL、不需反向代理，簡單優先。
- **密鑰不落地**：1Password 管理（本機 `op run`、VPS Service Account），`.env` 只存 `op://` 參照，明文密鑰不進磁碟。
- **排程時間一律台灣時間**（scheduler `timezone="Asia/Taipei"`）；VPS 系統時鐘是 UTC，差 8 小時，看 log 時需換算。

## 系統組成

| 模組 | 職責 |
|---|---|
| `main.py` | 進入點：註冊 handlers 與排程、auth_check decorator |
| `handlers/` | Telegram 指令層：食物記錄（meal）、體重（weight）、TDEE、今日摘要（query）、修正（correction）、手動記錄（manual_meal）、食物快取（food_cache）、週報（report）、補記（backfill） |
| `services/` | 核心邏輯：AI 引擎（ai）、Supabase CRUD（db）、營養計算（nutrition）、日期解析（dates）、訊息格式化（format）、COROS MCP client（coros_mcp）、體重同步決策純函式（weight_sync） |
| `scheduler.py` | APScheduler 排程：每日摘要、週報、照片清理、COROS 同步、更新提醒 |
| `scripts/` | 一次性工具：COROS OAuth bootstrap、手動補登、DB migration |
| `tests/` | 純函式單元測試，涵蓋 AI 回應解析、營養計算、日期解析、各 handler 的解析函式與同步決策真值表 |

架構細節與關鍵設計決策以 repo 內 [CLAUDE.md](https://github.com/huansbox/calorie-bot/blob/main/CLAUDE.md) 為準，本頁不重寫。

## 專案階段

- **已完成**：核心食物記錄（文字／照片 AI 分析、手動記錄、食物快取、修正按鈕）、週報與 API 費用追蹤、COROS TDEE 每日自動同步、COROS 體重每日自動同步（2026-06 上線並全數驗收）。
- **2026-07-01 上線**：`claude -p` 轉正——Gemini 停用、claude-cli 成為唯一預設分析路徑，配每月手動更新提醒與每餐模型標籤。
- **進行中**：claude-cli-only 運行觀察期與部署收尾，詳見 [Plan](Plan)。

## Wiki 頁面導覽

| 頁面 | 內容 |
|---|---|
| [Maintenance](Maintenance) | 維運手冊 — 環境、排程、部署、地雷、故障排查 |
| [Roadmap](Roadmap) | 路線圖 — 里程碑、方向、非目標 |
| [Plan](Plan) | 執行中計畫快照 |
| [Tech Debt](Tech-Debt) | 技術債 — 利息排序 + 償還紀錄 |

> **文件分工**：wiki 是導覽與快照；策略 / 規格 / 待辦的 source of truth
> 在 repo 內（CLAUDE.md、issues/、docs/）。兩者衝突時以 repo 為準。
