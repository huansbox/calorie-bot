# Telegram + AI + Obsidian 個人助理：可行性評估

> 調研日期：2026-03-25

---

## 一、GitHub 開源專案調研

### 1. [smixs/agent-second-brain](https://github.com/smixs/agent-second-brain) ⭐ 最高匹配度

- **架構**：Telegram → Deepgram（語音轉文字）→ Claude Code (`claude -p`) → Todoist + Obsidian vault → Telegram 回報
- **技術棧**：Python、Claude Code + OpenClaw、Obsidian vault、Todoist API
- **特色**：
  - 語音優先輸入，支援文字/照片/轉發訊息
  - Ebbinghaus 遺忘曲線記憶衰減、vault 健康評分、知識圖譜
  - 每月約 $5（VPS 費用），使用 Claude Max 訂閱額度
  - 每日自動報告推播
- **匹配度**：**極高** — 幾乎完全覆蓋你的需求（Telegram 輸入 → AI 理解 → Obsidian 寫入 → 定時推播）
- **可借鑑**：整體架構、vault 結構設計、`claude -p` 整合模式、OpenClaw 作為 Telegram 中介

### 2. [albinotonnina/echos](https://github.com/albinotonnina/echos)

- **架構**：Telegram 語音/文字 → AI 轉寫分類 → 本地知識庫
- **技術棧**：自架、私有部署
- **特色**：「打開 Telegram 說出來，30 秒後就在知識庫裡 — 轉寫、分類、標籤、可搜尋」
- **匹配度**：**高** — 理念一致，個人知識捕捉工具
- **可借鑑**：快速捕捉的 UX 流程

### 3. [clsandoval/monorepo](https://github.com/clsandoval/monorepo) ⭐ 最有野心

- **架構**：Life OS — 1,034 實體知識圖譜、Always-on Telegram bot、自動 git commit、CI 驅動的自主研究迴圈
- **技術棧**：TypeScript、Claude Agent SDK、MCP server、Dataview dashboard
- **特色**：
  - Telegram bot 從訊息中擷取實體，自動提交到 git
  - 4 個自主研究迴圈在 GitHub Actions 上以 cron 運行
  - 8 個 Dataview dashboard 查詢人物/地點/行程/專案
- **匹配度**：**中高** — 功能遠超你的需求，但架構思路值得參考
- **可借鑑**：知識圖譜結構、實體擷取、CI 驅動的自動化

### 4. [IslamTayeb/clawd-bot-setup](https://github.com/IslamTayeb/clawd-bot-setup)

- **架構**：Telegram Claude assistant for Obsidian
- **技術棧**：Python
- **匹配度**：**高** — 名稱直接描述你的需求
- **可借鑑**：小型專案，適合快速參考實作方式

### 5. [may-cat/obsidigram](https://github.com/may-cat/obsidigram)

- **架構**：Obsidian plugin — Telegram bot → OpenAI API → 智慧合併到現有筆記
- **技術棧**：TypeScript（Obsidian plugin）、OpenAI compatible API
- **特色**：
  - AI 驅動的筆記合併（非簡單 append，而是理解內容後合併）
  - 智慧檔名生成、可自訂 prompt
  - 已提交 Obsidian 社群 plugin
- **匹配度**：**中** — 是 Obsidian plugin 而非獨立 bot，需要 Obsidian 運行
- **可借鑑**：AI 合併筆記的 prompt 設計

### 6. [dimonier/tg2obsidian](https://github.com/dimonier/tg2obsidian) (145 ⭐)

- **架構**：從 Telegram chat/group 拉取訊息寫入 Obsidian vault
- **技術棧**：Python、支援 OCR 與 TTS
- **匹配度**：**低** — 純轉存，無 AI 理解層
- **可借鑑**：Telegram → Markdown 轉換的成熟實作

### 7. 其他值得注意的工具

| 專案 | 說明 |
|------|------|
| [cyanheads/obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server) (416 ⭐) | Obsidian MCP server — AI agent 透過 MCP 讀寫 vault |
| [Enigmora/claudian](https://github.com/Enigmora/claudian) | Obsidian plugin — Claude AI 直接管理 vault |
| [RichardAtCT/claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram) | Telegram bot 遠端存取 Claude Code |
| [seedprod/claude-code-telegram](https://github.com/seedprod/claude-code-telegram) | 雙向 Telegram ↔ Claude Code |
| [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | Obsidian 官方的 Agent Skills |

---

## 二、`claude -p` vs API 直接呼叫

### 對比分析

| 面向 | `claude -p`（CLI pipe mode） | Anthropic API 直接呼叫 |
|------|------|------|
| **延遲** | 高 — CLI 啟動開銷 + agent loop 多輪對話 + tool use 迴圈，單次可能 5-30 秒 | 低 — 直接 HTTP 呼叫，單次 1-5 秒 |
| **Rate Limit** | 受 Max 訂閱的 5 小時 rolling session + 每週配額限制，與 claude.ai 共用 | 取決於 API tier，可控且可擴展 |
| **穩定性** | 中 — 曾有 subprocess 掛住的 bug（已修），但本質上是啟動一個完整的 agent | 高 — 成熟的 HTTP API，失敗模式可預測 |
| **可控性** | 低 — Claude Code 自主決定 tool 使用、多輪推理，行為不完全可預測 | 高 — 你完全控制 prompt、tool definition、回應解析 |
| **上下文管理** | 自動 — Claude Code 管理對話歷史，可能膨脹 | 手動 — 你決定送什麼進去 |
| **成本** | 免費（Max 訂閱內） | $3/M input + $15/M output（Sonnet），約 $25-40/月中度使用 |
| **Filesystem 操作** | 內建 — Read/Write/Edit/Glob/Grep 全套 | 需自己寫 — 但 Obsidian vault 就是 Markdown 檔案，邏輯不複雜 |

### 結論：**建議 API 直接呼叫（路線 B）**

理由：
1. **延遲是致命問題**：Telegram 使用者期待秒級回覆，`claude -p` 的 agent loop 動輒 10+ 秒，體驗差
2. **可控性**：Bot 場景需要確定性行為（分類意圖 → 執行動作 → 回覆），不需要 agent 自主探索
3. **Rate limit 衝突**：你的 Max 訂閱同時要給 claude.ai 和 calobot 開發用，再加一個 always-on bot 會快速耗盡配額
4. **成本可控**：個人助理的對話量不大，API 每月可能只需 $5-15
5. **`claude -p` 仍有價值**：保留作為「深度任務」的備選（例如每日 vault 整理、週報生成），這類任務可接受較長延遲

### 混合架構建議

```
Telegram 訊息 → Python Bot → Anthropic API (Haiku/Sonnet)
                                ↓
                    意圖分類 + 結構化輸出
                                ↓
                    Python 檔案操作邏輯 → Obsidian vault
                                ↓
                    （選用）每日排程觸發 claude -p 做 vault 深度整理
```

- **即時互動**：API 直呼（Haiku 做分類，Sonnet 做複雜理解），自己寫檔案操作
- **批次任務**：可選用 `claude -p` 做每日 vault 健檢 / 重組 / 摘要，這類任務延遲可接受

---

## 三、AI 讀寫 Obsidian Vault 的實作方式

### API 路線需自己實作的邏輯

Obsidian vault 本質是**一堆 Markdown 檔案 + 資料夾結構**，操作並不複雜：

```python
# 核心操作清單
1. 建立筆記      → Path 決定 + 寫入 .md 檔（含 frontmatter）
2. 追加內容      → 讀取現有檔 → 找到合適插入點 → 寫回
3. 搜尋筆記      → 遍歷 .md 檔 + 全文搜尋（或建 index）
4. 讀取筆記      → 讀檔 + 解析 frontmatter/content
5. 列出結構      → os.walk / glob
6. 更新 metadata → 修改 frontmatter YAML
```

**工作量估計**：約 200-400 行 Python，不需要 Obsidian API — 直接操作檔案系統即可。

### Vault 結構設計考量

參考 agent-second-brain 和 Kagantic-vault-structure 的設計：

```
vault/
├── CLAUDE.md              # AI 操作規範（vault 結構、命名規則、標籤系統）
├── 00-Inbox/              # AI 初始寫入區，待整理
├── 01-Projects/           # 進行中專案
├── 02-Areas/              # 持續關注領域（健康、財務、學習...）
├── 03-Resources/          # 參考資料
├── 04-Archive/            # 歸檔
├── 05-Daily/              # 每日筆記
│   └── 2026-03-25.md
├── 06-Tasks/              # 待辦事項
└── templates/             # 筆記模板
```

**關鍵設計**：
- `CLAUDE.md`（或等效機制）作為 AI 的操作手冊，定義 vault 規則
- Frontmatter 標準化：每篇筆記帶 `tags`, `created`, `source: telegram` 等 metadata
- Inbox 模式：AI 不確定分類時先放 Inbox，每日整理排程再處理
- 使用 `[[wikilink]]` 建立筆記間連結，讓 Obsidian graph view 有用

---

## 四、同一台 VPS 跑多個 Bot 的隔離性

### 風險評估

| 風險 | 嚴重度 | 說明 |
|------|--------|------|
| 資源競爭 | 低 | Telegram bot polling 極輕量，兩個 bot 加起來 RAM < 200MB |
| Port 衝突 | 無 | 兩個 bot 都用 polling 模式，不監聽 port |
| 檔案系統衝突 | 無 | 完全不同目錄 |
| 程序互相影響 | 低 | 一個 bot crash 不影響另一個 |
| 密鑰管理 | 低 | 1Password Service Account 可為不同 bot 設不同 vault |

### 建議方案

```
/home/botuser/calorie-bot/     # 既有 calobot
/home/botuser/obsidian-bot/    # 新 bot
/home/botuser/vault/           # Obsidian vault（新 bot 讀寫）

# systemd service 各自獨立
calorie-bot.service            # 既有
obsidian-bot.service           # 新增
```

**結論**：**風險極低，直接共存即可**。兩個 polling bot 的資源消耗微乎其微，不需要 Docker 或其他隔離機制。你的 calobot 架構已經驗證了 systemd + `op run` 的模式，新 bot 照搬即可。

---

## 五、Obsidian Vault 同步

### 方案比較

| 方案 | 即時性 | 複雜度 | 衝突處理 | 備註 |
|------|--------|--------|----------|------|
| **Git（推薦）** | 手動/排程 | 低 | Git merge | VPS 為 origin，Mac 用 obsidian-git plugin |
| **Syncthing** | 即時 | 中 | 檔案級覆蓋 | VPS 跑 Syncthing daemon，Mac/手機安裝 client |
| **Obsidian Sync** | 即時 | 最低 | 內建 | $4/月，但 VPS headless 需要 Obsidian Headless（2026-02 釋出）|
| **CouchDB + LiveSync** | 即時 | 中高 | 內建 | 自架 CouchDB，功能最完整 |

### 推薦：Git 為主，Syncthing 為選配

**理由**：

1. **Git 天然適合 AI 工作流**：
   - 每次 AI 寫入後自動 `git commit`，完整歷史可追溯
   - 出問題可 `git revert`，安全網極好
   - Mac 端用 [obsidian-git](https://github.com/Vinzent03/obsidian-git) plugin 自動 pull/push
   - 手機端：iOS 用 Working Copy + Obsidian，Android 用 Termux + Git

2. **衝突風險評估**：
   - **實際上很低** — 你透過 Telegram 輸入，AI 在 VPS 寫入，Mac/手機主要是讀取
   - 真正的雙向編輯場景少（你不太會同時在 Obsidian 桌面版和 Telegram 編輯同一篇筆記）
   - 即使衝突，Git merge 處理 Markdown 很可靠

3. **同步流程**：
   ```
   VPS (AI 寫入) → git push → GitHub (private repo) → obsidian-git pull → Mac/手機
   Mac 手動編輯 → obsidian-git push → GitHub → VPS cron git pull
   ```

4. **如果需要更即時**：加裝 Syncthing，VPS 和 Mac 間直接 P2P 同步，繞過 GitHub

---

## 六、總結與建議

### 建議架構路線

```
┌──────────┐     ┌──────────────────┐     ┌──────────────┐
│ Telegram │────→│  Python Bot      │────→│ Obsidian     │
│ (輸入)   │←────│  (python-telegram │←────│ Vault        │
│          │     │   -bot v22)      │     │ (Markdown)   │
└──────────┘     └────────┬─────────┘     └──────────────┘
                          │                       ↑
                 ┌────────┴─────────┐    ┌────────┴───────┐
                 │ Anthropic API    │    │ Git Sync       │
                 │ Haiku: 意圖分類  │    │ → GitHub       │
                 │ Sonnet: 複雜理解 │    │ → Mac/手機     │
                 └──────────────────┘    └────────────────┘
```

### 主要風險

1. **AI 寫入品質**：AI 可能把筆記放錯位置或格式不一致 → 需要嚴格的 CLAUDE.md 規範 + Inbox 緩衝
2. **Prompt 工程量**：意圖分類（待辦 vs 筆記 vs 查詢 vs 提醒）需要反覆調教
3. **Vault 膨脹**：長期使用後搜尋效能 → 可考慮建立簡單索引或用 frontmatter tag 過濾
4. **API 成本漂移**：若未來加入語音轉文字（Whisper/Deepgram）會增加成本

### 開工前需先決定的事項

1. **Vault 結構**：先在 Mac 上建好 vault 骨架（資料夾、模板、CLAUDE.md），再搬到 VPS
2. **意圖分類清單**：明確定義 bot 要處理的訊息類型（待辦、筆記、提醒、查詢、...），每種對應什麼 vault 操作
3. **同步方案確認**：Git（推薦先用這個）還是 Syncthing
4. **API 模型選擇**：分類用 Haiku（便宜快速）還是全部用 Sonnet（簡單但貴一點）
5. **是否整合 Todoist**：agent-second-brain 的 Todoist 整合看起來很實用，但增加複雜度
6. **新 repo 還是 monorepo**：建議新開 repo，架構可以參考 calobot 但獨立管理

### 最終結論

**完全可行，而且有大量現成參考。** agent-second-brain 已經驗證了整條路線。建議：

- 採用 **API 直呼路線（路線 B）**，獲得低延遲 + 高可控性
- 技術棧沿用 calobot 的 **Python + python-telegram-bot + systemd**，降低學習成本
- 同步用 **Git**，VPS 為 source of truth
- MVP 先做三件事：**記筆記、記待辦、查詢 vault 內容**
- 排程推播（每日摘要、待辦提醒）在 MVP 之後用 APScheduler 加入

---

## 參考連結

- [smixs/agent-second-brain](https://github.com/smixs/agent-second-brain) — 最接近的完整實作
- [albinotonnina/echos](https://github.com/albinotonnina/echos) — Telegram 知識捕捉系統
- [clsandoval/monorepo](https://github.com/clsandoval/monorepo) — Life OS 知識圖譜架構
- [may-cat/obsidigram](https://github.com/may-cat/obsidigram) — Obsidian plugin 做 AI 筆記合併
- [cyanheads/obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server) — Obsidian MCP server
- [Vinzent03/obsidian-git](https://github.com/Vinzent03/obsidian-git) — Obsidian Git 同步 plugin
- [Anthropic Rate Limits](https://platform.claude.com/docs/en/api/rate-limits) — API 限制文件
- [Claude Code Rate Limits](https://www.truefoundry.com/blog/claude-code-limits-explained) — CLI 限制說明
- [Obsidian Vault Git Sync for AI](https://docs.bswen.com/blog/2026-03-23-sync-obsidian-vault-git-ai-collaboration/) — Git 同步最佳實踐
