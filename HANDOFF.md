# HANDOFF — 2026-07-18 AI provider 切換案已完結部署，進入觀察期

## 目標

AI provider 品質評估案（Sonnet 台灣品牌知識缺口 → 切回 gemini）**已全部完成並部署**：`gemini-3.1-pro-preview` 上線、費率 $2/$12、gemini 路徑記 `ai_model`、回覆印模型標籤、CLAUDE.md／wiki 全數刷新。無未完成的主動工作。全程記錄：[docs/agy-cli-exploration.md](docs/agy-cli-exploration.md)。

## 進度

- 已完成：見 CLAUDE.md「進行中的設計」前兩條與 wiki [Plan](wiki/Plan.md)（快照 2026-07-18，與現況同步）
- 進行中：純被動觀察——note 權威捏造率（已知 1/8）、preview 模型異動（看 ai_model 漂移）、GCP 抵免額消耗
- 下一步：無必做事項；可選 follow-up 見下

## 對話中已對齊、尚未落檔的決策

- **GCP billing 已由使用者在 Cloud Console 接回**（API key 專案 ↔ 抵免額 billing account）。docs/agy-cli-exploration.md「billing 阻塞（待使用者處理）」段的待辦已解，文件未回頭標註——接班若動該文件可順手補一句，不值得單獨開工
- **機器硬檢構想已獲使用者認可但未排程**：「無圖片＋note 以『標示轉錄：』開頭」＝必然捏造，程式可判定（`has_image=False` 檢查），觸發時機＝使用者說要做，或觀察期捏造率變常見。「官方值：」不可硬檢（連鎖店記憶引用合法）
- **media 孤兒照片疑似 bug** 已收 wiki Tech-Debt 待查，使用者未指示查——不要主動開工

## 注意事項

- agy CLI（v1.1.4）留在 VPS `/home/botuser/.local/bin/agy`，OAuth 憑證走使用者 Google AI Pro 帳號；smoke 腳本 `/home/botuser/agy-smoke.sh`。**這是評估遺留物＋未來搜尋能力選項，不是 production 依賴**
- `/tmp/gemini_model_test.py`（多模型對照腳本）在 VPS reboot 後會消失，屬預期；要重測從 docs 的記錄重建
- `.env` 的 `CLAUDE_CLI_MODEL=sonnet` 未動——claude -p 現為 fallback，仍解析 Sonnet 5，每月更新提醒照常
- 週報費率是 provider 一口價：gemini 歷史筆（2.5-pro 時代）若落在同一報表週會被以新費率計，已明文列為非目標（不做 per-model 費率表）

## Suggested skills

- `/repo-wiki refresh`：下個 milestone 或月度刷新快照頁
- `/doc-review`：使用者若要審 CLAUDE.md／agy-cli-exploration.md 時（規範上由使用者呼叫）

## 如何接續

main branch（無 feature branch 進行中）。先讀 CLAUDE.md「進行中的設計」前兩條，再讀 docs/agy-cli-exploration.md「定案」段即可掌握全貌。無需開場動作，等使用者出題。

---
本檔讀完即刪（`/handoff` 接班流程會處理）。
