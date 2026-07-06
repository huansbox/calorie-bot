# 執行中計畫

> 快照日期：2026-07-06。**Source of truth = repo 內 [CLAUDE.md「進行中的設計」段](https://github.com/huansbox/calorie-bot/blob/main/CLAUDE.md) 與 [issues/](https://github.com/huansbox/calorie-bot/tree/main/issues) 目錄**，
> 本頁為導覽快照，衝突時以 repo 為準。

## 主戰場

**Prompt v2（Sonnet 適配）＋品牌數值策略——觀察期**（2026-07-06 上線）：

- ✅ 全鏈完成：R4 設計三視角 review → R5 使用者逐段審定 → 4-4-9 回填機制實驗（錨點精度 0.2%）→ R6 錨點 15 條 TFDA／官方查證 → 實作三視角 review（R7，11 條 findings）→ 兩段式部署 smoke 全過（官方值／定值錨／推估／標示轉錄四情境 note 關鍵字全命中，「50嵐奶茶半糖」歷史原句命中 700cc 預設）。
- ✅ 隨案完成：`meals.note` 落庫（未來 AI 校正係數的 basis 分類依據，forward-only migration 已對 prod 執行）；/f 食物快取 17 項盤點對齊新錨點（更新 4 項：芝麻麻糬、8冰綠、Subway、星巴克）。
- 👀 觀察清單（各項觸發時機與動作見 [docs/prompt-v2-design.md「運行觀察交接」段](https://github.com/huansbox/calorie-bot/blob/main/docs/prompt-v2-design.md)）：
  - note 關鍵字遵守率：上線一週後看 log 的 soft-check warning 與 DB note 前綴分佈，不合規率 >10% 才動作
  - 2026-07-13 週一週報「週對週」攝取跳增屬預期（白飯基準 +18% 等記錄基準台階），不是 bug
  - 天仁鮮奶茶散裝文字輸入變多時，考慮「鮮奶茶 3 分糖 280」錨點下修 ~250
  - 快取備忘：舒跑買到新配方照瓶身更新；amino vital 換吃 Perfect Energy 時建新快取

## 其他 active

| 項目 | 狀態 |
|---|---|
| claude -p 轉正 | 全案完結（2026-07-06 收 `chmod 700 /root` 與首週 watch），歸檔 |
| COROS 體重自動同步 | 已全數驗收（issues 001–008），無 active 工作 |

## 被動觀察

不需主動施工、等時間或事件的項目：

- **weight sync 的告警分支實推**：「值同上次輕提醒」與「跳變 >3kg 告警」的 Telegram 實際推送至今未在 prod 觸發（決策邏輯已有單元測試覆蓋），等真實事件出現時瞄一眼 log。
- **`ai_confidence` 欄位**：Gemini 時代就幾乎不回 low/medium，觀察中，未來可能移除；v2 已重寫 confidence 三級定義，Sonnet 遵守度可順帶觀察。
- **`modelUsage` 缺失邊界**：缺失時 `ai_model=None`、標籤消失，實測一向都有，屬罕見；持續觀察，變常見再加通用標記。
- **VPS 磁碟**：每版 claude binary 約 230 MB，prune 併進每月更新流程，平時不用管。
- **資料量門檻**：滿 2 個月 → 開工月報；`meals.note` 的 basis 分類資料自 2026-07-06 起累積，滿 6-8 週（約 2026-08 下旬）→ 開工 AI 校正係數（見 [Roadmap](Roadmap)）。

## 開工守則

- 開工先讀 repo 的 CLAUDE.md「進行中的設計」與對應 design doc（docs/）；大型功能走 `/grill-me` 對齊 → PRD → issues 拆解流程。
- 功能開發、重構、bug fix 開 feature branch（feat/xxx, fix/xxx, refactor/xxx），Conventional Commits，小步提交。
- 完工回寫 CLAUDE.md（AI 記憶快照，不留歷史），必要時刷新本 wiki 快照頁。
