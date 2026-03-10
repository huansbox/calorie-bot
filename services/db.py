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
    }
    result = supabase.table("meals").insert(row).execute()
    logger.info("Inserted meal: %s", result.data[0]["id"])
    return result.data[0]


def get_today_meals(tz_offset: int = 8) -> list[dict]:
    """取得今日所有飲食記錄（依台灣時間）。"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 調整為台灣時間的 00:00 (UTC+8 → UTC-8h)
    from datetime import timedelta

    utc_start = today_start - timedelta(hours=tz_offset)
    utc_end = utc_start + timedelta(days=1)

    result = (
        supabase.table("meals")
        .select("*")
        .gte("recorded_at", utc_start.isoformat())
        .lt("recorded_at", utc_end.isoformat())
        .order("recorded_at")
        .execute()
    )
    return result.data


def get_last_meal() -> dict | None:
    """取得最後一筆飲食記錄。"""
    result = (
        supabase.table("meals")
        .select("*")
        .order("recorded_at", desc=True)
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
        .limit(2)
        .execute()
    )
    return result.data[1] if len(result.data) >= 2 else None


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
