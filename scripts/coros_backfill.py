"""COROS → daily_tdee 補登腳本。

兩種資料來源：
  1) --mcp-file <path>  讀 COROS MCP queryDailyHealthData 的純文字輸出（含 NEAT，準）
  2) （預設）coros-api 公開 endpoint，sum 運動 session calorie（不含 NEAT，會低估 200–400 kcal/天）

執行方式（需 op 解鎖載入 SUPABASE_*）：
    # 用 MCP 文字（先讓 Claude Code 跑 queryDailyHealthData，存到 tmp/mcp_health.txt）：
    op run --env-file .env -- uv run python scripts/coros_backfill.py --mcp-file tmp/mcp_health.txt
    op run --env-file .env -- uv run python scripts/coros_backfill.py --mcp-file tmp/mcp_health.txt --apply

    # 用 coros-api fallback：
    op run --env-file .env -- uv run python scripts/coros_backfill.py
    op run --env-file .env -- uv run python scripts/coros_backfill.py --apply

旗標：
    --days N      只看過去 N 天（預設 30，不含今天）
    --apply       真的 upsert；不加只是 dry-run
    --force       連已有 TDEE 的日子也覆寫（預設只補缺）

設計：
- daily_tdee 的 date 用台灣時區
- 排除今天（資料未完整）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BMR  # noqa: E402
from services.db import get_tdee_by_week, upsert_tdee  # noqa: E402

TW_TZ = timezone(timedelta(hours=8))
COROS_ENV_PATH = Path("D:/mywork/coros-api/.env")


# ── MCP 文字解析 ────────────────────────────────────────────

_MCP_DATE_RE = re.compile(r"^---\s*(\d{8})\s*---")
_MCP_CAL_RE = re.compile(r"Calories:\s*([\d,]+)\s*kcal")


def parse_mcp_output(text: str) -> dict[date, int]:
    """從 queryDailyHealthData 的純文字輸出解出 {date: active_kcal}。"""
    out: dict[date, int] = {}
    current_date: date | None = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _MCP_DATE_RE.match(line)
        if m:
            current_date = datetime.strptime(m.group(1), "%Y%m%d").date()
            continue
        if current_date is None:
            continue
        m = _MCP_CAL_RE.search(line)
        if m:
            out[current_date] = int(m.group(1).replace(",", ""))
            current_date = None
    return out


# ── coros-api fallback ──────────────────────────────────────

def _load_env(p: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _login(base: str, email: str, password: str) -> str:
    md5 = hashlib.md5(password.encode()).hexdigest()
    body = json.dumps({"account": email, "accountType": 2, "pwd": md5}).encode()
    req = urllib.request.Request(
        f"{base}/account/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["data"]["accessToken"]


def _query_activities(base: str, token: str, start: date, end: date) -> list[dict]:
    all_items: list[dict] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({
            "size": "200",
            "pageNumber": str(page),
            "modeList": "",
            "startDay": start.strftime("%Y%m%d"),
            "endDay": end.strftime("%Y%m%d"),
        })
        req = urllib.request.Request(
            f"{base}/activity/query?{qs}",
            headers={"accessToken": token},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        data = resp.get("data", {})
        items = data.get("dataList") or []
        all_items.extend(items)
        if page >= data.get("totalPage", 1):
            break
        page += 1
    return all_items


def fetch_via_coros_api(start: date, end: date) -> dict[date, int]:
    env = _load_env(COROS_ENV_PATH)
    base = env.get("COROS_API_URL", "https://teamapi.coros.com").rstrip("/")
    token = _login(base, env["COROS_EMAIL"], env["COROS_PASSWORD"])
    items = _query_activities(base, token, start, end)
    bucket: dict[date, float] = defaultdict(float)
    for a in items:
        d_int = a.get("date")
        if not d_int:
            continue
        d = datetime.strptime(str(d_int), "%Y%m%d").date()
        bucket[d] += a.get("calorie", 0) / 1000.0
    return {d: round(v) for d, v in bucket.items()}


# ── 主流程 ─────────────────────────────────────────────────

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description="COROS → daily_tdee 補登")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--mcp-file",
        type=Path,
        help="讀 MCP queryDailyHealthData 文字輸出，比 coros-api 準（含 NEAT）",
    )
    args = parser.parse_args()

    if not os.getenv("SUPABASE_URL"):
        print("ERROR: SUPABASE_URL 未設定 —— 用 `op run --env-file .env -- ...` 包起來執行")
        return 2

    today_tw = datetime.now(TW_TZ).date()
    end = today_tw - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)
    print(f"範圍：{start} ~ {end}（{args.days} 天，不含今天）")
    print(f"BMR={BMR} kcal")

    if args.mcp_file:
        print(f"\n讀 MCP 檔：{args.mcp_file}")
        active_by_date = parse_mcp_output(args.mcp_file.read_text(encoding="utf-8"))
        active_by_date = {d: v for d, v in active_by_date.items() if start <= d <= end}
        source = "MCP (含 NEAT)"
    else:
        print("\n抓 coros-api 公開 endpoint（不含 NEAT，會低估）...")
        active_by_date = fetch_via_coros_api(start, end)
        source = "coros-api"
    print(f"資料來源：{source}，有資料天數：{len(active_by_date)}")

    print("\n查 daily_tdee 已記錄 ...")
    existing_rows = get_tdee_by_week(start, end)
    existing_by_date = {datetime.strptime(r["date"], "%Y-%m-%d").date(): r["tdee_kcal"] for r in existing_rows}
    print(f"daily_tdee 已有：{len(existing_by_date)} 天")

    print("\n" + "=" * 80)
    print(f"{'日期':<12} {'活動消耗':>10} {'BMR+活動':>10} {'目前TDEE':>10} {'動作':<14}")
    print("-" * 80)

    to_write: list[tuple[date, int]] = []
    missing_data_dates: list[date] = []
    for offset in range(args.days):
        d = end - timedelta(days=offset)
        active = active_by_date.get(d)
        if active is None:
            missing_data_dates.append(d)
            active_str = "(無資料)"
            proposed_str = "-"
            action = "skip(無源)"
            existing = existing_by_date.get(d)
        else:
            proposed = BMR + active
            existing = existing_by_date.get(d)
            active_str = f"{active:,}"
            proposed_str = f"{proposed:,}"
            if existing is None:
                action = "補登"
                to_write.append((d, proposed))
            elif args.force and existing != proposed:
                action = f"覆寫(原{existing})"
                to_write.append((d, proposed))
            else:
                action = "skip"
        existing_str = str(existing) if existing is not None else "-"
        print(f"{d.isoformat():<12} {active_str:>10} {proposed_str:>10} {existing_str:>10} {action:<14}")

    print("=" * 80)
    print(f"\n預計寫入 {len(to_write)} 筆")
    if missing_data_dates:
        print(f"提醒：{len(missing_data_dates)} 天無 {source} 資料（可能還沒同步上雲）")

    if not args.apply:
        print("（dry-run，加 --apply 真的寫）")
        return 0

    if not to_write:
        print("沒有要寫的，結束。")
        return 0

    print("\n寫入中 ...")
    for d, tdee in to_write:
        upsert_tdee(tdee, d)
        print(f"  ✓ {d} = {tdee} kcal")
    print(f"\n完成，寫入 {len(to_write)} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
