-- ============================================================================
-- Migration: weight_logs 新增 log_date + source，壓成「一天一筆」，建 UNIQUE
-- ----------------------------------------------------------------------------
-- 對應 issues/001-migration-script.md（撰寫）+ issues/002-execute-migration.md（執行）。
-- Forward-only：不寫 rollback（單人專案慣例）。
--
-- 不可逆操作（刪一筆 + 加 UNIQUE 約束），標記為 HITL：
--   1) 先跑「Section A：唯讀預檢」，人工確認筆數與 3/13 兩筆符合 PRD。
--   2) 確認無誤後，再跑「Section B：交易式遷移」（BEGIN…COMMIT，失敗整批回滾）。
--   3) 最後跑「Section C：執行後驗證」核對結果。
--
-- 時區假設：recorded_at 為 timestamp WITH time zone（timestamptz）。
--   `recorded_at AT TIME ZONE 'Asia/Taipei'` → 台灣牆上時間，再 ::date 取台灣日期。
--   若 Section A 的 information_schema 查詢顯示 recorded_at 為「without time zone」
--   （代表存的是裸 UTC），請把所有 `recorded_at AT TIME ZONE 'Asia/Taipei'` 改成
--   `recorded_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Taipei'` 後再執行。
-- ============================================================================


-- ============================================================================
-- Section A：唯讀預檢（先跑，人工確認，無任何寫入）
-- ============================================================================

-- A1. 確認 recorded_at 欄位型別（決定上面的時區轉換是否正確）。
--     期望 data_type = 'timestamp with time zone'。
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'weight_logs'
ORDER BY ordinal_position;

-- A2. 總筆數與台灣日期分佈。期望：total = 42、distinct_tw_days = 41、
--     days_with_multiple_rows = 1（唯一同日多筆是 2026-03-13）、
--     範圍 2026-03-11 ~ 2026-06-01。
SELECT
    count(*)                                                       AS total_rows,
    count(DISTINCT (recorded_at AT TIME ZONE 'Asia/Taipei')::date) AS distinct_tw_days,
    min((recorded_at AT TIME ZONE 'Asia/Taipei')::date)            AS first_tw_day,
    max((recorded_at AT TIME ZONE 'Asia/Taipei')::date)            AS last_tw_day
FROM weight_logs;

-- A3. 列出所有同台灣日多筆的日子（期望只有 2026-03-13 一天）。
SELECT
    (recorded_at AT TIME ZONE 'Asia/Taipei')::date AS tw_day,
    count(*)                                       AS rows_on_day
FROM weight_logs
GROUP BY 1
HAVING count(*) > 1
ORDER BY 1;

-- A4. 攤開 3/13 兩筆供人工核對（PRD：72.3 kg @ 台灣 00:29 午夜筆 / 71.2 kg @ 晨重）。
--     確認「要刪的午夜筆」= 該日最早 recorded_at 那筆 = 72.3。
--     PRD 記錄的 id 僅供對照；本遷移以「該日最早 recorded_at」識別，不盲刪寫死 id。
SELECT
    id,
    recorded_at,
    (recorded_at AT TIME ZONE 'Asia/Taipei') AS tw_local,
    weight_kg
FROM weight_logs
WHERE (recorded_at AT TIME ZONE 'Asia/Taipei')::date = DATE '2026-03-13'
ORDER BY recorded_at;


-- ============================================================================
-- Section B：交易式遷移（Section A 確認無誤後才跑；整批成功或整批回滾）
-- ============================================================================
BEGIN;

-- B1. 加兩欄（先可為 NULL，待回填後再上 NOT NULL）。
ALTER TABLE weight_logs ADD COLUMN IF NOT EXISTS log_date date;
ALTER TABLE weight_logs ADD COLUMN IF NOT EXISTS source   text;

-- B2. 回填既有 42 筆：source='manual'、log_date 由 recorded_at 換算台灣(UTC+8)日期。
--     WHERE 條件讓遷移可重入（只補未填的）。
UPDATE weight_logs
SET source   = 'manual',
    log_date = (recorded_at AT TIME ZONE 'Asia/Taipei')::date
WHERE log_date IS NULL OR source IS NULL;

-- B3. 處理 3/13 同日兩筆衝突：刪除午夜筆（該日最早 recorded_at = 台灣 00:29 = 72.3），
--     保留晨重 71.2。以邏輯（MIN recorded_at）識別，非寫死 id。
--     預期：刪 1 筆。若刪到 0 或 >1 筆，代表資料與 Section A 不符 → ROLLBACK 重查。
DELETE FROM weight_logs
WHERE log_date = DATE '2026-03-13'
  AND recorded_at = (
      SELECT min(recorded_at)
      FROM weight_logs
      WHERE log_date = DATE '2026-03-13'
  );

-- B4. 上 NOT NULL（回填後全有值；log_date NOT NULL 是「一天一筆」保證的前提，
--     避免 UNIQUE 允許多個 NULL 的破口）。
ALTER TABLE weight_logs ALTER COLUMN log_date SET NOT NULL;
ALTER TABLE weight_logs ALTER COLUMN source   SET NOT NULL;

-- B5. 壓成一天一筆後，建立 log_date UNIQUE 約束（作為日後 upsert on log_date 的衝突鍵）。
--     若仍有同日多筆，這裡會失敗 → 整個交易回滾（安全）。
ALTER TABLE weight_logs ADD CONSTRAINT weight_logs_log_date_key UNIQUE (log_date);

COMMIT;


-- ============================================================================
-- Section C：執行後驗證（COMMIT 後跑）
-- ============================================================================

-- C1. 筆數 42 → 41，且每個台灣日恰一筆（distinct = total）。
SELECT
    count(*)                    AS total_rows,        -- 期望 41
    count(DISTINCT log_date)    AS distinct_log_dates -- 期望 41（= total）
FROM weight_logs;

-- C2. 不應再有任何同 log_date 多筆。期望 0 列。
SELECT log_date, count(*)
FROM weight_logs
GROUP BY log_date
HAVING count(*) > 1;

-- C3. 確認 3/13 只剩 71.2（晨重）。
SELECT id, recorded_at, weight_kg, log_date, source
FROM weight_logs
WHERE log_date = DATE '2026-03-13';

-- C4. 確認 source 全部回填為 'manual'（期望 manual = 41，其餘 = 0）。
SELECT source, count(*)
FROM weight_logs
GROUP BY source
ORDER BY source;

-- C5. 確認 UNIQUE 約束已建立（期望查得到 weight_logs_log_date_key）。
SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'weight_logs'::regclass
  AND contype = 'u';

-- C6.（可選）約束生效煙霧測試：以下兩句故意插同日兩筆，第二句應被 UNIQUE 擋下。
--     驗證後務必 ROLLBACK，不要留下測試資料。
-- BEGIN;
--   INSERT INTO weight_logs (weight_kg, log_date, source) VALUES (99.9, DATE '2099-01-01', 'manual');
--   INSERT INTO weight_logs (weight_kg, log_date, source) VALUES (88.8, DATE '2099-01-01', 'manual'); -- 應報 duplicate key
-- ROLLBACK;
