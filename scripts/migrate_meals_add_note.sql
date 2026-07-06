-- forward-only migration：meals 加 note 欄位（已於 2026-07-06 對 prod 執行，經 Supabase MCP apply_migration: add_note_to_meals）
-- 目的：落庫 AI 估算依據原文（「官方值：」「標示轉錄：」「推估：」開頭），
--       供未來校正係數區分「該校正的推估筆 vs 不該校正的官方/標示/定值錨筆」。
-- nullable、無 default：舊筆與非 AI 路徑（手動/快取）維持 NULL。
ALTER TABLE meals ADD COLUMN note text;
