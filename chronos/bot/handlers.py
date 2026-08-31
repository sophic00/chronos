from datetime import datetime, timedelta
from functools import wraps
import calendar
import logging
import pytz
import io

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import Conflict

from ..config import settings as config
from ..config import constants
from ..data.database import get_daily_stats_from_db, get_monthly_stats_from_db, get_weekly_stats_from_db, get_past_day_stats_from_db, get_past_week_stats_from_db, set_leetcode_target, get_leetcode_target, set_value, get_daily_breakdown_from_db, get_current_streak
from ..integrations.leetcode import get_leetcode_submission_details, get_leetcode_cookies, get_leetcode_headers, get_leetcode_problem_difficulty
from .image_generator import generate_solve_card, generate_summary_card
from .messaging import format_bytes, prettify_language, escape_md, cf_rating_bands

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


def get_daily_summary_message(target_date=None) -> str:
    """Generates the daily summary message content for target_date (or today if None)."""
    if target_date is None:
        target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
    stats = get_daily_stats_from_db(target_date)
    summary_details, grand_total = _format_summary_message(stats, 'daily')

    if grand_total == 0:
        return "yet another uneventful day."
    
    date_str = target_date.strftime("%B %d, %Y")

    return (
        f"📊 *Daily Coding Report*\n"
        f"🗓️ *Date:* {date_str}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved Today:* {grand_total}"
    )

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE, target_date=None):
    """Sends the daily summary message to the channel."""
    logging.info("Sending daily summary...")
    if target_date is None:
        target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
        
    stats = get_daily_stats_from_db(target_date)
    summary_details, grand_total = _format_summary_message(stats, 'daily')
    
    if grand_total == 0:
        # Fallback to plain text "yet another uneventful day."
        message = "yet another uneventful day."
        await context.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        logging.info("Daily summary sent (no solves today).")
    else:
        date_str = target_date.strftime("%B %d, %Y")
        message = (
            f"📊 *Daily Coding Report*\n"
            f"🗓️ *Date:* {date_str}\n"
            f"🚀 *Progress Overview*\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{summary_details}\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🎯 *Grand Total Solved Today:* {grand_total}"
        )
        
        if config.SEND_AS_IMAGE:
            try:
                # Generate summary card
                image_bytes = generate_summary_card(
                    "daily", date_str, stats,
                    targets=get_leetcode_target('daily'),
                    extras=_build_summary_extras('daily', target_date)
                )
                
                # Send photo
                await context.bot.send_photo(
                    chat_id=config.CHANNEL_ID,
                    photo=io.BytesIO(image_bytes),
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN
                )
                logging.info("Daily summary sent as image.")
            except Exception as img_err:
                logging.error(f"Failed to generate/send daily summary image: {img_err}. Falling back to text.", exc_info=True)
                await context.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            await context.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            logging.info("Daily summary sent.")
            
    # Track the sent summary date in the database
    set_value("last_sent_daily_summary_date", target_date.isoformat())


async def test_codeforces_submission(app: Application):
    """Fetches the latest CF submission and sends a test notification."""
    logging.info("--- Testing Codeforces Submission ---")
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
                    image_bytes = generate_solve_card(
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
                    logging.info(f"Sent Codeforces test photo notification for submission {submission['id']}.")
                except Exception as img_err:
                    logging.error(f"Failed to generate/send Codeforces test image: {img_err}. Falling back to text.", exc_info=True)
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
            logging.info(f"Sent Codeforces test notification for submission {submission['id']}.")
        else:
            logging.warning(f"Could not fetch latest Codeforces submission. Status: {data.get('comment')}")
    except httpx.RequestError as e:
        logging.error(f"An error occurred with Codeforces API during test: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(f"Codeforces API returned error status {e.response.status_code} during test: {e}")
    except httpx.TimeoutException as e:
        logging.error(f"Codeforces API request timed out during test: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during Codeforces test: {e}", exc_info=True)


async def test_leetcode_submission(app: Application):
    """Fetches the latest LC submission and sends a test notification."""
    logging.info("--- Testing LeetCode Submission ---")
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
            logging.error(f"LeetCode API error on test fetch: {data['errors']}")
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
                    image_bytes = generate_solve_card(
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
                    logging.info(f"Sent LeetCode test photo notification for submission {sub['id']}")
                except Exception as img_err:
                    logging.error(f"Failed to generate/send LeetCode test image: {img_err}. Falling back to text.", exc_info=True)
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
            logging.info(f"Sent LeetCode test notification for submission ID {sub['id']}")
        else:
            logging.warning("Could not find any recent LeetCode submissions to test.")
    except Exception as e:
        logging.error(f"An error occurred during LeetCode test: {e}", exc_info=True)


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with the current daily stats."""
    stats = get_daily_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'daily')

    if grand_total == 0:
        # Check if there are daily targets set
        targets = get_leetcode_target('daily')
        if targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0:
            target_summary = (
                f"📊 *Today's Progress*\n"
                f"🎯 *Daily Targets:*\n"
                f"🟢 Easy: {_format_progress_bar(0, targets['easy'])}\n"
                f"🟡 Medium: {_format_progress_bar(0, targets['medium'])}\n"
                f"🔴 Hard: {_format_progress_bar(0, targets['hard'])}\n\n"
                f"You haven't solved any new problems yet today. Let's get started! 💪"
            )
            await update.message.reply_text(target_summary, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            summary_message = "You haven't solved any new problems yet today. Let's get started! 💪"
            await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    local_tz = pytz.timezone(config.TIMEZONE)
    date_str = datetime.now(local_tz).strftime("%B %d, %Y")

    summary_message = (
        f"📊 *Today's Progress So Far*\n"
        f"🗓️ *Date:* {date_str}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved Today:* {grand_total}"
    )
    
    if config.SEND_AS_IMAGE:
        try:
            today = datetime.now(local_tz).date()
            image_bytes = generate_summary_card(
                "daily", date_str, stats,
                targets=get_leetcode_target('daily'),
                extras=_build_summary_extras('daily', today)
            )
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=summary_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as img_err:
            logging.error(f"Failed to generate/send stats summary image: {img_err}. Falling back to text.", exc_info=True)
            await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


async def monthly_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with the current monthly stats."""
    stats = get_monthly_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'monthly')

    local_tz = pytz.timezone(config.TIMEZONE)
    current_date = datetime.now(local_tz)
    month_year = current_date.strftime("%B %Y")

    if grand_total == 0:
        # Check if there are monthly targets set
        targets = get_leetcode_target('monthly')
        if targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0:
            target_summary = (
                f"📊 *Monthly Progress Report*\n"
                f"🗓️ *Period:* {month_year}\n"
                f"🎯 *Monthly Targets:*\n"
                f"🟢 Easy: {_format_progress_bar(0, targets['easy'])}\n"
                f"🟡 Medium: {_format_progress_bar(0, targets['medium'])}\n"
                f"🔴 Hard: {_format_progress_bar(0, targets['hard'])}\n\n"
                f"You haven't solved any new problems this month yet. Let's get started! 💪"
            )
            await update.message.reply_text(target_summary, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            summary_message = "You haven't solved any new problems this month yet. Let's get started! 💪"
            await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    summary_message = (
        f"📊 *Monthly Progress Report*\n"
        f"🗓️ *Period:* {month_year}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved This Month:* {grand_total}"
    )
    
    if config.SEND_AS_IMAGE:
        try:
            image_bytes = generate_summary_card(
                "monthly", month_year, stats,
                targets=get_leetcode_target('monthly'),
                extras=_build_summary_extras('monthly', current_date.date())
            )
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=summary_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as img_err:
            logging.error(f"Failed to generate/send monthly stats summary image: {img_err}. Falling back to text.", exc_info=True)
            await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


async def weekly_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with the current weekly stats."""
    stats = get_weekly_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'weekly')

    local_tz = pytz.timezone(config.TIMEZONE)
    current_date = datetime.now(local_tz)
    # Calculate week range (Monday to Sunday)
    days_since_monday = current_date.weekday()
    start_of_week = current_date - timedelta(days=days_since_monday)
    end_of_week = start_of_week + timedelta(days=6)
    week_range = f"{start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d, %Y')}"

    if grand_total == 0:
        # Check if there are weekly targets set
        targets = get_leetcode_target('weekly')
        if targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0:
            target_summary = (
                f"📊 *Weekly Progress Report*\n"
                f"🗓️ *Period:* {week_range}\n"
                f"🎯 *Weekly Targets:*\n"
                f"🟢 Easy: {_format_progress_bar(0, targets['easy'])}\n"
                f"🟡 Medium: {_format_progress_bar(0, targets['medium'])}\n"
                f"🔴 Hard: {_format_progress_bar(0, targets['hard'])}\n\n"
                f"You haven't solved any new problems this week yet. Let's get started! 💪"
            )
            await update.message.reply_text(target_summary, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            summary_message = "You haven't solved any new problems this week yet. Let's get started! 💪"
            await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    summary_message = (
        f"📊 *Weekly Progress Report*\n"
        f"🗓️ *Period:* {week_range}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved This Week:* {grand_total}"
    )
    
    if config.SEND_AS_IMAGE:
        try:
            image_bytes = generate_summary_card(
                "weekly", week_range, stats,
                targets=get_leetcode_target('weekly'),
                extras=_build_summary_extras('weekly', current_date.date())
            )
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=summary_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as img_err:
            logging.error(f"Failed to generate/send weekly stats summary image: {img_err}. Falling back to text.", exc_info=True)
            await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


async def past_day_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with yesterday's stats."""
    stats = get_past_day_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'daily')

    local_tz = pytz.timezone(config.TIMEZONE)
    yesterday = datetime.now(local_tz) - timedelta(days=1)
    date_str = yesterday.strftime("%B %d, %Y")

    if grand_total == 0:
        # Check if there are daily targets set for reference
        targets = get_leetcode_target('daily')
        if targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0:
            target_summary = (
                f"📊 *Yesterday's Progress Report*\n"
                f"🗓️ *Date:* {date_str}\n"
                f"🎯 *Daily Targets (for reference):*\n"
                f"🟢 Easy: {_format_progress_bar(0, targets['easy'])}\n"
                f"🟡 Medium: {_format_progress_bar(0, targets['medium'])}\n"
                f"🔴 Hard: {_format_progress_bar(0, targets['hard'])}\n\n"
                f"You didn't solve any new problems yesterday. 📅"
            )
            await update.message.reply_text(target_summary, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            summary_message = f"You didn't solve any new problems on {date_str}. 📅"
            await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    summary_message = (
        f"📊 *Yesterday's Progress Report*\n"
        f"🗓️ *Date:* {date_str}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved Yesterday:* {grand_total}"
    )
    
    if config.SEND_AS_IMAGE:
        try:
            image_bytes = generate_summary_card(
                "daily", date_str, stats,
                targets=get_leetcode_target('daily'),
                extras=_build_summary_extras('daily', yesterday.date())
            )
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=summary_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as img_err:
            logging.error(f"Failed to generate/send yesterday's stats summary image: {img_err}. Falling back to text.", exc_info=True)
            await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


async def past_week_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with last week's stats."""
    stats = get_past_week_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'weekly')

    # Calculate last week's date range (Monday to Sunday)
    local_tz = pytz.timezone(config.TIMEZONE)
    current_date = datetime.now(local_tz)
    days_since_monday = current_date.weekday()
    start_of_current_week = current_date - timedelta(days=days_since_monday)
    start_of_last_week = start_of_current_week - timedelta(days=7)
    end_of_last_week = start_of_current_week - timedelta(days=1)
    week_range = f"{start_of_last_week.strftime('%b %d')} - {end_of_last_week.strftime('%b %d, %Y')}"

    if grand_total == 0:
        # Check if there are weekly targets set for reference
        targets = get_leetcode_target('weekly')
        if targets['easy'] > 0 or targets['medium'] > 0 or targets['hard'] > 0:
            target_summary = (
                f"📊 *Last Week's Progress Report*\n"
                f"🗓️ *Period:* {week_range}\n"
                f"🎯 *Weekly Targets (for reference):*\n"
                f"🟢 Easy: {_format_progress_bar(0, targets['easy'])}\n"
                f"🟡 Medium: {_format_progress_bar(0, targets['medium'])}\n"
                f"🔴 Hard: {_format_progress_bar(0, targets['hard'])}\n\n"
                f"You didn't solve any new problems last week. 📅"
            )
            await update.message.reply_text(target_summary, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
        else:
            summary_message = f"You didn't solve any new problems last week ({week_range}). 📅"
            await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    summary_message = (
        f"📊 *Last Week's Progress Report*\n"
        f"🗓️ *Period:* {week_range}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved Last Week:* {grand_total}"
    )
    
    if config.SEND_AS_IMAGE:
        try:
            image_bytes = generate_summary_card(
                "weekly", week_range, stats,
                targets=get_leetcode_target('weekly'),
                extras=_build_summary_extras('weekly', start_of_last_week.date())
            )
            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=summary_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as img_err:
            logging.error(f"Failed to generate/send last week's stats summary image: {img_err}. Falling back to text.", exc_info=True)
            await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


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


async def set_daily_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets daily LeetCode targets. Usage: /dset <easy> <medium> <hard>"""
    if len(context.args) != 3:
        await update.message.reply_text(
            "❌ *Usage:* `/dset <easy> <medium> <hard>`\n"
            "Example: `/dset 2 1 0` (2 easy, 1 medium, 0 hard per day)",
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
        
        success = set_leetcode_target('daily', easy, medium, hard)
        
        if success:
            # Send confirmation to user
            await update.message.reply_text(
                f"✅ *Daily LeetCode Target Set!*\n\n"
                f"🟢 *Easy:* {easy} problems/day\n"
                f"🟡 *Medium:* {medium} problems/day\n"
                f"🔴 *Hard:* {hard} problems/day\n\n"
                f"Good luck crushing your daily goals! 💪",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send notification to channel
            channel_message = (
                f"🎯 *New Daily Target Set!*\n\n"
                f"📊 *LeetCode Daily Goals:*\n"
                f"🟢 Easy: {easy} problems\n"
                f"🟡 Medium: {medium} problems\n"
                f"🔴 Hard: {hard} problems\n\n"
                f"Let's achieve these goals every day! 🚀"
            )
            await context.bot.send_message(
                config.CHANNEL_ID, 
                channel_message, 
                disable_web_page_preview=True, 
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Failed to set daily target. Please try again.")
            
    except ValueError:
        await update.message.reply_text("❌ All arguments must be valid integers.")


async def set_weekly_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets weekly LeetCode targets. Usage: /wset <easy> <medium> <hard>"""
    if len(context.args) != 3:
        await update.message.reply_text(
            "❌ *Usage:* `/wset <easy> <medium> <hard>`\n"
            "Example: `/wset 10 5 2` (10 easy, 5 medium, 2 hard per week)",
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
        
        success = set_leetcode_target('weekly', easy, medium, hard)
        
        if success:
            # Send confirmation to user
            await update.message.reply_text(
                f"✅ *Weekly LeetCode Target Set!*\n\n"
                f"🟢 *Easy:* {easy} problems/week\n"
                f"🟡 *Medium:* {medium} problems/week\n"
                f"🔴 *Hard:* {hard} problems/week\n\n"
                f"Time to dominate this week! 🔥",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send notification to channel
            channel_message = (
                f"🎯 *New Weekly Target Set!*\n\n"
                f"📊 *LeetCode Weekly Goals:*\n"
                f"🟢 Easy: {easy} problems\n"
                f"🟡 Medium: {medium} problems\n"
                f"🔴 Hard: {hard} problems\n\n"
                f"Let's smash these weekly goals! 💥"
            )
            await context.bot.send_message(
                config.CHANNEL_ID, 
                channel_message, 
                disable_web_page_preview=True, 
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Failed to set weekly target. Please try again.")
            
    except ValueError:
        await update.message.reply_text("❌ All arguments must be valid integers.")


async def set_monthly_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets monthly LeetCode targets. Usage: /mset <easy> <medium> <hard>"""
    if len(context.args) != 3:
        await update.message.reply_text(
            "❌ *Usage:* `/mset <easy> <medium> <hard>`\n"
            "Example: `/mset 40 20 8` (40 easy, 20 medium, 8 hard per month)",
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
        
        success = set_leetcode_target('monthly', easy, medium, hard)
        
        if success:
            # Send confirmation to user
            await update.message.reply_text(
                f"✅ *Monthly LeetCode Target Set!*\n\n"
                f"🟢 *Easy:* {easy} problems/month\n"
                f"🟡 *Medium:* {medium} problems/month\n"
                f"🔴 *Hard:* {hard} problems/month\n\n"
                f"Ready to conquer this month! 🏆",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send notification to channel
            channel_message = (
                f"🎯 *New Monthly Target Set!*\n\n"
                f"📊 *LeetCode Monthly Goals:*\n"
                f"🟢 Easy: {easy} problems\n"
                f"🟡 Medium: {medium} problems\n"
                f"🔴 Hard: {hard} problems\n\n"
                f"Let's achieve greatness this month! 🌟"
            )
            await context.bot.send_message(
                config.CHANNEL_ID, 
                channel_message, 
                disable_web_page_preview=True, 
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Failed to set monthly target. Please try again.")
            
    except ValueError:
        await update.message.reply_text("❌ All arguments must be valid integers.")

def restrict_to_owner(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if config.OWNER_USER_ID is not None:
            user = update.effective_user
            if not user or user.id != config.OWNER_USER_ID:
                logging.warning(f"Unauthorized command access attempt from user ID: {user.id if user else 'Unknown'}")
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
        logging.critical(
            "Conflict error detected. Another instance of the bot is already running. "
            "Please stop the other instance before starting a new one."
        )
    else:
        logging.error("Exception while handling an update:", exc_info=context.error) 
