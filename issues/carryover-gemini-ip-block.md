# Carry-over：Gemini 主路徑被 Google 依 client IP 封鎖，路線未定

**這不是已規格化的任務。** 三個選項尚未決定，實作前先跑 `/grill-me` 對齊範圍；由該流程產出的 issue 應關閉或取代本項。

不屬於 `issues/prd.md`（COROS 體重同步）那條編號序列。

## 事實（2026-09-06 建立）

2026-09-04 01:52 UTC 起，VPS 對 `generativelanguage.googleapis.com` 的**所有**請求回：

```
400 FAILED_PRECONDITION
User location is not supported for the API use.
```

連 `GET /v1beta/models`（不帶模型、不做推論）都是同一個 400 → 錯在 IP 層，不在請求內容。

已排除的假設：

- **key / 專案 / 模型**：同一把 key 從台灣家用網路打 `gemini-3.1-pro-preview:generateContent` 回 200 並正常計 token
- **free tier / 抵免額 / billing**：官方 pricing 頁 free tier 對 3.1 Pro Preview 標 "Not available"，而台灣打得通 → 專案仍在 paid tier。且官方條款中唯一的 tier×地理差異是 EEA/CH/UK，與 US 無關；付費 tier 案例（OVH Montreal、InterServer NJ、Render Frankfurt）同樣被擋
- **地理資料庫查不到**：VPS 上抓 YouTube ytcfg 回 `"GL":"US"`，Google 主要 geo 認得這個 IP 是美國

外部脈絡：Google 官方論壇自 2026-08-18 起有橫跨 OVH / Linode / Akamai / InterServer / Render / ColoCrossing 的同類災情，Google staff 於 8/26 與 9/2 兩度公開承認並發除錯表單，至今無根因說明與修復時程。**查無任何自行恢復的結案案例**（唯一「解決」的是 IPv6 段誤判改走 IPv4，本 VPS 為純 IPv4，不適用）。

目前影響：`AI_PROVIDER=gemini` 每餐先打一次必失敗的請求（~200ms），fallback `claude -p`（Sonnet 5）正常承接，**服務未中斷**。主路徑失敗告警已於 `7d5ac16` 上線，狀態轉換時各推一則 Telegram。

## 為什麼停在這裡

三個選項待使用者決定，各自需要使用者先動手（開 ticket 或建 GCP 憑證）：

1. **跟 RackNerd 換 IP**——成本最低，成功的話零改動零維護增量；但 ColoCrossing 整個 AS 的 reputation 不佳，需爭取換不同 prefix
2. **改走 Vertex AI**——官方文件逐字寫「You can use the API from any location in the world」，且 Gemini API 支援地區頁對被擋者的官方指引就是改用 Vertex；**但無實測**（從被擋 IP 打 Vertex 是 401 UNAUTHENTICATED，認證擋在地區檢查之前，測不出來），也查無他人的對照實驗。要確認須建 service account 用 OAuth token 實打一次
3. **先觀察 Sonnet 品質兩週**——9/4–9/5 共 15 筆判讀的 note 品質實測：權威捏造 0/15、定值錨與品類校準區間命中、confidence 分佈合理；代價是品牌品項全部走推估、放棄官方值那一層

## 下一個 session 從哪裡開始

使用者決定路線。若選 2，第一步是建 service account + `roles/aiplatform.user`，從 VPS 用 OAuth token 打
`us-central1-aiplatform.googleapis.com/.../gemini-3.1-pro-preview:generateContent`，回 200 才動 `services/ai.py`。

相關脈絡見 `docs/agy-cli-exploration.md` 與 `CLAUDE.md`「AI 路由」段。
