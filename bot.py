from datetime import datetime
import logging
import time as time_module

import requests
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import Conflict

import config
import constants
from database import get_daily_stats_from_db, get_monthly_stats_from_db
from codeforces import generate_api_sig
from leetcode import get_leetcode_submission_details, get_leetcode_cookies, get_leetcode_headers

def _format_summary_message(stats: dict) -> tuple[str, int]:
    """Formats the complete summary message from a stats dictionary."""
    lc_stats = stats.get("leetcode", {})
    cf_stats = stats.get("codeforces", {})
    
    # LeetCode stats
    lc_easy = 0
    lc_medium = 0
    lc_hard = 0
    lc_na = 0

    for difficulty, count in lc_stats.items():
        if difficulty == "Easy":
            lc_easy += count
        elif difficulty == "Medium":
            lc_medium += count
        elif difficulty == "Hard":
            lc_hard += count
        else:
            lc_na += count
    
    lc_total = sum(lc_stats.values())

    # Codeforces stats aggregation
    cf_800_1000 = 0
    cf_1100_1300 = 0
    cf_1400_1600 = 0
    cf_1700_plus = 0
    cf_na = 0
    
    for rating_str, count in cf_stats.items():
        if str(rating_str).isdigit():
            rating = int(rating_str)
            if 800 <= rating <= 1000:
                cf_800_1000 += count
            elif 1100 <= rating <= 1300:
                cf_1100_1300 += count
            elif 1400 <= rating <= 1600:
                cf_1400_1600 += count
            elif rating >= 1700:
                cf_1700_plus += count
            else: # For ratings outside defined bands but still digits
                cf_na += count 
        else:
            cf_na += count
            
    cf_total = sum(cf_stats.values())
    grand_total = lc_total + cf_total
    
    message_parts = []
    
    if lc_total > 0:
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
            f"↦ 🥉 *800–1000:* {cf_800_1000}\n"
            f"↦ 🥈 *1100–1300:* {cf_1100_1300}\n"
            f"↦ 🥇 *1400–1600:* {cf_1400_1600}\n"
            f"↦ 🏆 *1700+:* {cf_1700_plus}\n"
            f"↦ ❓ *Unrated/Other:* {cf_na}\n"
            f"✅ *Total Codeforces:* {cf_total} problems"
        )
        message_parts.append(cf_summary)

    details = "\n\n━━━━━━━━━━━━━━━\n\n".join(message_parts)
    return details, grand_total


def get_daily_summary_message() -> str:
    """Generates the daily summary message content."""
    stats = get_daily_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats)

    if grand_total == 0:
        return "yet another uneventful day."
    
    date_str = datetime.now().strftime("%B %d, %Y")

    return (
        f"📊 *Daily Coding Report*\n"
        f"🗓️ *Date:* {date_str}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved Today:* {grand_total}"
    )

async def send_daily_summary(context: ContextTypes.DEFAULT_TYPE):
    """Sends the daily summary message to the channel."""
    logging.info("Sending daily summary...")
    message = get_daily_summary_message()
    await context.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    logging.info("Daily summary sent.")


async def test_codeforces_submission(app: Application):
    """Fetches the latest CF submission and sends a test notification."""
    logging.info("--- Testing Codeforces Submission ---")
    try:
        method_name = "user.status"
        params_for_sig = {
            "handle": config.CF_HANDLE,
            "from": 1,
            "count": 1,
            "apiKey": config.CF_API_KEY,
            "time": int(time_module.time()),
        }
        api_sig_hash = generate_api_sig(method_name, **params_for_sig)
        params = params_for_sig.copy()
        params["apiSig"] = "123456" + api_sig_hash
        
        # Note: requests is synchronous, consider httpx for async
        response = requests.get(constants.CODEFORCES_API_URL + f"/{method_name}", params=params)
        response.raise_for_status()
        data = response.json()

        if data["status"] == "OK" and data["result"]:
            submission = data["result"][0]
            problem = submission["problem"]
            problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
            verdict = submission.get('verdict', 'N/A')
            message = (
                f"👾 *[TEST] Latest Submission* 👾\n\n"
                f"**Platform:** Codeforces\n"
                f"**Problem:** [{problem['name']}]({problem_url})\n"
                f"**Verdict:** {verdict}\n"
                f"**Language:** {submission['programmingLanguage']}\n"
                f"**Time:** {submission['timeConsumedMillis']} ms\n"
                f"**Memory:** {submission['memoryConsumedBytes'] // 1024} KB"
            )
            await app.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            logging.info(f"Sent Codeforces test notification for submission {submission['id']}.")
        else:
            logging.warning(f"Could not fetch latest Codeforces submission. Status: {data.get('comment')}")
    except Exception as e:
        logging.error(f"An error occurred during Codeforces test: {e}", exc_info=True)


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
            message = (
                f"👾 *[TEST] Latest Submission* 👾\n\n"
                f"**Platform:** LeetCode\n"
                f"**Problem:** [{sub['title']}]({problem_url})\n"
                f"**Language:** {sub['lang']}"
            )
            details = await get_leetcode_submission_details(int(sub['id']))
            if details and details.get('runtime') is not None and details.get('memory') is not None:
                memory_kb = details['memory'] // 1024
                message += f"\n**Runtime:** {details['runtime']} ms\n**Memory:** {memory_kb} KB"
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
    summary_details, grand_total = _format_summary_message(stats)

    if grand_total == 0:
        summary_message = "You haven't solved any new problems yet today. Let's get started! 💪"
        await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    date_str = datetime.now().strftime("%B %d, %Y")

    summary_message = (
        f"📊 *Today's Progress So Far*\n"
        f"🗓️ *Date:* {date_str}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved Today:* {grand_total}"
    )
    
    await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

async def monthly_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with the current monthly stats."""
    stats = get_monthly_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats)

    if grand_total == 0:
        summary_message = "You haven't solved any new problems this month yet. Let's get started! 💪"
        await update.message.reply_text(summary_message, disable_web_page_preview=True)
        return

    current_date = datetime.now()
    month_year = current_date.strftime("%B %Y")

    summary_message = (
        f"📊 *Monthly Progress Report*\n"
        f"🗓️ *Period:* {month_year}\n"
        f"🚀 *Progress Overview*\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{summary_details}\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Grand Total Solved This Month:* {grand_total}"
    )
    
    await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with a pong message."""
    await update.message.reply_text("Pong!")

def register_handlers(app: Application):
    """Registers all the message handlers for the bot."""
    app.add_handler(CommandHandler("ping", ping_handler, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stats", stats_handler, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("mstats", monthly_stats_handler, filters=filters.ChatType.PRIVATE))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the error and provides a specific message for conflict errors."""
    if isinstance(context.error, Conflict):
        logging.critical(
            "Conflict error detected. Another instance of the bot is already running. "
            "Please stop the other instance before starting a new one."
        )
    else:
        logging.error("Exception while handling an update:", exc_info=context.error) 
