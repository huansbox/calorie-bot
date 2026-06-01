## Parent PRD

`issues/prd.md`

## What to build

在 `services/coros_mcp.py` 新增從 COROS 抓取當前 profile 體重的能力，對應 PRD「COROS 抓取與解析」節。

- `fetch_user_info(token)`：呼叫 MCP `queryUserInfo` tool（無參數），回傳純文字。比照現有 `fetch_daily_health`，但**走 `load→fetch` 路徑、不做 refresh**。
- **實作陷阱（US 22）**：**不可複用 `fetch_and_persist`**（coros_mcp.py 中它把 refresh + save + fetch 綁死，會違反「體重同步不 refresh」的要求）。抓取路徑只 `load_token → fetch_user_info`。
- `parse_user_weight(text)`：純函式，從 `queryUserInfo` 輸出解出體重 float，解析不到回 None。
- 單元測試覆蓋 parse。

已實測 `queryUserInfo` 真實回傳格式（本 session 實際呼叫驗證）：

```
User Profile Information
========================

Height: 170.0 cm
Weight: 70.7 kg
Birthday: 1986-10-02 (Age: 39)
Gender: Male
Nickname: LinShuHuan
```

parser 依此格式撰寫；部署後第一天看 VPS log 確認與 production token 回傳一致。

## Acceptance criteria

- [ ] `fetch_user_info` 呼叫 `queryUserInfo`，沿用 `_mcp_call` 既有 initialize→notified→tools/call 流程
- [ ] 抓取路徑只 `load_token → fetch`，**不呼叫 refresh、不複用 `fetch_and_persist`**
- [ ] `parse_user_weight` 從上述格式正確解出 `70.7`（float）
- [ ] `parse_user_weight` 對缺 Weight 欄位、空字串、格式異常回 None
- [ ] 單元測試涵蓋：正常、整數值、不同小數、缺欄位、空字串（比照 `tests/test_coros_mcp.py` 的 parse 真值表風格）

## Blocked by

None - can start immediately

## User stories addressed

- User story 2（抓取能力部分；「整條管線自動跑」由 `issues/005` 完成）
