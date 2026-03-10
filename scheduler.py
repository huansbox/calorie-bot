import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import DAILY_CALORIE_GOAL, PUSH_HOUR, TELEGRAM_CHAT_ID
from services.db import clear_image_path, get_expired_images, get_today_meals, get_today_tdee

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))


def _fmt(n: int) -> str:
    return f"{n:,}"


async def daily_summary(app: Application):
    """每日推播今日摘要。"""
    meals = get_today_meals()
    if not meals:
        logger.info("No meals today, skipping daily summary")
        return

    now_tw = datetime.now(TW_TZ)
    date_str = now_tw.strftime("%#m/%#d") if os.name == "nt" else now_tw.strftime("%-m/%-d")

    total_cal = sum(m["calories"] or 0 for m in meals)
    total_protein = sum(float(m["protein_g"] or 0) for m in meals)
    total_carbs = sum(float(m["carbs_g"] or 0) for m in meals)
    total_fat = sum(float(m["fat_g"] or 0) for m in meals)

    lines = [
        f"📊 今日摘要（{date_str}）",
        "",
        f"攝取：{_fmt(total_cal)} kcal　目標參考：{_fmt(DAILY_CALORIE_GOAL)} kcal",
        f"蛋白質：{total_protein:.0f}g　碳水：{total_carbs:.0f}g　脂肪：{total_fat:.0f}g",
        f"記錄筆數：{len(meals)} 餐",
    ]

    tdee_row = get_today_tdee()
    lines.append("")
    if tdee_row:
        tdee = tdee_row["tdee_kcal"]
        deficit = total_cal - tdee
        lines.append(f"總消耗（TDEE）：{_fmt(tdee)} kcal")
        if deficit <= 0:
            lines.append(f"熱量缺口：{_fmt(deficit)} kcal ✅")
        else:
            lines.append(f"熱量盈餘：+{_fmt(deficit)} kcal")
    else:
        lines.append("今日尚未記錄 TDEE（/tdee <數字>）")

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\n".join(lines))
    logger.info("Daily summary sent")


async def cleanup_expired_images(app: Application):
    """清理過期照片檔案並更新 DB。"""
    expired = get_expired_images()
    if not expired:
        return

    for row in expired:
        path = row["image_path"]
        if path and os.path.exists(path):
            os.remove(path)
            logger.info("Deleted expired image: %s", path)
        clear_image_path(row["id"])

    logger.info("Cleaned up %d expired images", len(expired))


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    """設定排程：每日推播 + 照片清理。"""
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")

    scheduler.add_job(
        daily_summary,
        "cron",
        hour=PUSH_HOUR,
        minute=0,
        args=[app],
        id="daily_summary",
    )

    scheduler.add_job(
        cleanup_expired_images,
        "cron",
        hour=3,
        minute=0,
        args=[app],
        id="cleanup_images",
    )

    scheduler.start()
    logger.info("Scheduler started: daily summary at %d:00, image cleanup at 03:00", PUSH_HOUR)
    return scheduler
