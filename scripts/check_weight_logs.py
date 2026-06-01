"""One-off: inspect weight_logs for same-day-multiple-rows before adding log_date UNIQUE.

Run: op run --env-file .env -- uv run python scripts/check_weight_logs.py
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from services.db import supabase

TW = timezone(timedelta(hours=8))

rows = (
    supabase.table("weight_logs")
    .select("*")
    .order("recorded_at")
    .order("id")
    .execute()
    .data
)

print(f"total rows: {len(rows)}")
if not rows:
    raise SystemExit("no rows")

# show columns present (to confirm current schema)
print(f"columns: {sorted(rows[0].keys())}")

by_date = defaultdict(list)
for r in rows:
    dt = datetime.fromisoformat(r["recorded_at"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tw_date = dt.astimezone(TW).date()
    by_date[tw_date].append(r)

multi = {d: rs for d, rs in by_date.items() if len(rs) > 1}
print(f"distinct TW days with data: {len(by_date)}")
print(f"days with >1 row: {len(multi)}")
print(f"date range: {min(by_date)} ~ {max(by_date)}")

for d in sorted(multi):
    print(f"  {d}: {len(multi[d])} rows")
    for r in multi[d]:
        print(f"    {r['recorded_at']}  {r['weight_kg']} kg  id={r.get('id')}")
