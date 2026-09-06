# Carry-over：輪替 1Password Service Account token

**這不是已規格化的任務。** 實作前若需擴大範圍，先跑 `/grill-me` 對齊；由該流程產出的 issue 應關閉或取代本項。

不屬於 `issues/prd.md`（COROS 體重同步）那條編號序列。

## 事實（2026-09-06 建立）

Claude Code session 在 VPS 上讀 Supabase 時，用了

```
sudo -u botuser env OP_SERVICE_ACCOUNT_TOKEN=$(grep -o '...' /etc/calorie-bot/op-token.env | cut -d= -f2-) op run ...
```

這種形式。`sudo` 會把完整 argv 記進 `/var/log/auth.log`，因此該 SA token 以明文落在 log 裡。

實測範圍：

- `/var/log/auth.log` 有 **15 行**含明文的 `OP_SERVICE_ACCOUNT_TOKEN=<token>`
- 時間全部落在 **2026-09-06 02:48–03:21 UTC**，即該次 session
- 輪替過的 `auth.log.1`、`auth.log.{2,3,4}.gz` **零筆** → 是該次 session 引入的，非既有問題

影響：這把 token 能解出 1Password `Developer / Calorie Bot` 的全部欄位（`TELEGRAM_TOKEN`、`SUPABASE_KEY`、`GEMINI_API_KEY`、`CLAUDE_CODE_OAUTH_TOKEN`、`COROS_EMAIL`/`COROS_PASSWORD`）。

## 為什麼停在這裡

輪替要在 1Password 產生新的 Service Account token，屬於使用者操作，session 內無法完成。

## 下一個 session 從哪裡開始

1. 使用者在 1Password 產生新的 SA token
2. 寫入 VPS `/etc/calorie-bot/op-token.env`（權限 600、root only）
3. `systemctl restart calorie-bot`
4. 驗證 `op run` 仍能解出密鑰（bot 正常啟動、排程註冊）

輪替後 auth.log 裡那 15 行即為死字串，`auth.log` 本身是稽核 log，不建議改動。

## 預防

正確的取用方式（token 不經 argv）已寫進 memory `reference_vps.md`，並附明確禁止 argv 形式的警告：

```
set -a; source /etc/calorie-bot/op-token.env; set +a
sudo -u botuser --preserve-env=OP_SERVICE_ACCOUNT_TOKEN bash -lc "cd ... && op run --env-file .env -- ..."
```
