import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import PUSH_HOUR, TELEGRAM_CHAT_ID, get_calorie_goal
from services.nutrition import format_macros
from services.db import (
    clear_image_path,
    get_expired_images,
    get_meals_by_date,
    get_tdee_by_date,
    get_weekly_token_usage,
)

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))


def _fmt(n: int) -> str:
    return f"{n:,}"


async def daily_summary(app: Application):
    """每日早上推播昨日摘要。"""
    now_tw = datetime.now(TW_TZ)
    yesterday = (now_tw - timedelta(days=1)).date()
    meals = get_meals_by_date(yesterday)

    if not meals:
        logger.info("No meals yesterday, skipping daily summary")
        return

    date_str = yesterday.strftime("%-m/%-d") if os.name != "nt" else yesterday.strftime("%#m/%#d")

    total_cal = sum(m["calories"] or 0 for m in meals)
    total_protein = sum(float(m["protein_g"] or 0) for m in meals)
    total_carbs = sum(float(m["carbs_g"] or 0) for m in meals)
    total_fat = sum(float(m["fat_g"] or 0) for m in meals)

    lines = [
        f"📊 昨日摘要（{date_str}）",
        "",
        f"攝取：{_fmt(total_cal)} kcal　目標參考：{_fmt(get_calorie_goal())} kcal",
        *format_macros(total_protein, total_carbs, total_fat),
        f"記錄筆數：{len(meals)} 餐",
    ]

    tdee_row = get_tdee_by_date(yesterday)
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
        lines.append("昨日未記錄 TDEE（/t <活動消耗>）")

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\n".join(lines))
    logger.info("Daily summary sent")


async def weekly_api_report(app: Application):
    """每週日推播 API 用量與費用。"""
    usage = get_weekly_token_usage()
    if usage["count"] == 0:
        return

    input_cost = usage["input_tokens"] * 3 / 1_000_000
    output_cost = usage["output_tokens"] * 15 / 1_000_000
    total_cost = input_cost + output_cost

    lines = [
        "📈 本週 API 用量",
        "",
        f"分析次數：{usage['count']} 次",
        f"Input tokens：{_fmt(usage['input_tokens'])}",
        f"Output tokens：{_fmt(usage['output_tokens'])}",
        f"預估費用：${total_cost:.4f} USD",
    ]

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\n".join(lines))
    logger.info("Weekly API report sent")


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
    """設定排程：每日推播 + 週報 + 照片清理。"""
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
        weekly_api_report,
        "cron",
        day_of_week="sun",
        hour=PUSH_HOUR,
        minute=5,
        args=[app],
        id="weekly_api_report",
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
    logger.info(
        "Scheduler started: daily summary at %d:00, weekly report Sun %d:05, image cleanup at 03:00",
        PUSH_HOUR,
        PUSH_HOUR,
    )
    return scheduler
