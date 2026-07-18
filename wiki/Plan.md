# 執行中計畫

> 快照日期：2026-07-18。**Source of truth = repo 內 [CLAUDE.md「進行中的設計」段](https://github.com/huansbox/calorie-bot/blob/main/CLAUDE.md) 與 [issues/](https://github.com/huansbox/calorie-bot/tree/main/issues) 目錄**，
> 本頁為導覽快照，衝突時以 repo 為準。

## 主戰場

**AI provider 品質評估——已定案並部署，觀察期**（2026-07-18）：

- ✅ 全鏈完成：Sonnet 台灣品牌品項知識缺口定錨（奧利多案例，裸探測判定為 model 非 prompt 問題）→ VPS 裝 agy CLI（Antigravity）smoke 4/4 全過 → GCP 抵免額回歸、接回 gemini-api → 模型對照（food_cache 官方值當 ground truth）選定 `gemini-3.1-pro-preview` → 費率更新（$2/$12）→ 全鏈 smoke 過、gemini 路徑補記 `ai_model`（回覆印模型標籤）。
- ✅ 落選記錄：2.5-pro 與 Flash 系因假冒「官方值／標示轉錄」＋confidence high 失格；agy 留在 VPS 作「搜尋官方標示」能力的未來選項。全程見 [docs/agy-cli-exploration.md](https://github.com/huansbox/calorie-bot/blob/main/docs/agy-cli-exploration.md)。
- 👀 觀察清單：
  - note 權威捏造率：3.1-pro 已知 1/8（「維他露奧利多」張冠李戴案）；變常見時考慮機器硬檢（「無圖片＋標示轉錄」為必然捏造，程式可判定）
  - preview 模型異動：`ai_model` 欄位與回覆標籤直接監控 `model_version` 漂移
  - GCP 抵免額消耗：效期至 2027-07，月費 ~US$3 級距，理論上無壓力，偶爾瞄帳單

**Prompt v2 ＋品牌數值策略——觀察期**（2026-07-06 上線；2026-07-18 起主要讀者由 Sonnet 5 改為 gemini-3.1-pro-preview，prompt 不動）：

- ✅ 全鏈完成：R4 設計三視角 review → R5 使用者逐段審定 → 4-4-9 回填機制實驗（錨點精度 0.2%）→ R6 錨點 15 條 TFDA／官方查證 → 實作三視角 review（R7）→ 兩段式部署 smoke 全過。note 關鍵字制度實測跨模型通用，且成為本次模型評選的關鍵指標。
- ✅ 隨案完成：`meals.note` 落庫（未來 AI 校正係數的 basis 分類依據）；/f 食物快取 17 項盤點對齊新錨點。
- 👀 觀察清單（各項觸發時機與動作見 [docs/prompt-v2-design.md「運行觀察交接」段](https://github.com/huansbox/calorie-bot/blob/main/docs/prompt-v2-design.md)；Sonnet 專屬項目適用性已下降）：
  - note 關鍵字遵守率：看 log soft-check warning 與 DB note 前綴分佈，不合規率 >10% 才動作
  - 天仁鮮奶茶散裝文字輸入變多時，考慮「鮮奶茶 3 分糖 280」錨點下修 ~250
  - 快取備忘：舒跑買到新配方照瓶身更新；amino vital 換吃 Perfect Energy 時建新快取

## 其他 active

| 項目 | 狀態 |
|---|---|
| claude -p 路徑 | 2026-07-18 起降為 fallback（Gemini 掛時接手）；每月更新提醒照常（fallback 仍依賴 CLI） |
| agy CLI（Antigravity） | 已裝於 VPS 並完成 smoke，暫不整合；等「搜尋官方標示」需求成熟再評估 |
| COROS 體重自動同步 | 已全數驗收（issues 001–008），無 active 工作 |

## 被動觀察

不需主動施工、等時間或事件的項目：

- **weight sync 的告警分支實推**：「值同上次輕提醒」與「跳變 >3kg 告警」的 Telegram 實際推送至今未在 prod 觸發（決策邏輯已有單元測試覆蓋），等真實事件出現時瞄一眼 log。
- **`ai_confidence` 欄位**：v1 時代 Gemini 2.5 Pro 幾乎不回 low/medium；v2 ＋ 3.1-pro 已見合理分佈（有依據 high、推估 medium、不確定 low），欄位續留觀察。已知失效模式：權威捏造時連帶標 high。
- **`data/media/` 孤兒照片（疑似 bug，待查）**：發現 3–6 月舊照片殘留，疑清理排程只刪 DB 有記錄的檔案，見 [Tech Debt](Tech-Debt)。
- **VPS 磁碟**：每版 claude binary 約 230 MB，prune 併進每月更新流程，平時不用管。
- **資料量門檻**：滿 2 個月 → 開工月報；`meals.note` 的 basis 分類資料自 2026-07-06 起累積，滿 6-8 週（約 2026-08 下旬）→ 開工 AI 校正係數（見 [Roadmap](Roadmap)）。

## 開工守則

- 開工先讀 repo 的 CLAUDE.md「進行中的設計」與對應 design doc（docs/）；大型功能走 `/grill-me` 對齊 → PRD → issues 拆解流程。
- 功能開發、重構、bug fix 開 feature branch（feat/xxx, fix/xxx, refactor/xxx），Conventional Commits，小步提交。
- 完工回寫 CLAUDE.md（AI 記憶快照，不留歷史），必要時刷新本 wiki 快照頁。
