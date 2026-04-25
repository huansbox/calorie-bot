# claude-cli 模型追蹤設計

## 為什麼（rationale）

- **2026-04-09 事件背景**：API key 從 `.env` 洩漏到 subprocess 環境，導致 `claude -p` fallback 走 API 計費（Sonnet）而非預期的 Max 訂閱（Opus）。事後從帳單金額才察覺，DB 沒有任何能反查的軌跡。
- **既有風險**：
  - Claude Code CLI 可能因版本升級悄悄切換預設模型
  - 環境變數污染（ANTHROPIC_API_KEY、CLAUDE_CODE_USE_BEDROCK 等）會改變實際呼叫端點
  - `claude-cli` 在 meals 表只記為單一字串，無法區分不同模型
- **防禦目的**：在 meals 留下「這筆食物分析實際使用哪個模型」的稽核軌跡，未來計費異常 / 結果品質異動時可從 DB 直接反查，不需翻 systemd journal。
- **附加效益**：週報 API 費用統計可從「假設 claude-cli 一律 $0」進化到「實際根據 modelUsage.costUSD 加總」，更貼近真實成本（Max 訂閱有月費上限，超量會回退到 API 計費）。

## 核心機制

### 模型名稱來源比較

| 來源 | 取得方式 | 優點 | 缺點 |
|------|----------|------|------|
| **A. stdout JSON `modelUsage` 欄位** | 解析現有 `--output-format json` 的 envelope | 零成本、零新依賴、已存在於每次回應 | key 名稱包含 `[1m]` 等變體後綴需正規化 |
| B. CLI flag | 預期 `claude --print-model` 之類 | 顯式 | **不存在**（已查 `claude -p --help`） |
| C. stderr 解析 | grep stderr 訊息 | 可在 verbose 下取得 | 格式不穩定、需開 `--verbose`、增加 noise |
| D. 端點查詢 | OAuth subscription API 反查 | 最權威 | 無公開 API、需另起認證流程、過度工程 |
| E. `--debug` 輸出解析 | `claude -p --debug api` | 含完整 request 細節 | 輸出量爆炸、影響 timeout、噪音極大 |

### 推薦方案：A（stdout JSON `modelUsage` 解析）

實測 `claude -p "..." --output-format json` 回傳的 envelope 已包含：

```json
{
  "result": "...",
  "usage": { "input_tokens": 6, "output_tokens": 10, ... },
  "modelUsage": {
    "claude-opus-4-7[1m]": {
      "inputTokens": 6,
      "outputTokens": 10,
      "costUSD": 0.1157815,
      ...
    }
  },
  "total_cost_usd": 0.1157815
}
```

**選 A 的理由**：
1. 已經在每次回應裡，**改動 = 多 parse 一個欄位**，零新依賴零新 subprocess
2. `modelUsage` 是 dict，天然支援「同一次呼叫跨多模型」的場景（雖然食物分析不會發生）
3. `total_cost_usd` 順便可解決週報實際費用追蹤
4. 失敗模式單純：欄位缺失就記 null，不阻斷主流程

## 完整流程

```
使用者送食物 / 照片
       ↓
handlers/meal._process_food
       ↓
services/ai.analyze_food
       ↓ (Gemini 失敗)
services/ai._analyze_claude_cli
  ├── subprocess 呼叫 claude -p --output-format json
  ├── json.loads(stdout)
  ├── 解析 result（既有）
  ├── 解析 usage（既有）
  └── 【新】解析 modelUsage → 取第一個 key 作為 ai_model
       ↓
FoodAnalysis(provider="claude-cli", ai_model="claude-opus-4-7", ...)
       ↓
handlers/meal 將 result.ai_model 傳給 insert_meal
       ↓
services/db.insert_meal 寫入 meals 表 ai_model 欄位
```

### 失敗 fallback

| 情境 | 行為 |
|------|------|
| `modelUsage` 欄位缺失（CLI 升級格式變更） | `ai_model = None`，logger.warning 記錄一次 | 
| `modelUsage` 是空 dict | 同上 |
| `modelUsage` 有多個 key（理論上不會發生於單次 prompt） | 取 cost 最高者，logger.info 提醒 |
| 解析整個 envelope 失敗 | 既有錯誤路徑，整筆呼叫已 raise |

**原則**：模型名稱屬於「稽核資料」而非「核心業務資料」，取不到就記 null，不影響使用者記錄食物。

### 模型名稱正規化

CLI 回傳 key 形如 `claude-opus-4-7[1m]`（後綴是 context window 變體）。建議：

- **正規化策略**：去除 `[...]` 後綴，存 `claude-opus-4-7`
- 若日後需要區分 1m vs 200k context，再加欄位 `ai_model_variant`
- 寫一個 `_normalize_model_name(raw: str) -> str` 函式，附單元測試

## 實作骨架

### 1. DB Migration

**新增欄位**（不要塞進 `ai_provider`，分開存方便 query）：

```sql
ALTER TABLE meals ADD COLUMN ai_model TEXT;
-- 歷史資料留 NULL，意義為「未知」（claude-api 那段也沒記過）
```

不需 backfill。`ai_provider` 維持 `gemini` / `claude-cli` / `claude-api` 不變。

**為什麼分欄位而非塞 `ai_provider`**：
- `ai_provider` 已被週報 group by 使用，混入模型名稱會破壞既有查詢
- DB 角度：provider 是「呼叫管道」，model 是「實際模型」，正交概念
- 未來 Gemini 也可能要記 model（gemini-2.5-pro vs gemini-2.5-flash）—— 統一架構

### 2. `services/ai.py` 改動點

**FoodAnalysis dataclass（line 64-76）**：
```python
@dataclass
class FoodAnalysis:
    ...
    provider: str = ""
    ai_model: str | None = None   # 新增
```

**`_analyze_claude_cli`（line 266-318）**，在 line 314 附近：
```python
usage = output.get("usage", {})
result.input_tokens = usage.get("input_tokens", 0) or 0
result.output_tokens = usage.get("output_tokens", 0) or 0
result.provider = "claude-cli"
# 新增：
model_usage = output.get("modelUsage", {})
if model_usage:
    raw_model = next(iter(model_usage.keys()))
    result.ai_model = _normalize_model_name(raw_model)
else:
    logger.warning("claude -p 回傳缺少 modelUsage 欄位")
```

**新增 helper 函式**（檔案尾部或 `_analyze_claude_cli` 上方）：
```python
def _normalize_model_name(raw: str) -> str:
    """去除 context window 變體後綴。e.g. 'claude-opus-4-7[1m]' -> 'claude-opus-4-7'"""
    import re
    return re.sub(r"\[.*?\]$", "", raw).strip()
```

**`_analyze_claude`（line 247-260）**：可選同步改動，將 `result.ai_model = "claude-sonnet-4-6"`（從 `response.model` 讀）

**`_analyze_gemini`（line 162-206）**：可選，`result.ai_model = "gemini-2.5-pro"`（hardcode 即可，未來換型號時改一處）

### 3. `handlers/meal.py` 改動點

`_process_food`（line 87-103，`insert_meal` 呼叫）加一行：
```python
row = insert_meal(
    ...
    ai_provider=result.provider,
    ai_model=result.ai_model,   # 新增
)
```

### 4. `services/db.py` 改動點

`insert_meal`（line 15-56）：
- 新增參數 `ai_model: str | None = None`
- 在組 row 處（line 50 附近）：
  ```python
  if ai_model is not None:
      row["ai_model"] = ai_model
  ```

### 5. 其他補充修改點

- `handlers/manual_meal.py`、`handlers/backfill.py`、`handlers/food_cache.py`：手動記錄 / cache 路徑不傳 `ai_model`（=NULL，正確語意）
- `tests/test_ai.py`：新增 `_normalize_model_name` 單元測試（3-4 個 case）
- `CLAUDE.md`：在「ai_provider 追蹤」段落附近加一行 `ai_model` 說明

### 6. 部署順序

1. Supabase 後台或 SQL editor 執行 ALTER TABLE
2. PR 合併到 main
3. VPS pull + restart
4. 觀察一週，確認 meals 表 `ai_model` 欄位有正確填入

## 尚待決定的細節

### 設計層面
1. **Gemini / Claude API 路徑要不要同步記 `ai_model`？**
   - 對：架構一致、未來換 model 可從 DB 找出影響範圍
   - 反：Gemini 一直是 hardcode `gemini-2.5-pro`，記了等於 redundant
   - 建議：先只做 claude-cli（解 TODO），Gemini/Claude API 留下次需要時再加（YAGNI）

2. **是否同步記 `total_cost_usd`？**
   - CLI envelope 已給。週報目前 claude-cli 顯示 $0，若記了就能顯示真實成本（雖然 Max 訂閱實際自付為 0）
   - 建議：加一個 `ai_cost_usd numeric` 欄位，weekly_token_usage 改用實際值。額外工作但價值高
   - 開放問題：跟此 TODO 是同個 PR 還是分開？

3. **是否警報 `ai_model != 'claude-opus-4-7'`？**
   - 既然防禦目的是「察覺異常」，被動記錄不夠主動
   - 進階做法：`_analyze_claude_cli` 中若 model 不符預期，logger.error 並在 Telegram 回覆加標籤
   - 建議：先被動記錄一週，看 CLI 是否會自然切換 model；若會則加白名單；若不會就維持被動

### 實作層面
4. **正規化函式要不要存原始 key？** 加 `ai_model_raw` 欄位 vs 只存正規化版本。建議先只存正規化，DRY 起見。
5. **歷史資料要不要 backfill `ai_provider='claude-cli'` 的列？** 不行，因為當時沒記，無法事後得知。維持 NULL。
6. **TDD 還是先實作再加測試？** `_normalize_model_name` 是純函式，TDD 適合；subprocess 解析難測試（要 mock）建議用 integration test 在 staging 跑一次驗證。

## 重新檢視必要性

**結論：值得做，但範圍小。**

- 核心改動小（新增 1 欄位 + 解析 1 個 dict key + 正規化函式），預估 1-2 小時含測試
- 帶來明確稽核能力，2026-04-09 同類事件可在 5 分鐘內定位
- CLI 已主動暴露 `modelUsage`，等於官方支援這個用例，未來 schema 穩定性可期
- **不必做的版本**：若僅依賴 systemd journal 也能事後翻查（claude -p 的 stdout 進 log），但需維持 log retention 策略；DB 方式更可靠且可以做統計

**綜合判斷**：建議實作，採方案 A，以「只記 ai_model，暫不記 cost」的最小範圍切第一個 PR，cost 追蹤留作獨立 follow-up。
