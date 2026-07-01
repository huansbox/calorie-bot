# Claude -p 轉正 + 每月更新提醒 設計

狀態：設計定案（經兩輪 3-agent 複審 + 更新策略改為手動提醒），待實作
日期：2026-07-01

## 為什麼（rationale）

- Gemini API **停用**（程式碼保留，可隨時重啟用），`claude -p` CLI 從「fallback」轉為**唯一預設路徑**。
- 走 Max 訂閱 $0，停掉 Gemini API key 的使用與計費。
- 附帶把「botuser 憑證 × root binary」這個安裝順序留下的**意外耦合**收乾淨，並還原被放寬的 `/root` 權限。
- 每餐回覆改印**實際模型**（取代舊的 `⚡ Claude CLI` fallback 標籤），讓模型漂移**每餐可見**。

## 決策摘要（已定案）

| 項目     | 決定                                                                                                                                                                      |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 分析路徑   | `claude -p` 唯一預設，**無 fallback**（選項 A）。Gemini／Claude API 分支保留、不接線                                                                                                        |
| 模型     | `--model sonnet`（別名、不鎖版本），透過 `CLAUDE_CLI_MODEL` env（預設 `sonnet`），換模型只改 .env                                                                                             |
| binary | 切到 botuser 自己的 `/home/botuser/.local/bin/claude`（透過 .env `CLAUDE_CLI_PATH`）                                                                                             |
| 更新策略   | binary 唯一會變的時機＝你手動更新：`.env` 加 `DISABLE_AUTOUPDATER=1`（關自動更新）+ 每月 1 號 10:30 Telegram **提醒**你手動 `claude update`（訊息附可貼給 session 的 prompt，內含 smoke + prune）。**無自動換 binary** |
| 回覆標籤   | 有 `ai_model` 就印模型（如 `· claude-sonnet-4-6`），沒有就不印（D2）                                                                                                                    |
| 權限收尾   | `chmod 700 /root`，且**延到 bot 穩跑約一天後**再做（保留回滾退路）                                                                                                                          |

## 核心機制 / 關鍵洞察

1. **別名解析 baked 進 binary 版本**。實測：同一個 `--model opus`，舊 binary 2.1.96 給 `claude-opus-4-6`、新 binary 2.1.185 給 `claude-opus-4-8`；`--model sonnet` 兩顆都 `claude-sonnet-4-6`（該期間沒出更新 sonnet，一致、非反例）。官方文件加強佐證別名為 client-side、隨版本 gating（Opus 4.8 需 CLI ≥ 2.1.154、Sonnet 5 需 ≥ 2.1.197）。結論：`--model sonnet` 只給「**這顆 binary 知道的最新**」，要跟上新模型 binary 必須更新。
   - **FYI**：把 botuser binary `claude update` 到 latest 後，`--model sonnet` 很可能**從 sonnet-4-6 跳成 Sonnet 5**（若 latest ≥ 2.1.197）。上線後 bot 大概率跑 Sonnet 5，非 4-6——「sonnet 夠用」的基準以 Sonnet 5 看（更強，OK）。
2. **為何切 botuser 自己的 binary**（觀察／假設，非已證實事實）：
   - 服務自給自足 / least-privilege：常駐服務不該依賴讀 `/root` 的檔案。
   - 手動 `claude update`（由你觸發）要能生效，前提是**執行者對 binary 安裝目錄有寫權限**。botuser 對 `/home/botuser/.local/share/claude/versions`（實測 `drwxrwxr-x botuser botuser`）可寫，對 root 的安裝目錄不可寫。
   - ⚠️ auto-updater 究竟寫「binary 安裝路徑」還是「執行者 HOME 推導路徑」官方未明講；兩種解讀下「切 botuser binary」**都是對的**，故低風險。
3. **模型漂移由&#x20;********`ai_model`********&#x20;逐筆留痕**（即時記錄已實作，`/b` 補記本次補上——見 Code #3）。`services/ai.py` 從 `modelUsage` 取首 key → `_normalize_model_name` 去 `[...]` 後綴 → `meals.ai_model`，值含版本（如 `claude-sonnet-4-6`）。搭配 D2「每餐回覆印模型」，漂移**即時可見**（不必等週報）。
   - **已知邊界（D2 回歸）**：`modelUsage` 缺失時（`ai.py` else warning 分支）`ai_model=None` → 標籤消失、該筆也無留痕。實測 `modelUsage` 一向都有，屬罕見；依 D2「沒有就刪」接受之，文件記錄在此。（可選：缺 `modelUsage` 時退回通用 `· claude-cli` 標記——本次不做，待觀察。）
4. **現況耦合的成因**：`CLAUDE_CLI_PATH` 預設 `/root/.local/bin/claude`、`.env` 未覆蓋 → bot（botuser 執行）跑的是 root 的 binary，只因 `/root` 被放寬成 `705`（drwx---r-x，非預設 700）botuser 才讀得到；憑證則讀 botuser 自己的 `~/.claude`。切到 botuser binary 後耦合與權限放寬都能收掉。

## 更新策略（為何是「提醒」而非「自動」）

自動 `claude update`（in-process 排程）的所有痛點——hang/timeout、APScheduler `max_instances=1` 卡死後再也不更新、無人時 envelope 漂移靜默壞掉、prune 要寫進 code、in-process vs systemd 取捨——**全源於「無人值守時自動換 binary」**。改「每月提醒 + 手動更新」把此前提拿掉：更新在你看著時發生、當場 smoke 驗證；scheduler 只送一則訊息（零失敗模式）。配 `DISABLE_AUTOUPDATER=1`，形成強不變式：**binary 唯一會變的時機＝你手動那次**。代價是每月動一下手，但貼式 prompt 讓它趨近於零；D2 每餐印模型，平時被動看得到版本，不怕不知不覺變舊。

## 完整流程

### Code（本機改 + 測試）

1. `config.py`
   - 新增 `CLAUDE_CLI_MODEL: str = os.getenv("CLAUDE_CLI_MODEL", "sonnet")`
   - `AI_PROVIDER` 預設改為 `"claude-cli"`（新增此值語意）

2. `services/ai.py`
   - `_analyze_claude_cli` 的 `cmd` 加 `--model {CLAUDE_CLI_MODEL}`（import 補 `CLAUDE_CLI_MODEL`）
   - `analyze_food` 路由改三分支：`claude`→API；`gemini`→Gemini 後 cli fallback（保留）；其餘（含預設 `claude-cli`）→ 只走 `claude -p`、無 fallback

3. `handlers/backfill.py`：`insert_meal(...)` 補 `ai_model=result.ai_model`（`backfill.py:262` 後）。**修正 §3 稽核軌跡對 /b 補記斷掉的洞。**

4. `handlers/meal.py:111` 與 `handlers/backfill.py:270`：`provider_tag` 改為模型標籤（D2）：

   ```python
   model_tag = f" · {result.ai_model}" if result.ai_model else ""
   ```

   並把 `meal.py:113`、`backfill.py:272` 內用到 `provider_tag` 的地方換成 `model_tag`。（可選：去 `claude-` 前綴讓每餐回覆更短。）

5. `scheduler.py`：**在&#x20;********`setup_scheduler(app)`********&#x20;內、********`scheduler.start()`********（********`scheduler.py:358`********）之前**加每月更新提醒 job（骨架見下），比照 sibling 帶 `args=[app]` + `id=`。此 job 只送訊息、無 subprocess、無失敗模式。**無需改 main.py**。

6. `tests/test_ai.py`：補路由分支測試 + `--model` 有帶入。**注意**：`services/ai.py:7` 是 import-time 綁定 `from config import AI_PROVIDER`，測試要 `monkeypatch.setattr("services.ai.AI_PROVIDER", ...)`，改 env／改 `config.AI_PROVIDER` 皆無效。

### 文件同步清單（變更後會過時，一併改）

- `CLAUDE.md` 技術架構「**AI**: Gemini 優先 + claude -p CLI 自動 fallback」及三條子項 → 改為 claude -p 預設、Gemini/Claude API 保留可切換。
- `CLAUDE.md` 關鍵設計決策「**AI fallback 鏈**：Gemini API → claude -p CLI → 錯誤訊息」→ 改述為 claude-cli-only（gemini 值才有 fallback）。
- `CLAUDE.md` **排程清單字串出現兩次**（`CLAUDE.md:21` 技術架構、`CLAUDE.md:31` 檔案結構 scheduler.py 註解）→ 兩處都加「每月 1 號 10:30 claude 更新提醒」。
- `scheduler.py:299` `setup_scheduler` docstring + `:359-360` startup log 字串 → 加每月更新提醒。
- `services/ai.py:344-346` `analyze_food` docstring（仍寫「Gemini API → claude -p CLI fallback」）。
- `services/db.py:141` 註解「此專案上線至今全用 Gemini」→ 會變半真（新資料全 claude-cli；`or "gemini"` 對歷史 NULL 列的邏輯不壞，但註解誤導）。
- **`README.md`**（給未來的我的環境文件，勿漏）：
  - `README.md:3` 「Gemini API 優先，失敗時自動 fallback 到 claude -p CLI」→ 改述。
  - `README.md:72` `| AI_PROVIDER | gemini（預設…）或 claude |` → 預設改 `claude-cli`、補列新值 `claude-cli`。
  - 環境變數表**新增&#x20;********`CLAUDE_CLI_MODEL`********（預設&#x20;********`sonnet`********）、********`DISABLE_AUTOUPDATER`********（********`1`********）** 兩列。

### VPS（部署，順序關鍵）

1. **更新 botuser binary**：`sudo -u botuser /home/botuser/.local/bin/claude update`
   （用絕對路徑：sudoers `secure_path` 不含 `/home/botuser/.local/bin`，裸 `claude` 會 command-not-found。或 `sudo -iu botuser claude ...`。此時 bot 仍跑 root binary 2.1.185，兩顆互不干擾。）

2. **煙霧測試（翻 .env 前必做，文字 + 圖片都要）**：

   ```
   # 文字路徑
   sudo -u botuser /home/botuser/.local/bin/claude -p 'ping, 回一個簡短 JSON' --model sonnet --output-format json
   # 圖片路徑（prod 會加 --allowedTools Read；純文字 smoke 攔不到圖片專屬回歸）
   sudo -u botuser /home/botuser/.local/bin/claude -p '讀取並描述這張圖：/path/to/test.jpg' --model sonnet --output-format json --allowedTools Read
   ```

   確認兩發都回得出 `result` / `modelUsage`、版本 ≥ 已知良品。**失敗就停，別翻 .env**（切過去無 fallback，且 2.1.96→latest 前形同降版）。

3. **確認 auto-update 已關**：`sudo -iu botuser claude config get autoUpdates`（應為 false），並在 `.env` 加 `DISABLE_AUTOUPDATER=1` 做強不變式（只擋自動更新，不影響你手動的 `claude update`）。

4. `.env` 四行：

   ```
   AI_PROVIDER=claude-cli
   CLAUDE_CLI_PATH=/home/botuser/.local/bin/claude
   CLAUDE_CLI_MODEL=sonnet
   DISABLE_AUTOUPDATER=1
   ```

5. `git pull`（帶入每月提醒 job）+ `systemctl restart calorie-bot`

6. **驗證**：Telegram 實打一餐（文字＋照片各一）→ 回覆正常、每則印 `· claude-sonnet-…` 模型標籤、`meals.ai_provider=claude-cli` + `ai_model` 有值；再 `/b` 補記一筆確認 `ai_model` 也有落（驗 Code #3）。

7. **穩跑約一天後**再 `chmod 700 /root`（在此之前 root binary 是回滾退路，見下）。

8. 部署前先看一次 VPS 剩餘磁碟做基準（每次手動更新會長一版 binary，靠更新時 prune 控制，見 watch #5）。

### Rollback

- **binary 壞**：還原 `.env` `CLAUDE_CLI_PATH=/root/.local/bin/claude` + restart。**僅在步驟 7（chmod 700）之前有效**（之後 botuser 讀不到 root binary）——這正是步驟 7 要延後的理由。
- **回 Gemini**：`.env` `AI_PROVIDER=gemini` + restart。前提：Gemini key 仍在 1Password（`.env` 的 `op://` 參照保留，未刪 → 確認保留）。

## 實作骨架

```python
# config.py
AI_PROVIDER: str = os.getenv("AI_PROVIDER", "claude-cli")  # claude-cli / gemini / claude
CLAUDE_CLI_MODEL: str = os.getenv("CLAUDE_CLI_MODEL", "sonnet")  # 別名，不鎖版本
```

```python
# services/ai.py — _analyze_claude_cli
from config import CLAUDE_CLI_MODEL  # 既有 import 補上
cmd = [CLAUDE_CLI_PATH, "-p", "".join(prompt_parts),
       "--output-format", "json", "--model", CLAUDE_CLI_MODEL]
if image_path:
    cmd.extend(["--allowedTools", "Read"])
```

```python
# services/ai.py — analyze_food 路由
async def analyze_food(text=None, image_path=None) -> FoodAnalysis:
    if AI_PROVIDER == "claude":                     # Claude API（無 fallback，備選）
        return await _analyze_claude(text=text, image_path=image_path)
    if AI_PROVIDER == "gemini":                      # 保留：Gemini → claude -p fallback
        try:
            return await _analyze_gemini(text=text, image_path=image_path)
        except Exception as e:
            logger.warning("Gemini 失敗，切 claude -p: %s", e)
        return await _analyze_claude_cli(text=text, image_path=image_path)
    # 預設 claude-cli：唯一路徑，無 fallback
    return await _analyze_claude_cli(text=text, image_path=image_path)
```

```python
# scheduler.py — 每月 1 號 10:30 提醒手動更新（放 setup_scheduler(app) 內、start() 前）
UPDATE_REMINDER_TEXT = """每月 claude binary 更新提醒。把下面整段貼給一個能 SSH 到 VPS 的 Claude Code session：

————
更新 calorie-bot VPS（root@107.175.30.172）上 botuser 的 claude binary 並驗證，唯讀報告、不要 restart bot：
1. 記更新前版本：ssh root@107.175.30.172 "sudo -u botuser /home/botuser/.local/bin/claude --version"
2. 更新：同上路徑 claude update
3. smoke（文字）：claude -p 'ping, 回簡短 JSON' --model sonnet --output-format json，確認回得出 result/modelUsage
   若 data/media 有現存圖，順手測圖片路徑：... -p '描述這張圖：<路徑>' --model sonnet --output-format json --allowedTools Read；沒有就略過（下一餐真實照片會驗）
4. 記新版本 + `--model sonnet` 現在解析到的模型（modelUsage 的 key），跟舊版比對有無跳版
5. prune ~/.local/share/claude/versions/ 保留最新 2 版、刪其餘
6. 回報：舊版→新版、模型有無變化、smoke 過否。binary 換版下次 claude -p 自動生效，不需 restart。
————"""

async def monthly_update_reminder(app):
    from config import TELEGRAM_CHAT_ID
    await app.bot.send_message(TELEGRAM_CHAT_ID, UPDATE_REMINDER_TEXT)

# 在 setup_scheduler(app) 內、scheduler.start() 之前：
scheduler.add_job(
    monthly_update_reminder, "cron", day=1, hour=10, minute=30,
    args=[app], id="update_reminder",
)
```

## 尚待決定 / 風險（watch items）

1. **模型漂移可見性**：改手動更新後，漂移由三層兜住——更新時你當場 smoke（貼式 prompt 第 3-4 步）、D2 每餐印模型、parse 壞即 `分析失敗` 立刻可見。無自動路徑＝無「無人時靜默壞掉」。
2. **`get_weekly_token_usage`********&#x20;用&#x20;********`.gt("input_tokens", 0)`****\*\*\*\* 過濾**（`services/db.py:134`）。claude-cli 的 `input_tokens` 來自 envelope；若某週全 cache-read 回 0 → `count==0` → `weekly_api_report`（`scheduler.py:151-152`）提早 return、**該週 API 週報整封不發**。同一判準也用來「區分 AI vs 手動」。**上線首週確認** token/週報照發。（純 cosmetic 面：週 API 費用會掉到 \~\$0，正常。）
3. **60s timeout 是唯一硬失敗點且無 fallback**（`services/ai.py:301`）。claude -p 從偶爾 fallback 變每餐必跑 + `--model` + 照片 `Read`。建議至少標註，或提成 env 旋鈕日後不改 code 調整。
4. **無 fallback**：claude -p 掛掉該餐分析直接失敗（`meal.py:73-76` / `backfill.py:234-237` → 「分析失敗，請重試。」）。可接受（Max 穩定、有手動記錄逃生口）。日後不放心再考慮「claude -p 主、Gemini 反向 fallback」。
5. **磁碟堆積**：每版 binary ≈ 230 MB、`claude update` 不自清（root 端累積三版佐證）。因改手動更新、頻率低（每月），prune 併進更新流程（貼式 prompt 第 5 步：保留最新 2 版）。部署前量一次剩餘磁碟做基準（VPS 步驟 8）。

## Builder 交接（本次實作）

**給執行 session 的邊界與驗收。此段之外的「VPS（部署）」段不在 Builder 範圍。**

### 範圍

- **只做**：Code（本節「完整流程 → Code #1–6」）+ 文件同步清單 + 本機 `uv run pytest` + push。
- **絕對不做**：VPS 部署那 8 步（smoke／翻 .env／restart／驗證／`chmod 700 /root`）。那是有序、需真人盯的 ops 動作，留給 review 後有人看著時執行。Builder 碰到「要 ssh / 改 .env / restart」就停下回報。

### 流程

1. branch：`feat/claude-cli-primary`（從 `main` 開）。
2. 依下列順序小步提交（每個 commit 只做一件事，Conventional Commits、英文）：
   1. `feat(ai): default to claude -p CLI, add --model via CLAUDE_CLI_MODEL` — `config.py`（Code #1）+ `services/ai.py`（Code #2）+ `tests/test_ai.py`（Code #6）
   2. `fix(backfill): record ai_model on /b meals` — `handlers/backfill.py`（Code #3）
   3. `feat(meal): show model tag instead of provider tag` — `handlers/meal.py` + `handlers/backfill.py`（Code #4，D2）
   4. `feat(scheduler): monthly claude update reminder` — `scheduler.py`（Code #5）
   5. `docs: sync Gemini→claude-cli across docs` — 文件同步清單那批（CLAUDE.md ×2、README、docstrings、`services/db.py:141` 註解）
3. 驗收：`uv run pytest` 全綠（新增測試涵蓋路由三分支 + `--model` 有帶入；注意 `monkeypatch.setattr("services.ai.AI_PROVIDER", ...)`，見 Code #6）。
4. push branch，**不要**開 PR 直接 merge、**不要**部署。回報：commit 清單 + pytest 結果 + 有無偏離 doc 之處，交回 review。

### 給新 session 的起手 prompt（直接貼）

```
你是 Builder。讀 docs/claude-cli-primary-design.md，只實作「完整流程 → Code #1–6」+「文件同步清單」，不要碰「VPS（部署）」那段（那是需真人盯的 ops，碰到要 ssh/改 .env/restart 就停下回報）。

做法：從 main 開 feat/claude-cli-primary，照 doc「Builder 交接」的 5 個 commit 順序小步提交（Conventional Commits、英文）。跑 uv run pytest 要全綠（路由三分支 + --model 帶入的測試，記得 monkeypatch services.ai.AI_PROVIDER）。完成後 push，不要開 PR merge、不要部署，回報 commit 清單 + pytest 結果 + 有無偏離 doc。
```

