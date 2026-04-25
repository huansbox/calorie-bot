import logging
from datetime import date, datetime, timezone

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Meals ──────────────────────────────────────────────

def insert_meal(
    meal_type: str,
    description: str,
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    raw_input: str,
    ai_confidence: str,
    has_image: bool = False,
    image_path: str | None = None,
    image_expires_at: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    thinking_tokens: int = 0,
    recorded_at: str | None = None,
    ai_provider: str | None = None,
    ai_model: str | None = None,
) -> dict:
    """新增一筆飲食記錄，回傳插入的 row。"""
    row = {
        "meal_type": meal_type,
        "description": description,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "raw_input": raw_input,
        "ai_confidence": ai_confidence,
        "has_image": has_image,
        "image_path": image_path,
        "image_expires_at": image_expires_at,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
    }
    if recorded_at is not None:
        row["recorded_at"] = recorded_at
    if ai_provider is not None:
        row["ai_provider"] = ai_provider
    if ai_model is not None:
        row["ai_model"] = ai_model
    result = supabase.table("meals").insert(row).execute()
    logger.info("Inserted meal: %s", result.data[0]["id"])
    return result.data[0]


def get_today_meals(tz_offset: int = 8) -> list[dict]:
    """取得今日所有飲食記錄（依台灣時間）。"""
    from datetime import timedelta

    now_tw = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    today = now_tw.date()
    utc_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(hours=tz_offset)
    utc_end = utc_start + timedelta(days=1)

    result = (
        supabase.table("meals")
        .select("*")
        .gte("recorded_at", utc_start.isoformat())
        .lt("recorded_at", utc_end.isoformat())
        .order("recorded_at")
        .order("id")
        .execute()
    )
    return result.data


def get_meals_by_date(target_date: date, tz_offset: int = 8) -> list[dict]:
    """取得指定日期的所有飲食記錄（依台灣時間）。"""
    from datetime import timedelta

    start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    utc_start = start - timedelta(hours=tz_offset)
    utc_end = utc_start + timedelta(days=1)

    result = (
        supabase.table("meals")
        .select("*")
        .gte("recorded_at", utc_start.isoformat())
        .lt("recorded_at", utc_end.isoformat())
        .order("recorded_at")
        .order("id")
        .execute()
    )
    return result.data


def get_meals_by_week(start_date: date, end_date: date, tz_offset: int = 8) -> list[dict]:
    """取得指定日期範圍的所有飲食記錄（含 start_date 到 end_date）。"""
    from datetime import timedelta

    utc_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc) - timedelta(hours=tz_offset)
    utc_end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) - timedelta(hours=tz_offset) + timedelta(days=1)

    result = (
        supabase.table("meals")
        .select("*")
        .gte("recorded_at", utc_start.isoformat())
        .lt("recorded_at", utc_end.isoformat())
        .order("recorded_at")
        .order("id")
        .execute()
    )
    return result.data


def get_weekly_token_usage(tz_offset: int = 8) -> dict:
    """取得過去 7 天的 token 用量總計，依 provider 分組。"""
    from datetime import timedelta

    now_tw = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    week_ago = now_tw.date() - timedelta(days=7)
    utc_start = datetime(week_ago.year, week_ago.month, week_ago.day, tzinfo=timezone.utc) - timedelta(hours=tz_offset)

    result = (
        supabase.table("meals")
        .select("input_tokens, output_tokens, thinking_tokens, ai_provider")
        .gte("recorded_at", utc_start.isoformat())
        .gt("input_tokens", 0)
        .execute()
    )

    by_provider: dict[str, dict] = {}
    for r in result.data:
        # 歷史資料 ai_provider 為 NULL，此專案上線至今全用 Gemini
        provider = r.get("ai_provider") or "gemini"
        if provider not in by_provider:
            by_provider[provider] = {
                "input_tokens": 0, "output_tokens": 0,
                "thinking_tokens": 0, "count": 0,
            }
        by_provider[provider]["input_tokens"] += r.get("input_tokens", 0) or 0
        by_provider[provider]["output_tokens"] += r.get("output_tokens", 0) or 0
        by_provider[provider]["thinking_tokens"] += r.get("thinking_tokens", 0) or 0
        by_provider[provider]["count"] += 1

    total_input = sum(p["input_tokens"] for p in by_provider.values())
    total_output = sum(p["output_tokens"] for p in by_provider.values())
    total_thinking = sum(p["thinking_tokens"] for p in by_provider.values())

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "thinking_tokens": total_thinking,
        "count": sum(p["count"] for p in by_provider.values()),
        "by_provider": by_provider,
    }


def get_last_meal() -> dict | None:
    """取得最後一筆飲食記錄。"""
    result = (
        supabase.table("meals")
        .select("*")
        .order("recorded_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_meal(meal_id: str, updates: dict) -> dict:
    """更新指定飲食記錄。"""
    result = supabase.table("meals").update(updates).eq("id", meal_id).execute()
    return result.data[0]


def delete_meal(meal_id: str) -> None:
    """刪除指定飲食記錄。"""
    supabase.table("meals").delete().eq("id", meal_id).execute()


# ── Weight Logs ────────────────────────────────────────

def insert_weight(weight_kg: float) -> dict:
    """新增體重記錄。"""
    result = supabase.table("weight_logs").insert({"weight_kg": weight_kg}).execute()
    logger.info("Inserted weight: %s kg", weight_kg)
    return result.data[0]


def get_last_weight() -> dict | None:
    """取得最近一筆體重記錄。"""
    result = (
        supabase.table("weight_logs")
        .select("*")
        .order("recorded_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_previous_weight() -> dict | None:
    """取得倒數第二筆體重記錄（用於計算變化）。"""
    result = (
        supabase.table("weight_logs")
        .select("*")
        .order("recorded_at", desc=True)
        .order("id", desc=True)
        .limit(2)
        .execute()
    )
    return result.data[1] if len(result.data) >= 2 else None


def get_recent_weights(n: int = 7) -> list[dict]:
    """取得最近 n 筆體重記錄（時間由舊到新）。"""
    result = (
        supabase.table("weight_logs")
        .select("*")
        .order("recorded_at", desc=True)
        .order("id", desc=True)
        .limit(n)
        .execute()
    )
    return list(reversed(result.data))


def get_weight_moving_avg(n: int = 7) -> float | None:
    """計算最近 n 筆體重的移動平均，不足 3 筆回傳 None。"""
    rows = get_recent_weights(n)
    if len(rows) < 3:
        return None
    return sum(float(r["weight_kg"]) for r in rows) / len(rows)


def get_weight_range(start_date: date, end_date: date, tz_offset: int = 8) -> list[dict]:
    """取得指定日期範圍內的體重記錄，依時間排序。"""
    from datetime import timedelta

    utc_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc) - timedelta(hours=tz_offset)
    utc_end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) - timedelta(hours=tz_offset) + timedelta(days=1)

    result = (
        supabase.table("weight_logs")
        .select("*")
        .gte("recorded_at", utc_start.isoformat())
        .lt("recorded_at", utc_end.isoformat())
        .order("recorded_at")
        .order("id")
        .execute()
    )
    return result.data


# ── Daily TDEE ─────────────────────────────────────────

def upsert_tdee(tdee_kcal: int, target_date: date | None = None) -> dict:
    """新增或更新今日 TDEE（date 欄位 UNIQUE，所以用 upsert）。"""
    if target_date is None:
        from datetime import timedelta

        now_tw = datetime.now(timezone.utc) + timedelta(hours=8)
        target_date = now_tw.date()

    row = {"date": target_date.isoformat(), "tdee_kcal": tdee_kcal}
    result = (
        supabase.table("daily_tdee")
        .upsert(row, on_conflict="date")
        .execute()
    )
    logger.info("Upserted TDEE: %s kcal for %s", tdee_kcal, target_date)
    return result.data[0]


def get_tdee_by_date(target_date: date) -> dict | None:
    """取得指定日期的 TDEE 記錄。"""
    result = (
        supabase.table("daily_tdee")
        .select("*")
        .eq("date", target_date.isoformat())
        .execute()
    )
    return result.data[0] if result.data else None


def get_today_tdee(tz_offset: int = 8) -> dict | None:
    """取得今日 TDEE 記錄。"""
    from datetime import timedelta

    now_tw = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    today = now_tw.date()

    result = (
        supabase.table("daily_tdee")
        .select("*")
        .eq("date", today.isoformat())
        .execute()
    )
    return result.data[0] if result.data else None


def get_tdee_by_week(start_date: date, end_date: date) -> list[dict]:
    """取得指定日期範圍的所有 TDEE 記錄。"""
    result = (
        supabase.table("daily_tdee")
        .select("*")
        .gte("date", start_date.isoformat())
        .lte("date", end_date.isoformat())
        .order("date")
        .execute()
    )
    return result.data


# ── Cleanup ────────────────────────────────────────────

def get_expired_images() -> list[dict]:
    """取得已過期的照片記錄。"""
    now = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("meals")
        .select("id, image_path")
        .not_.is_("image_path", "null")
        .lt("image_expires_at", now)
        .execute()
    )
    return result.data


def clear_image_path(meal_id: str) -> None:
    """清除指定記錄的 image_path。"""
    supabase.table("meals").update({"image_path": None}).eq("id", meal_id).execute()


# ── Food Cache ────────────────────────────────────────

MAX_CACHE_ITEMS = 89  # 編號 11-99


def get_all_cache() -> list[dict]:
    """取得所有快取食物，依建立時間排序。"""
    result = (
        supabase.table("food_cache")
        .select("*")
        .order("created_at")
        .order("id")
        .execute()
    )
    return result.data


def get_cache_by_index(index: int) -> dict | None:
    """依編號取得快取（11 = 第一筆）。"""
    offset = index - 11
    if offset < 0:
        return None
    result = (
        supabase.table("food_cache")
        .select("*")
        .order("created_at")
        .order("id")
        .limit(1)
        .offset(offset)
        .execute()
    )
    return result.data[0] if result.data else None


def insert_cache(description: str, calories: int, protein_g: float, carbs_g: float, fat_g: float) -> dict:
    """新增快取食物。"""
    row = {
        "description": description,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }
    result = supabase.table("food_cache").insert(row).execute()
    logger.info("Inserted cache: %s", description)
    return result.data[0]


def delete_cache_by_name(description: str) -> bool:
    """依品名刪除快取，回傳是否有刪除。"""
    result = supabase.table("food_cache").delete().eq("description", description).execute()
    return len(result.data) > 0


def cache_exists(description: str) -> bool:
    """檢查品名是否已在快取中。"""
    result = (
        supabase.table("food_cache")
        .select("id")
        .eq("description", description)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


def get_meal_by_id(meal_id: str) -> dict | None:
    """依 ID 取得單筆 meal 記錄。"""
    result = (
        supabase.table("meals")
        .select("*")
        .eq("id", meal_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
