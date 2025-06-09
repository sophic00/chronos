import asyncio
import sqlite3
from datetime import datetime, timedelta, time
import logging
import time as time_module

import pytz
import requests
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from telegram.constants import ParseMode
from telegram.error import Conflict

import config
import constants
from database import get_daily_stats_from_db
from codeforces import get_latest_submission_id, generate_api_sig
from leetcode import get_latest_leetcode_submission_timestamp, get_leetcode_submission_details, get_leetcode_cookies, get_leetcode_headers

def _format_platform_stats(platform_name: str, stats: dict) -> str:
    """Formats the stats string for a single platform."""
    if not stats:
        return f"**{platform_name}:** 0 unique problems\n"

    total = sum(stats.values())
    
    # Sort ratings: numerical for CF, predefined for LC
    if platform_name == "LeetCode":
        rating_order = {"Easy": 0, "Medium": 1, "Hard": 2}
        sorted_ratings = sorted(stats.keys(), key=lambda r: rating_order.get(r, 99))
    else: # Codeforces
        sorted_ratings = sorted(stats.keys(), key=lambda r: int(r) if r.isdigit() else 9999)

    details = [f"{rating}: {stats[rating]}" for rating in sorted_ratings]
    return f"**{platform_name}:** {total} unique problems ({', '.join(details)})\n"


def get_daily_summary_message() -> str:
    """Generates the daily summary message content."""
    stats = get_daily_stats_from_db()
    
    total_count = sum(sum(p.values()) for p in stats.values())

    if total_count == 0:
        return "yet another uneventful day."
    else:
        cf_stats = _format_platform_stats("Codeforces", stats.get("codeforces", {}))
        lc_stats = _format_platform_stats("LeetCode", stats.get("leetcode", {}))
        return (
            f"**📊 Daily Summary**\n\n"
            f"yet another slightly eventful day:\n\n"
            f"{cf_stats}"
            f"{lc_stats}"
            f"**Total:** {total_count} unique problems solved today.\n\n"
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
    total_count = sum(sum(p.values()) for p in stats.values())

    if total_count == 0:
        summary_message = "You haven't solved any new problems yet today. Let's get started! 💪"
    else:
        cf_stats = _format_platform_stats("Codeforces", stats.get("codeforces", {}))
        lc_stats = _format_platform_stats("LeetCode", stats.get("leetcode", {}))
        summary_message = (
            f"**📊 Today's Progress So Far**\n\n"
            f"Here's your summary for today:\n\n"
            f"{cf_stats}"
            f"{lc_stats}"
            f"**Total:** {total_count} unique problems solved today.\n\n"
        )
    
    await update.message.reply_text(summary_message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with a pong message."""
    await update.message.reply_text("Pong!")

def register_handlers(app: Application):
    """Registers all the message handlers for the bot."""
    app.add_handler(CommandHandler("ping", ping_handler, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stats", stats_handler, filters=filters.ChatType.PRIVATE))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the error and provides a specific message for conflict errors."""
    if isinstance(context.error, Conflict):
        logging.critical(
            "Conflict error detected. Another instance of the bot is already running. "
            "Please stop the other instance before starting a new one."
        )
    else:
        logging.error("Exception while handling an update:", exc_info=context.error) 