# agy CLI（Antigravity）評估記錄

日期：2026-07-18｜狀態：smoke 全過，觀察期／待決策（gemini-api 抵免額回歸後，接回 API 為首選短路徑，agy 降為搜尋能力選項）

## 動機

Prompt v2 + Sonnet 上線後，台灣在地品牌品項出現判讀品質下降。定錨案例「奧利多水」（金車，585ml 實測 252 kcal、碳水 68.4g）：

- Sonnet 多次抽樣給出 0（當白開水）／104／156／341（當多多綠手搖）／376（當乳酸菌飲料）kcal，發散且全錯
- 裸問 Sonnet 直接承認「對此品牌沒有高把握的記憶」→ **確立為 model 知識缺口，非 prompt v2 問題**
- 附帶發現 prompt 層風險：知識缺口下 Sonnet 會腦補品牌歸屬（黑松／可口可樂）、假冒「標示轉錄：」＋confidence high
- Gemini 系（Google 語料）台灣在地產品覆蓋顯著較好；「Gemini 會查詢」是錯覺——API JSON mode 無 grounding，靠的是訓練記憶

## agy CLI 背景

- Antigravity CLI（binary 名 `agy`）＝ Google 對應 Claude Code 的終端 agent，走 **Google AI Pro/Ultra 訂閱**（非 API 計費）
- gemini-cli 免費層 2026-06-18 起被 agy 取代；`agy -p` 對應 `claude -p` 的 headless 一次性模式
- flags 重點：`--model`（含 thinking level 變體）、`-p/--print`、`--print-timeout`（預設 5m）、`--dangerously-skip-permissions`、`--sandbox`；**無 JSON envelope 輸出、無 system prompt 注入 flag**（system prompt 只能併入 -p 內文）
- 模型清單（AI Pro 方案實測）：Gemini 3.5 Flash (Low/Medium/High)、Gemini 3.1 Pro (Low/High)、Claude Sonnet/Opus 4.6、GPT-OSS 120B。括號＝thinking level（同權重、同知識，只差推理預算），對應 Claude 的 effort

## VPS 安裝記錄（2026-07-18）

```bash
# 以 botuser 安裝，binary 落 /home/botuser/.local/bin/agy（v1.1.4）
curl -fsSL https://antigravity.google/cli/install.sh | bash
```

- OAuth：`ssh -t` 進互動 TUI，偵測 SSH session 印授權 URL → 本地瀏覽器登入（Google AI Pro 帳號）→ 貼授權碼。憑證落 `~/.gemini/antigravity-cli/antigravity-oauth-token`（檔案，600，重開機不掉）
- Trusted workspace：`/home/botuser`（首次進 TUI 時核可）
- 設定檔：`~/.gemini/antigravity-cli/settings.json`。**權限 grant 語法**（試錯代價高，記錄）：
  - 格式 `tool(target)`，target 為**目錄路徑＝涵蓋整個子樹**，萬用字元是 `*`；glob `**` 無效（載入成功但比對不中）；裸工具名（`"read_file"`）非法直接被忽略；優先序 Deny > Ask > Allow
  - 現行規則：`"read_file(/home/botuser/calorie-bot/data/media)"`（headless 圖片分析所需，範圍鎖 media 目錄，避免 `--dangerously-skip-permissions` 全開）
  - headless 模式下未命中 allow 的工具請求一律 soft-deny（log 關鍵字 `Print mode: soft-denying tool confirmation`）；搜尋類工具例外，自動放行
- smoke 腳本遺留：`/home/botuser/agy-smoke.sh`（probe/replay/image/search 四模式，`AGYMODEL` 環境變數切模型）＋ `/home/botuser/agy-smoke/sysprompt.txt`（從 services/ai.py 抽出的 SYSTEM_PROMPT）

## Smoke 結果（4/4 過）

| 項目 | 結果 |
|---|---|
| 品牌知識 | Gemini 3.1 Pro (Low) 一發答對「金車、寡醣微碳酸飲料」（Sonnet 全不認得） |
| JSON 純淨度 | production prompt 重放 9/9 乾淨 JSON、零 agent 前導文字、note 全數「推估：」開頭、正確預設 585ml 規格、confidence 全 medium（誠實） |
| 配額 | 單日累計 16 發（Pro 13＋Flash 3）零錯誤；長期行為未驗證（與個人 AI Pro 用量共池、政策 2026 一路在變） |
| 圖片 | `@檔案` 語法＋read_file allow 規則後成功（丸亀製麵照片正確辨識），16.8s |

延遲：文字 7-19s、圖片 ~17s、含搜尋 ~21s，皆在 bot timeout 60s 內。

### 數值精度（誠實記錄）

Pro 重放 9 次：6 次 ~130-140 kcal（真值一半）、3 次命中標示口徑（碳水 58.5-64.3g ≈ 234-257 kcal）。**認得品牌 ≠ 記得標示**，記憶檢索不穩定；重複品項的正解仍是 food_cache。

### 模型對照：不用 Flash

Flash (Low/Medium) 品牌知識同樣在、快 3-6 倍（2.5-3.8s），但重放一發即**捏造「官方值：金車官方標示每100ml熱量18kcal」＋confidence high**（真值 44）。note 前綴誠實分層是校正係數設計的地基，Flash 校準差、不可用。定調 **Gemini 3.1 Pro (Low)**。

### Web search 鑑別（-p 模式有即時網路）

- 決定性證據：問 python-telegram-bot 最新 release，答 `v22.8、2026-06-12T08:11:08Z`，與 `gh api` 真值**秒級一致**——只能來自即時存取
- 奧利多搜尋探測拿回正解：44 kcal/100ml、碳水 11.7g（與手動記錄分毫不差）
- **預設不搜**（9 次重放全走記憶），prompt 明示才觸發 → 「品牌品項路由到搜尋」是整合時的 prompt 設計決策點
- 「出處」會唬爛（給首頁級 URL 充數）：數值可信、引用不可信
- 注意：問 agy 自身版本號的測試被污染（版本資訊在其 context 內），不可作為搜尋證據

## 若轉正的整合設計點（未實作）

1. **token 追蹤斷線**：無 JSON envelope → 拿不到 token 用量與實際模型名。現行「input_tokens=0 區分 AI vs 手動」慣例會被打破，需改以 ai_provider 判別
2. **ai_model 稽核降級**：只能寫死傳入的 `--model` 值，無法從輸出驗證實際模型（claude-cli 的 modelUsage 稽核鏈做不到）
3. timeout 對齊：`--print-timeout`（預設 5m）與 bot 端 60s 的關係
4. 搜尋路由：SYSTEM_PROMPT agy 版是否指示品牌包裝品項查官方標示（能力上限 vs 延遲/配額/穩定性，需觀察「搜尋版 prompt 能否穩定命中官方標示」）

## 決策現況（2026-07-18）

GCP 抵免額回歸（Google Developer Program premium benefit，$319×2＋$315，效期至 2027-07；前一筆 $314 於 2026 年初用罄——這正是「gemini-api 從免費變收費」的原因）。gemini-api 月費 ~US$2.5（719 筆歷史實測：均 in 579／out 82／thinking 1113 tokens）完全被覆蓋。

→ **接回 gemini-api（`AI_PROVIDER=gemini`，model 寫死 `gemini-2.5-pro` @ services/ai.py，3 週前仍驗證可用）為首選短路徑**：零整合、JSON schema 強制輸出、token/model 追蹤完整、自帶 fallback 鏈（Gemini 掛 → claude -p）。agy 續留 VPS 作為「搜尋能力」的未來選項。模型升 Gemini 3.x API 另案評估。

### 2026-07-18 切換後續：billing 阻塞（待使用者處理）

`AI_PROVIDER=gemini` 已切換並重啟，但實測 API key 所在 GCP 專案目前為 **free tier，pro 系模型配額為 0**（429 `free_tier_requests, limit: 0`，2.5-pro 與 3.1-pro 皆擋）——新抵免額所在的 billing account 未連結（或已解除連結）該專案。**待辦：使用者在 Cloud Console 將 API key 所屬專案連上持有抵免額的 billing account**。期間 fallback 鏈已實測接手（gemini 429 → claude -p，每餐多 ~1-2s 與一行 warning log），行為等同 claude-cli-only；billing 接上後 gemini-2.5-pro 即自動生效，無需再部署。

多模型對照初步結果：`gemini-pro-latest` 別名實際解析到 `gemini-3.1-pro`（production 勿用別名，鎖定明確版本）；`gemini-3.5-flash`（free tier 可跑）兩發皆捏造官方權威（「標示轉錄：金車官網 28kcal/100ml」「官方值：6.7g/100ml」＋confidence high，真值 44 kcal/11.7g）——與 agy 側 Flash 同病，**不可用**。2.5-pro vs 3.1-pro-preview 對照待 billing 修復後補測（腳本留存 VPS `/tmp/gemini_model_test.py`）。

## 順帶發現（與本案無關，待查）

`data/media/` 存有 2026 年 3／5／6 月舊照片，而設計為 24h 過期＋03:00 排程清理——疑似清理只刪 DB 有記錄的檔案，分析失敗等路徑產生的孤兒檔案永久殘留。
