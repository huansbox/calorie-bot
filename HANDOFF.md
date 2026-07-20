# HANDOFF

- Status: idle
- Task/issue: COROS 共用核心（與 strava-sync 逐字節 vendored）+ refresh fallback——修復 7/18–7/19 TDEE 同步中斷
- Branch: main
- Updated: 2026-07-20

## Progress

- 根因：COROS `/oauth2/token` 自 2026-07-18 01:50 UTC 起對**有效** refresh token 一律回 500（伺服器端 bug，重 bootstrap 無效）；資料面與既存 access_token（30 天效期）正常。strava-sync #28 有完整記錄
- calobot：`services/coros_mcp_core.py`（共用核心，含 `refresh_with_fallback`）+ facade 瘦身 + scheduler「已續行」警示。merge `8f1534b`，**已部署 VPS**（service active）
- strava-sync：`lt2_auto/coros_mcp_core.py`（同一份複本）+ `tools/sync_coros_core.py`（check/copy）+ sync.bat step 7b 每小時 drift check（ntfy 告警）。merge `564ef4c`。sync.bat 逐次執行讀 working tree，無需部署動作
- 機制記錄：兩 repo CLAUDE.md、calobot wiki/Maintenance.md（含新告警 runbook 列）
- 觀察項（非阻塞）：7/21 03:05 後 `daily_tdee` 應自動回補 7/18（BMR+1704）、7/19（BMR+2317），且收到「已續行」警示而非「請手動 /t」；strava-sync 下個整點 sync.bat step 7b 首次實跑應報「兩份一致」；COROS refresh 持續故障則 calobot token 效期至約 8/17（strava-sync 約 8/18），逼近需重跑 bootstrap
- 前案（gemini provider 切換，觀察期）備忘：billing 已接回未回標 docs、機器硬檢構想已認可未排程、media 孤兒照片入 Tech-Debt 不主動查——詳見 `git show 1c4508f:HANDOFF.md` 與 CLAUDE.md「進行中的設計」

## Next step

None

## Validation

- calobot `uv run pytest tests/` 204 passed（test_coros_mcp.py 29，含 fallback 新案例）
- strava-sync `uv run pytest tests/` 509 passed
- VPS 真實故障 smoke：refresh 仍 500 → fallback 用既存 token 撈回 8 天（含缺的 7/18、7/19）
- 兩 repo 核心檔 `cmp` 逐字節一致；`sync_coros_core.py` skip（repo 不存在）與 drift（exit 1 + 訊息）路徑實測通過
- 未跑：明早 03:05 排程自動回補（等真實觸發）；step 7b 排程內首次執行

## Blockers

None
