import logging
import os
from datetime import date as date_type, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from config import (
    BMR,
    COROS_EMAIL,
    COROS_PASSWORD,
    COROS_TOKEN_PATH,
    PUSH_HOUR,
    TELEGRAM_CHAT_ID,
)
from services.coros_mcp import (
    CorosMCPError,
    fetch_and_persist,
    fetch_user_info,
    load_token,
    parse_user_weight,
)
from services.coros_web import CorosWebError, fetch_weight
from services.format import format_meal_groups
from services.nutrition import format_macros
from services.weight_sync import decide_weight_sync
from services.db import (
    clear_image_path,
    get_expired_images,
    get_last_weight,
    get_meals_by_date,
    get_tdee_by_date,
    get_tdee_by_week,
    get_weekly_token_usage,
    get_weight_moving_avg,
    today_has_weight_row,
    upsert_tdee,
    upsert_weight,
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
        # 已知取捨：無餐日整個摘要不推，連下方的最新體重行也一併略過。
        # 使用者幾乎天天記食物，無餐日近乎不存在，故接受此 gap（US15 的「每天」）。
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
        f"攝取：{_fmt(total_cal)} kcal",
        *format_macros(total_protein, total_carbs, total_fat),
        f"記錄筆數：{len(meals)} 餐",
    ]

    lines.extend(format_meal_groups(meals, force_meal_types=["早餐", "午餐", "晚餐"]))

    tdee_row = get_tdee_by_date(yesterday)
    lines.append("")
    if tdee_row:
        tdee = tdee_row["tdee_kcal"]
        active = tdee - BMR
        deficit = total_cal - tdee
        lines.append(f"總消耗（TDEE）：{_fmt(tdee)} kcal")
        lines.append(f"　 BMR {_fmt(BMR)} + 活動 {_fmt(active)}")
        if deficit <= 0:
            lines.append(f"熱量缺口：{_fmt(deficit)} kcal ✅")
        else:
            lines.append(f"熱量盈餘：+{_fmt(deficit)} kcal")
    else:
        lines.append("昨日未記錄 TDEE（/t <活動消耗>）")

    # 最新體重：帶 log_date 讓你看出是不是今天的（08:00 時當日同步尚未跑，顯示的
    # 必為昨日或更早），也看得出是否久未量測。無資料時優雅省略。
    last_w = get_last_weight()
    if last_w:
        w_kg = float(last_w["weight_kg"])
        w_date = date_type.fromisoformat(last_w["log_date"])
        w_date_str = (
            w_date.strftime("%-m/%-d") if os.name != "nt" else w_date.strftime("%#m/%#d")
        )
        avg = get_weight_moving_avg(7)
        lines.append("")
        if avg:
            lines.append(f"⚖️ 最新體重：{w_kg} kg（{w_date_str}，7日均線 {avg:.1f}）")
        else:
            lines.append(f"⚖️ 最新體重：{w_kg} kg（{w_date_str}）")

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\n".join(lines))
    logger.info("Daily summary sent")


async def weekly_nutrition_report(app: Application):
    """每週一推播上週營養週報。"""
    from handlers.report import _get_last_week_range, generate_report

    start, end = _get_last_week_range()
    report = generate_report(start, end, "週報")

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=report)
    logger.info("Weekly nutrition report sent")


# 費率 (USD per 1M tokens)
_PRICING = {
    "gemini": {"input": 2.0, "output": 12.0, "thinking": 12.0},
    "claude": {"input": 3.0, "output": 15.0, "thinking": 0},
    "claude-api": {"input": 3.0, "output": 15.0, "thinking": 0},
    "claude-cli": {"input": 0, "output": 0, "thinking": 0},
}


def _calc_api_cost(
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
    provider: str,
) -> float:
    """依 provider 計算 API 費用 (USD)。"""
    rates = _PRICING.get(provider, _PRICING["gemini"])
    return (
        input_tokens * rates["input"] / 1_000_000
        + output_tokens * rates["output"] / 1_000_000
        + thinking_tokens * rates["thinking"] / 1_000_000
    )


_PROVIDER_LABEL = {
    "gemini": "Gemini",
    "claude-api": "Claude API",
    "claude-cli": "Claude CLI (Max)",
}


async def weekly_api_report(app: Application):
    """每週一推播 API 用量與費用（依 provider 分組）。"""
    usage = get_weekly_token_usage()
    if usage["count"] == 0:
        return

    by_provider = usage.get("by_provider", {})

    lines = [
        "📈 本週 API 用量",
        "",
        f"總分析次數：{usage['count']} 次",
    ]

    total_cost = 0.0
    for provider, data in sorted(by_provider.items()):
        cost = _calc_api_cost(
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            thinking_tokens=data["thinking_tokens"],
            provider=provider,
        )
        total_cost += cost
        label = _PROVIDER_LABEL.get(provider, provider)

        lines.append("")
        lines.append(f"【{label}】{data['count']} 次")
        lines.append(f"  Input: {_fmt(data['input_tokens'])} tokens")
        lines.append(f"  Output: {_fmt(data['output_tokens'])} tokens")
        if data["thinking_tokens"] > 0:
            lines.append(f"  Thinking: {_fmt(data['thinking_tokens'])} tokens")
        if cost > 0:
            lines.append(f"  費用：${cost:.4f}")
        else:
            lines.append(f"  費用：$0 (Max 訂閱)")

    lines.append("")
    lines.append(f"預估總費用：${total_cost:.4f} USD")

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\n".join(lines))
    logger.info("Weekly API report sent")


async def sync_coros_tdee(app: Application):
    """每日 03:00 拉 COROS 過去 7 天 daily health → upsert daily_tdee（fill-missing-only）。

    - 7 天視窗：給之前 cron 失敗的日子自動補上機會
    - fill-missing-only：絕不覆寫已存在的 daily_tdee（你手動 /t 的值優先）
    - 失敗推 Telegram 告警，請手動 /t
    """
    now_tw = datetime.now(TW_TZ)
    yesterday = (now_tw - timedelta(days=1)).date()
    start = yesterday - timedelta(days=6)

    try:
        active_by_date, token_notice = fetch_and_persist(COROS_TOKEN_PATH, days=8)
    except CorosMCPError as e:
        msg = f"⚠️ COROS 拉取失敗\n{e}\n請手動 /t 補昨日"
        logger.error("COROS sync failed: %s", e)
        try:
            await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as send_err:
            logger.error("Failed to send Telegram alert: %s", send_err)
        return

    if token_notice:
        # token 端有事要講（已自動重新授權／無法自動續期）。資料照樣撈到了，
        # 不要求手動 /t。本 job 每日一跑，天然限頻一則。
        try:
            await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=token_notice)
        except Exception as send_err:
            logger.error("Failed to send Telegram alert: %s", send_err)

    existing_rows = get_tdee_by_week(start, yesterday)
    existing_dates = {datetime.strptime(r["date"], "%Y-%m-%d").date() for r in existing_rows}

    written: list[tuple[date_type, int]] = []
    for d in sorted(active_by_date.keys()):
        if not (start <= d <= yesterday):
            continue
        if d in existing_dates:
            continue
        tdee = BMR + active_by_date[d]
        upsert_tdee(tdee, d)
        written.append((d, tdee))
        logger.info("COROS sync wrote: %s = %d kcal", d, tdee)

    logger.info(
        "COROS sync done: wrote %d new (range %s ~ %s, %d already had data)",
        len(written), start, yesterday, len(existing_dates),
    )

    # 昨天沒拉到資料 → 告警（手錶可能沒同步上雲）
    if yesterday not in active_by_date and yesterday not in existing_dates:
        try:
            await app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"⚠️ COROS 未回傳昨日（{yesterday}）資料，請手動 /t 或檢查手錶同步",
            )
        except Exception as e:
            logger.error("Failed to send no-yesterday alert: %s", e)


def _fetch_coros_weight() -> float | None:
    """抓 COROS profile 體重：teamapi 帳密為主路徑，失敗退 MCP。抓不到回 None。

    teamapi（`/account/login` 回應直接帶 weight）零 OAuth、沒有會壞掉的 token 狀態，
    是比照 strava-sync 的主路徑；MCP 保留為 fallback，token 沿用 03:05
    sync_coros_tdee 處理過的 access_token，本 job **不自己 refresh**（PRD US22，
    把 rotation 風險集中在單一每日時點）。
    """
    if COROS_EMAIL and COROS_PASSWORD:
        try:
            return fetch_weight(COROS_EMAIL, COROS_PASSWORD)
        except CorosWebError as e:
            logger.warning("COROS teamapi 體重撈取失敗，改走 MCP fallback: %s", e)

    token = load_token(COROS_TOKEN_PATH)
    return parse_user_weight(fetch_user_info(token))


async def sync_coros_weight(app: Application):
    """每日 10:29（主抓）+ 22:29（fallback）從 COROS profile 抓體重 → 決策 → upsert。

    - 抓取 / 解析失敗一律當 fetched=None，交給 decide_weight_sync 走告警分支。
    - 決策由純函式 decide_weight_sync 負責：should_write → upsert；
      decision.message 不為 None → 推 Telegram（值同上次的輕提醒 / 抓取失敗 /
      跳變過大的告警）。fallback 透過「當天已有筆 → SKIP」自動成立，晨重優先。
    """
    try:
        fetched = _fetch_coros_weight()
    except Exception as e:  # 任何抓取 / 解析失敗 → 走 ALERT_NO_WRITE 分支
        logger.error("COROS weight sync fetch failed: %s", e)
        fetched = None

    last = get_last_weight()
    last_weight = float(last["weight_kg"]) if last else None
    today_has_row = today_has_weight_row()

    decision = decide_weight_sync(fetched, last_weight, today_has_row)
    logger.info(
        "COROS weight sync: fetched=%s last=%s today_has_row=%s -> %s",
        fetched, last_weight, today_has_row, decision.action,
    )

    if decision.should_write:
        upsert_weight(fetched, source="coros")

    if decision.message:
        try:
            await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=decision.message)
        except Exception as send_err:
            logger.error("Failed to send weight sync alert: %s", send_err)


async def cleanup_expired_images(app: Application):
    """清理過期照片檔案並更新 DB。"""
    expired = get_expired_images()
    if not expired:
        return

    for row in expired:
        # 相簿記錄的 image_path 是逗號串接的多個路徑（見 handlers/meal.py）
        for path in (row["image_path"] or "").split(","):
            if path and os.path.exists(path):
                os.remove(path)
                logger.info("Deleted expired image: %s", path)
        clear_image_path(row["id"])

    logger.info("Cleaned up %d expired images", len(expired))


UPDATE_REMINDER_TEXT = """每月 claude binary 更新提醒。把下面整段貼給一個能 SSH 到 VPS 的 Claude Code session：

————
更新 calorie-bot VPS（root@107.175.30.172）上 botuser 的 claude binary 並驗證。
可以動 binary 與版本目錄，但不要 restart bot、不要改 .env 或 systemd 設定：
1. 記更新前版本：ssh root@107.175.30.172 "sudo -u botuser /home/botuser/.local/bin/claude --version"
2. 更新：同上路徑 claude update
3. smoke（文字）：claude -p 'ping, 回簡短 JSON' --model sonnet --output-format json，確認回得出 result/modelUsage
   若 data/media 有現存圖，順手測圖片路徑：... -p '描述這張圖：<路徑>' --model sonnet --output-format json --allowedTools Read；沒有就略過（下一餐真實照片會驗）
   smoke 若回 "OAuth session expired and could not be refreshed"（modelUsage 空、~/.claude/.credentials.json 的 token 被清成空字串）：
   這是 fallback 的預期失效模式——claude -p 只在 gemini 失敗時才被呼叫，長期沒用到 refresh token 就會過期，
   而 bot 環境沒有 ANTHROPIC_API_KEY，OAuth 是唯一認證來源。修法是人工重新登入（互動式，代跑不了）：
   ssh 進 VPS 跑 sudo -u botuser -H /home/botuser/.local/bin/claude setup-token，照印出的 URL 授權完再重跑 smoke。
   主路徑 gemini 不受影響，bot 仍能正常記錄，只是暫時沒有備援。
4. 記新版本 + `--model sonnet` 現在解析到的模型（modelUsage 的 key），跟舊版比對有無跳版
5. prune ~/.local/share/claude/versions/ 保留最新 2 版、刪其餘
6. 回報：舊版→新版、模型有無變化、smoke 過否。binary 換版下次 claude -p 自動生效，不需 restart。
————"""


async def monthly_update_reminder(app):
    """每月 1 號提醒手動更新 claude binary（只送訊息，無 subprocess、無失敗模式）。"""
    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=UPDATE_REMINDER_TEXT)


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    """設定排程：每日推播 + 週報 + 照片清理 + COROS 同步 + 每月 claude 更新提醒。"""
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
        day_of_week="mon",
        hour=PUSH_HOUR,
        minute=5,
        args=[app],
        id="weekly_api_report",
    )

    scheduler.add_job(
        weekly_nutrition_report,
        "cron",
        day_of_week="mon",
        hour=PUSH_HOUR,
        minute=10,
        args=[app],
        id="weekly_nutrition_report",
    )

    scheduler.add_job(
        cleanup_expired_images,
        "cron",
        hour=3,
        minute=0,
        args=[app],
        id="cleanup_images",
    )

    scheduler.add_job(
        sync_coros_tdee,
        "cron",
        hour=3,
        minute=5,
        args=[app],
        id="sync_coros_tdee",
    )

    scheduler.add_job(
        sync_coros_weight,
        "cron",
        hour="10,22",
        minute=29,
        args=[app],
        id="sync_coros_weight",
    )

    scheduler.add_job(
        monthly_update_reminder,
        "cron",
        day=1,
        hour=10,
        minute=30,
        args=[app],
        id="update_reminder",
    )

    scheduler.start()
    logger.info(
        "Scheduler started: daily summary at %d:00, API report Mon %d:05, nutrition report Mon %d:10, image cleanup at 03:00, COROS TDEE sync at 03:05, COROS weight sync at 10:29/22:29, claude update reminder on day 1 at 10:30",
        PUSH_HOUR,
        PUSH_HOUR,
        PUSH_HOUR,
    )
    return scheduler
