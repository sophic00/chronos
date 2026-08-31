import asyncio
import calendar
import io
import logging

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from functools import wraps

import httpx
import pytz
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from ..config import constants
from ..config import settings as config
from ..data.database import (
    get_current_streak,
    get_daily_breakdown_from_db,
    get_daily_stats_from_db,
    get_leetcode_target,
    get_monthly_stats_from_db,
    get_past_day_stats_from_db,
    get_past_week_stats_from_db,
    get_weekly_stats_from_db,
    set_leetcode_target,
    set_value,
)
from ..integrations.leetcode import (
    get_leetcode_cookies,
    get_leetcode_headers,
    get_leetcode_problem_difficulty,
    get_leetcode_submission_details,
)
from .image_generator import generate_solve_card, generate_summary_card
from .messaging import cf_rating_bands, escape_md, format_bytes, prettify_language


def _stats_total(stats: dict) -> int:
    """Total solve count across all platforms in a stats dictionary."""
    return sum(sum(platform.values()) for platform in stats.values())


def _build_summary_extras(summary_type: str, target_date) -> dict:
    """Builds streak / delta / per-day activity extras for the summary image card.

    Args:
        summary_type: "daily", "weekly", or "monthly"
        target_date: The reference date of the summary period.
    """
    extras = {"streak": get_current_streak()}

    if summary_type == "daily":
        start = target_date - timedelta(days=6)
        breakdown = get_daily_breakdown_from_db(start, target_date)
        extras["activity"] = [
            ((start + timedelta(days=i)).strftime("%a")[:2],
             breakdown.get(start + timedelta(days=i), 0))
            for i in range(7)
        ]
        extras["activity_title"] = "LAST 7 DAYS"
        previous = get_daily_stats_from_db(target_date - timedelta(days=1))
        current = get_daily_stats_from_db(target_date)
        extras["delta"] = _stats_total(current) - _stats_total(previous)
        extras["delta_label"] = "VS YESTERDAY"
    elif summary_type == "weekly":
        start = target_date - timedelta(days=target_date.weekday())
        breakdown = get_daily_breakdown_from_db(start, start + timedelta(days=6))
        extras["activity"] = [
            ((start + timedelta(days=i)).strftime("%a")[:2],
             breakdown.get(start + timedelta(days=i), 0))
            for i in range(7)
        ]
        extras["activity_title"] = "THIS WEEK"
        previous = get_weekly_stats_from_db(start - timedelta(days=7))
        current = get_weekly_stats_from_db(target_date)
        extras["delta"] = _stats_total(current) - _stats_total(previous)
        extras["delta_label"] = "VS LAST WEEK"
    else:  # monthly
        first_day = target_date.replace(day=1)
        days_in_month = calendar.monthrange(target_date.year, target_date.month)[1]
        breakdown = get_daily_breakdown_from_db(first_day, first_day + timedelta(days=days_in_month - 1))
        extras["activity"] = [
            (str(day), breakdown.get(first_day + timedelta(days=day - 1), 0))
            for day in range(1, days_in_month + 1)
        ]
        extras["activity_title"] = target_date.strftime("%B").upper()
        previous = get_monthly_stats_from_db(first_day - timedelta(days=1))
        current = get_monthly_stats_from_db(target_date)
        extras["delta"] = _stats_total(current) - _stats_total(previous)
        extras["delta_label"] = "VS LAST MONTH"

    return extras


def _format_progress_bar(current: int, target: int) -> str:
    if target == 0:
        # No target set, but show current count if there are attempts
        return str(current) if current > 0 else "─"
    
    percentage = min(100, (current / target) * 100)
    filled_blocks = round(percentage / 10)
    filled_blocks = min(10, filled_blocks)
    
    filled = "▰"
    empty = "═"
    
    progress_bar = filled * filled_blocks + empty * (10 - filled_blocks)
    
    if current >= target:
        indicator = " ✅"  
    else:
        indicator = " ❌" 
    
    return f"{progress_bar} {current}/{target}{indicator}"


def _format_summary_message(stats: dict, target_type: str = None) -> tuple[str, int]:
    """Formats the complete summary message from a stats dictionary."""
    lc_stats = stats.get("leetcode", {})
    cf_stats = stats.get("codeforces", {})
    
    # LeetCode stats
    lc_easy = lc_stats.get("Easy", 0)
    lc_medium = lc_stats.get("Medium", 0)
    lc_hard = lc_stats.get("Hard", 0)
    lc_na = sum(count for diff, count in lc_stats.items() if diff not in ("Easy", "Medium", "Hard"))
    
    lc_total = sum(lc_stats.values())

    # Codeforces stats aggregation
    cf_bands = cf_rating_bands(cf_stats)
            
    cf_total = sum(cf_stats.values())
    grand_total = lc_total + cf_total
    
    message_parts = []
    
    if lc_total > 0 or target_type:
        targets = get_leetcode_target(target_type) if target_type else {'easy': 0, 'medium': 0, 'hard': 0}
        
        if target_type and (targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0):
            lc_summary = (
                f"💻 *LeetCode Summary*\n"
                f"↦ 🟢 *Easy:* {_format_progress_bar(lc_easy, targets['easy'])}\n"
                f"↦ 🟡 *Medium:* {_format_progress_bar(lc_medium, targets['medium'])}\n"
                f"↦ 🔴 *Hard:* {_format_progress_bar(lc_hard, targets['hard'])}\n"
                f"↦ ❓ *Other/Unrated:* {lc_na}\n"
                f"✅ *Total LeetCode:* {lc_total} problems"
            )
        else:
            # Show normal summary without targets
            lc_summary = (
                f"💻 *LeetCode Summary*\n"
                f"↦ 🟢 *Easy:* {lc_easy}\n"
                f"↦ 🟡 *Medium:* {lc_medium}\n"
                f"↦ 🔴 *Hard:* {lc_hard}\n"
                f"↦ ❓ *Other/Unrated:* {lc_na}\n"
                f"✅ *Total LeetCode:* {lc_total} problems"
            )
        message_parts.append(lc_summary)

    if cf_total > 0:
        cf_summary = (
            f"⚔️ *Codeforces Summary*\n"
            f"↦ 🥉 *800–1000:* {cf_bands['800-1000']}\n"
            f"↦ 🥈 *1100–1300:* {cf_bands['1100-1300']}\n"
            f"↦ 🥇 *1400–1600:* {cf_bands['1400-1600']}\n"
            f"↦ 🏆 *1700+:* {cf_bands['1700+']}\n"
            f"↦ ❓ *Unrated/Other:* {cf_bands['unrated']}\n"
            f"✅ *Total Codeforces:* {cf_total} problems"
        )
        message_parts.append(cf_summary)

    if target_type and lc_total > 0:
        targets = get_leetcode_target(target_type)
        if targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0:
            targets_met = 0
            total_targets = 0
            
            if targets['easy'] > 0:
                total_targets += 1
                if lc_easy >= targets['easy']:
                    targets_met += 1
            
            if targets['medium'] > 0:
                total_targets += 1
                if lc_medium >= targets['medium']:
                    targets_met += 1
            
            if targets['hard'] > 0:
                total_targets += 1
                if lc_hard >= targets['hard']:
                    targets_met += 1
            
            if targets_met == total_targets:
                achievement_status = "🎉 *All targets achieved!* Excellent work! 💪"
            elif targets_met > 0:
                achievement_status = f"🎯 *{targets_met}/{total_targets} targets achieved.* Keep pushing! 🚀"
            else:
                achievement_status = f"💪 *0/{total_targets} targets achieved.* Let's get started! 🔥"
            
            message_parts.append(achievement_status)

    details = "\n\n━━━━━━━━━━━━━━━\n\n".join(message_parts)
    return details, grand_total


_SUMMARY_CONFIG = {
    "daily": {
        "db_stats": get_daily_stats_from_db,
        "title": "Daily Coding Report",
        "period_label": "Date",
        "period": lambda d: d.strftime("%B %d, %Y"),
        "total_label": "Grand Total Solved Today",
        "none_msg": "yet another uneventful day.",
        "last_sent_key": "last_sent_daily_summary_date",
    },
    "weekly": {
        "db_stats": get_weekly_stats_from_db,
        "title": "Weekly Progress Report",
        "period_label": "Period",
        "period": lambda d: _week_range(_start_of_week(d)),
        "total_label": "Grand Total Solved This Week",
        "none_msg": "No problems were solved this week. Let's step up next week! 💪",
        "last_sent_key": "last_sent_weekly_summary_date",
    },
    "monthly": {
        "db_stats": get_monthly_stats_from_db,
        "title": "Monthly Progress Report",
        "period_label": "Period",
        "period": lambda d: d.strftime("%B %Y"),
        "total_label": "Grand Total Solved This Month",
        "none_msg": "No problems were solved this month. Let's do better next month! 💪",
        "last_sent_key": "last_sent_monthly_summary_date",
    },
}


def build_summary_message(kind: str, target_date, stats: dict, recovered: bool = False) -> str:
    """Formats the full summary text for a daily/weekly/monthly report."""
    cfg = _SUMMARY_CONFIG[kind]
    summary_details, grand_total = _format_summary_message(stats, kind)

    if grand_total == 0:
        return cfg["none_msg"]

    recovered_tag = " (RECOVERED)" if recovered else ""
    return (
        f"📊 *{cfg['title']}{recovered_tag}*\n"
        f"🗓️ *{cfg['period_label']}:* {cfg['period'](target_date)}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *{cfg['total_label']}:* {grand_total}"
    )


def _summary_marker_date(kind: str, target_date):
    """The date persisted after a summary is sent (start of week / month for those kinds)."""
    if kind == "weekly":
        return _start_of_week(target_date)
    if kind == "monthly":
        return target_date.replace(day=1)
    return target_date


async def send_summary(bot, kind: str, target_date=None, recovered: bool = False, mark_sent: bool = True) -> None:
    """Builds and sends a daily/weekly/monthly summary to the channel as an
    image card (with text fallback) or plain text, then records it as sent."""
    cfg = _SUMMARY_CONFIG[kind]
    if target_date is None:
        target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()

    stats = cfg["db_stats"](target_date)
    message = build_summary_message(kind, target_date, stats, recovered=recovered)

    if message != cfg["none_msg"] and config.SEND_AS_IMAGE:
        try:
            image_bytes = await asyncio.to_thread(
                generate_summary_card,
                kind, cfg["period"](target_date), stats,
                targets=get_leetcode_target(kind),
                extras=_build_summary_extras(kind, target_date)
            )
            await bot.send_photo(
                chat_id=config.CHANNEL_ID,
                photo=io.BytesIO(image_bytes),
                caption=message,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"{kind.capitalize()} summary sent as image.")
        except Exception as img_err:
            logger.error(f"Failed to generate/send {kind} summary image: {img_err}. Falling back to text.", exc_info=True)
            await bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"{kind.capitalize()} summary sent as text.")

    if mark_sent:
        set_value(cfg["last_sent_key"], _summary_marker_date(kind, target_date).isoformat())


def get_daily_summary_message(target_date=None) -> str:
    """Generates the daily summary message content for target_date (or today if None)."""
    if target_date is None:
        target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
    return build_summary_message("daily", target_date, get_daily_stats_from_db(target_date))


async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE, target_date=None):
    """Sends the daily summary message to the channel."""
    logger.info("Sending daily summary...")
    await send_summary(context.bot, "daily", target_date)


async def test_codeforces_submission(app: Application):
    """Fetches the latest CF submission and sends a test notification."""
    logger.info("--- Testing Codeforces Submission ---")
    try:
        method_name = "user.status"
        # Lazy import to avoid circular dependency
        from ..integrations.codeforces import _signed_params
        params = _signed_params(method_name, {
            "handle": config.CF_HANDLE,
            "from": 1,
            "count": 1,
        })
        
        # Use async httpx for non-blocking requests
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(constants.CODEFORCES_API_URL + f"/{method_name}", params=params)
            response.raise_for_status()
            data = response.json()

        if data["status"] == "OK" and data["result"]:
            submission = data["result"][0]
            problem = submission["problem"]
            problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
            verdict = submission.get('verdict', 'N/A')
            rating = problem.get('rating', 'NA')
            
            if config.SEND_AS_IMAGE:
                try:
                    stats = [
                        ("Language", prettify_language(submission['programmingLanguage'])),
                        ("Time", f"{submission['timeConsumedMillis']} ms"),
                        ("Memory", format_bytes(submission['memoryConsumedBytes'])),
                        ("Problem", f"{problem.get('contestId')}{problem.get('index')}")
                    ]
                    solve_dt = datetime.fromtimestamp(
                        submission["creationTimeSeconds"], tz=pytz.timezone(config.TIMEZONE)
                    )
                    image_bytes = await asyncio.to_thread(
                        generate_solve_card,
                        platform="Codeforces",
                        title=f"[TEST] {problem['name']}",
                        difficulty=str(rating),
                        stats=stats,
                        tags=problem.get("tags", [])[:3],
                        footer_left=solve_dt.strftime("%d %b %Y, %I:%M %p"),
                        footer_right=f"@{config.CF_HANDLE}"
                    )
                    
                    caption = (
                        f"👾 *[TEST] Latest Submission on Codeforces*\n"
                        f"📘 *Problem:* [{escape_md(problem['name'])}]({problem_url})\n"
                        f"🏷️ *Rating:* {rating}"
                    )
                    
                    await app.bot.send_photo(
                        chat_id=config.CHANNEL_ID,
                        photo=io.BytesIO(image_bytes),
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    logger.info(f"Sent Codeforces test photo notification for submission {submission['id']}.")
                except Exception as img_err:
                    logger.error(f"Failed to generate/send Codeforces test image: {img_err}. Falling back to text.", exc_info=True)
                    message = (
                        f"👾 *[TEST] Latest Submission* 👾\n\n"
                        f"**Platform:** Codeforces\n"
                        f"**Problem:** [{escape_md(problem['name'])}]({problem_url})\n"
                        f"**Verdict:** {verdict}\n"
                        f"**Language:** {submission['programmingLanguage']}\n"
                        f"**Time:** {submission['timeConsumedMillis']} ms\n"
                        f"**Memory:** {submission['memoryConsumedBytes'] // 1024} KB"
                    )
                    await app.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            else:
                message = (
                    f"👾 *[TEST] Latest Submission* 👾\n\n"
                    f"**Platform:** Codeforces\n"
                    f"**Problem:** [{escape_md(problem['name'])}]({problem_url})\n"
                    f"**Verdict:** {verdict}\n"
                    f"**Language:** {submission['programmingLanguage']}\n"
                    f"**Time:** {submission['timeConsumedMillis']} ms\n"
                    f"**Memory:** {submission['memoryConsumedBytes'] // 1024} KB"
                )
                await app.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Sent Codeforces test notification for submission {submission['id']}.")
        else:
            logger.warning(f"Could not fetch latest Codeforces submission. Status: {data.get('comment')}")
    except httpx.RequestError as e:
        logger.error(f"An error occurred with Codeforces API during test: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Codeforces API returned error status {e.response.status_code} during test: {e}")
    except httpx.TimeoutException as e:
        logger.error(f"Codeforces API request timed out during test: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during Codeforces test: {e}", exc_info=True)


async def test_leetcode_submission(app: Application):
    """Fetches the latest LC submission and sends a test notification."""
    logger.info("--- Testing LeetCode Submission ---")
    graphql_query = {
        "query": """
            query recentAcSubmissions($username: String!, $limit: Int!) {
              recentAcSubmissionList(username: $username, limit: $limit) {
                id
                title
                titleSlug
                timestamp
                lang
              }
            }
        """,
        "variables": {"username": config.LEETCODE_USERNAME, "limit": 1}
    }
    cookies = get_leetcode_cookies()
    headers = get_leetcode_headers()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()

        if "errors" in data:
            logger.error(f"LeetCode API error on test fetch: {data['errors']}")
            return

        submissions = data.get("data", {}).get("recentAcSubmissionList", [])
        if submissions:
            sub = submissions[0]
            problem_url = f"https://leetcode.com/problems/{sub['titleSlug']}/"
            
            # Fetch difficulty and details
            difficulty = await get_leetcode_problem_difficulty(sub['titleSlug'])
            if not difficulty:
                difficulty = "N/A"
            details = await get_leetcode_submission_details(int(sub['id']))
            runtime = memory = beats = None
            if details:
                if details.get('runtime') is not None:
                    runtime = f"{details['runtime']} ms"
                if details.get('memory') is not None:
                    memory = format_bytes(details['memory'])
                if details.get('runtimePercentile') is not None:
                    beats = f"{details['runtimePercentile']:.1f}%"

            if config.SEND_AS_IMAGE:
                try:
                    stats = [
                        ("Language", prettify_language(sub['lang'])),
                        ("Runtime", runtime if runtime else "N/A"),
                        ("Memory", memory if memory else "N/A"),
                        ("Beats", beats if beats else "N/A")
                    ]
                    solve_dt = datetime.fromtimestamp(
                        int(sub["timestamp"]), tz=pytz.timezone(config.TIMEZONE)
                    )
                    image_bytes = await asyncio.to_thread(
                        generate_solve_card,
                        platform="LeetCode",
                        title=f"[TEST] {sub['title']}",
                        difficulty=difficulty,
                        stats=stats,
                        footer_left=solve_dt.strftime("%d %b %Y, %I:%M %p"),
                        footer_right=f"@{config.LEETCODE_USERNAME}"
                    )
                    
                    caption = (
                        f"👾 *[TEST] Latest Submission on LeetCode*\n"
                        f"📘 *Problem:* [{escape_md(sub['title'])}]({problem_url})\n"
                        f"🏷️ *Difficulty:* {difficulty}"
                    )
                    
                    await app.bot.send_photo(
                        chat_id=config.CHANNEL_ID,
                        photo=io.BytesIO(image_bytes),
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    logger.info(f"Sent LeetCode test photo notification for submission {sub['id']}")
                except Exception as img_err:
                    logger.error(f"Failed to generate/send LeetCode test image: {img_err}. Falling back to text.", exc_info=True)
                    message = (
                        f"👾 *[TEST] Latest Submission* 👾\n\n"
                        f"**Platform:** LeetCode\n"
                        f"**Problem:** [{escape_md(sub['title'])}]({problem_url})\n"
                        f"**Language:** {sub['lang']}"
                    )
                    if runtime and memory:
                        message += f"\n**Runtime:** {runtime}\n**Memory:** {memory}"
                    else:
                        message += "\n_(Could not fetch runtime/memory details)_"
                    await app.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            else:
                message = (
                    f"👾 *[TEST] Latest Submission* 👾\n\n"
                    f"**Platform:** LeetCode\n"
                    f"**Problem:** [{escape_md(sub['title'])}]({problem_url})\n"
                    f"**Language:** {sub['lang']}"
                )
                if runtime and memory:
                    message += f"\n**Runtime:** {runtime}\n**Memory:** {memory}"
                else:
                    message += "\n_(Could not fetch runtime/memory details)_"
                await app.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            logger.info(f"Sent LeetCode test notification for submission ID {sub['id']}")
        else:
            logger.warning("Could not find any recent LeetCode submissions to test.")
    except Exception as e:
        logger.error(f"An error occurred during LeetCode test: {e}", exc_info=True)


def _start_of_week(dt):
    return (dt - timedelta(days=dt.weekday())).date()

def _week_range(start_date):
    end_date = start_date + timedelta(days=6)
    return f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

def _start_of_last_week(dt):
    return (dt - timedelta(days=dt.weekday())).date() - timedelta(days=7)


def _make_stats_handler(
    kind: str,
    fetch_stats,
    heading: str,
    total_label: str,
    period_label: str,
    period_fn,
    extras_date_fn,
    target_kind: str,
    empty_heading: str,
    empty_period: bool,
    target_label: str,
    empty_msg: str,
    empty_no_targets: str,
):
    """Builds a /stats-style command handler.

    All five stats commands share the same flow; only the period, DB source
    and wording differ, so those are captured here.
    """
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        now = datetime.now(pytz.timezone(config.TIMEZONE))
        stats = fetch_stats()
        summary_details, grand_total = _format_summary_message(stats, kind)
        period = period_fn(now)
        targets = get_leetcode_target(target_kind)
        targets_set = targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0

        if grand_total == 0:
            if targets_set:
                target_summary = (
                    f"📊 *{empty_heading}*\n"
                    + (f"🗓️ *{period_label}:* {period}\n" if empty_period else "")
                    + f"🎯 *{target_label}:*\n"
                    f"🟢 Easy: {_format_progress_bar(0, targets['easy'])}\n"
                    f"🟡 Medium: {_format_progress_bar(0, targets['medium'])}\n"
                    f"🔴 Hard: {_format_progress_bar(0, targets['hard'])}\n\n"
                    f"{empty_msg}"
                )
                await update.message.reply_text(target_summary, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(
                    empty_no_targets.format(period=period), disable_web_page_preview=True
                )
            return

        summary_message = (
            f"📊 *{heading}*\n"
            f"🗓️ *{period_label}:* {period}\n"
            f"🚀 *Progress Overview*\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{summary_details}\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🎯 *{total_label}:* {grand_total}"
        )

        if config.SEND_AS_IMAGE:
            try:
                image_bytes = await asyncio.to_thread(
                    generate_summary_card,
                    kind, period, stats,
                    targets=targets,
                    extras=_build_summary_extras(kind, extras_date_fn(now))
                )
                await update.message.reply_photo(
                    photo=io.BytesIO(image_bytes),
                    caption=summary_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as img_err:
                logger.error(f"Failed to generate/send {kind} stats summary image: {img_err}. Falling back to text.", exc_info=True)
                await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    return handler


stats_handler = _make_stats_handler(
    kind="daily",
    fetch_stats=lambda: get_daily_stats_from_db(),
    heading="Today's Progress So Far",
    total_label="Grand Total Solved Today",
    period_label="Date",
    period_fn=lambda now: now.strftime("%B %d, %Y"),
    extras_date_fn=lambda now: now.date(),
    target_kind="daily",
    empty_heading="Today's Progress",
    empty_period=False,
    target_label="Daily Targets",
    empty_msg="You haven't solved any new problems yet today. Let's get started! 💪",
    empty_no_targets="You haven't solved any new problems yet today. Let's get started! 💪",
)

monthly_stats_handler = _make_stats_handler(
    kind="monthly",
    fetch_stats=lambda: get_monthly_stats_from_db(),
    heading="Monthly Progress Report",
    total_label="Grand Total Solved This Month",
    period_label="Period",
    period_fn=lambda now: now.strftime("%B %Y"),
    extras_date_fn=lambda now: now.date(),
    target_kind="monthly",
    empty_heading="Monthly Progress Report",
    empty_period=True,
    target_label="Monthly Targets",
    empty_msg="You haven't solved any new problems this month yet. Let's get started! 💪",
    empty_no_targets="You haven't solved any new problems this month yet. Let's get started! 💪",
)

weekly_stats_handler = _make_stats_handler(
    kind="weekly",
    fetch_stats=lambda: get_weekly_stats_from_db(),
    heading="Weekly Progress Report",
    total_label="Grand Total Solved This Week",
    period_label="Period",
    period_fn=lambda now: _week_range(_start_of_week(now)),
    extras_date_fn=lambda now: now.date(),
    target_kind="weekly",
    empty_heading="Weekly Progress Report",
    empty_period=True,
    target_label="Weekly Targets",
    empty_msg="You haven't solved any new problems this week yet. Let's get started! 💪",
    empty_no_targets="You haven't solved any new problems this week yet. Let's get started! 💪",
)

past_day_stats_handler = _make_stats_handler(
    kind="daily",
    fetch_stats=lambda: get_past_day_stats_from_db(),
    heading="Yesterday's Progress Report",
    total_label="Grand Total Solved Yesterday",
    period_label="Date",
    period_fn=lambda now: (now - timedelta(days=1)).strftime("%B %d, %Y"),
    extras_date_fn=lambda now: (now - timedelta(days=1)).date(),
    target_kind="daily",
    empty_heading="Yesterday's Progress Report",
    empty_period=True,
    target_label="Daily Targets (for reference)",
    empty_msg="You didn't solve any new problems yesterday. 📅",
    empty_no_targets="You didn't solve any new problems on {period}. 📅",
)

past_week_stats_handler = _make_stats_handler(
    kind="weekly",
    fetch_stats=lambda: get_past_week_stats_from_db(),
    heading="Last Week's Progress Report",
    total_label="Grand Total Solved Last Week",
    period_label="Period",
    period_fn=lambda now: _week_range(_start_of_last_week(now)),
    extras_date_fn=lambda now: _start_of_last_week(now),
    target_kind="weekly",
    empty_heading="Last Week's Progress Report",
    empty_period=True,
    target_label="Weekly Targets (for reference)",
    empty_msg="You didn't solve any new problems last week. 📅",
    empty_no_targets="You didn't solve any new problems last week ({period}). 📅",
)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with all available commands."""
    help_text = (
        "ℹ️ *Chronos Bot Help*\n\n"
        "Here are the available commands:\n\n"
        "📊 *Stats Commands*\n"
        "• `/stats` - View today's progress so far\n"
        "• `/wstats` - View current weekly progress\n"
        "• `/mstats` - View current monthly progress\n"
        "• `/pstats` - View yesterday's progress\n"
        "• `/pwstats` - View last week's progress\n\n"
        "🎯 *Target Commands*\n"
        "• `/dset <easy> <medium> <hard>` - Set daily LeetCode targets\n"
        "• `/wset <easy> <medium> <hard>` - Set weekly LeetCode targets\n"
        "• `/mset <easy> <medium> <hard>` - Set monthly LeetCode targets\n\n"
        "🔌 *Utility Commands*\n"
        "• `/help` - Show this help message\n"
        "• `/ping` - Check if the bot is online"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with a pong message."""
    await update.message.reply_text("Pong!")


def _make_target_setter(
    target_type: str,
    label: str,
    noun: str,
    example_args: str,
    usage_note: str,
    success_close: str,
    channel_close: str,
):
    """Builds a /dset-style target command handler (dset/wset/mset)."""
    command = f"{target_type[0]}set"

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) != 3:
            await update.message.reply_text(
                f"❌ *Usage:* `/{command} <easy> <medium> <hard>`\n"
                f"Example: `/{command} {example_args}` ({usage_note})",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        try:
            easy = int(context.args[0])
            medium = int(context.args[1])
            hard = int(context.args[2])

            if easy < 0 or medium < 0 or hard < 0:
                await update.message.reply_text("❌ All target values must be non-negative integers.")
                return

            success = set_leetcode_target(target_type, easy, medium, hard)

            if success:
                await update.message.reply_text(
                    f"✅ *{label} LeetCode Target Set!*\n\n"
                    f"🟢 *Easy:* {easy} problems/{noun}\n"
                    f"🟡 *Medium:* {medium} problems/{noun}\n"
                    f"🔴 *Hard:* {hard} problems/{noun}\n\n"
                    f"{success_close}",
                    parse_mode=ParseMode.MARKDOWN
                )

                channel_message = (
                    f"🎯 *New {label} Target Set!*\n\n"
                    f"📊 *LeetCode {label} Goals:*\n"
                    f"🟢 Easy: {easy} problems\n"
                    f"🟡 Medium: {medium} problems\n"
                    f"🔴 Hard: {hard} problems\n\n"
                    f"{channel_close}"
                )
                await context.bot.send_message(
                    config.CHANNEL_ID,
                    channel_message,
                    disable_web_page_preview=True,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(f"❌ Failed to set {target_type} target. Please try again.")

        except ValueError:
            await update.message.reply_text("❌ All arguments must be valid integers.")

    return handler


set_daily_target_handler = _make_target_setter(
    target_type="daily",
    label="Daily",
    noun="day",
    example_args="2 1 0",
    usage_note="2 easy, 1 medium, 0 hard per day",
    success_close="Good luck crushing your daily goals! 💪",
    channel_close="Let's achieve these goals every day! 🚀",
)

set_weekly_target_handler = _make_target_setter(
    target_type="weekly",
    label="Weekly",
    noun="week",
    example_args="10 5 2",
    usage_note="10 easy, 5 medium, 2 hard per week",
    success_close="Time to dominate this week! 🔥",
    channel_close="Let's smash these weekly goals! 💥",
)

set_monthly_target_handler = _make_target_setter(
    target_type="monthly",
    label="Monthly",
    noun="month",
    example_args="40 20 8",
    usage_note="40 easy, 20 medium, 8 hard per month",
    success_close="Ready to conquer this month! 🏆",
    channel_close="Let's achieve greatness this month! 🌟",
)

def restrict_to_owner(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if config.OWNER_USER_ID is not None:
            user = update.effective_user
            if not user or user.id != config.OWNER_USER_ID:
                logger.warning(f"Unauthorized command access attempt from user ID: {user.id if user else 'Unknown'}")
                if update.message:
                    await update.message.reply_text("❌ Unauthorized: Only the bot owner can access this command.")
                return
        return await func(update, context, *args, **kwargs)
    return wrapper

def register_handlers(app: Application):
    """Registers all the message handlers for the bot."""
    app.add_handler(CommandHandler("help", restrict_to_owner(help_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("ping", restrict_to_owner(ping_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stats", restrict_to_owner(stats_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("mstats", restrict_to_owner(monthly_stats_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("wstats", restrict_to_owner(weekly_stats_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("pstats", restrict_to_owner(past_day_stats_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("pwstats", restrict_to_owner(past_week_stats_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("dset", restrict_to_owner(set_daily_target_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("wset", restrict_to_owner(set_weekly_target_handler), filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("mset", restrict_to_owner(set_monthly_target_handler), filters=filters.ChatType.PRIVATE))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the error and provides a specific message for conflict errors."""
    if isinstance(context.error, Conflict):
        logger.critical(
            "Conflict error detected. Another instance of the bot is already running. "
            "Please stop the other instance before starting a new one."
        )
    else:
        logger.error("Exception while handling an update:", exc_info=context.error) 
