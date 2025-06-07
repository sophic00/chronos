import asyncio
import sqlite3
from datetime import datetime, timedelta

import pytz
import requests
import httpx
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

import config
import constants
from database import get_daily_stats_from_db
from codeforces import get_latest_submission_id, generate_api_sig
from leetcode import get_latest_leetcode_submission_timestamp, get_leetcode_submission_details, get_leetcode_cookies, get_leetcode_headers

async def send_daily_summary(app: Client):
    print("Sending daily summary...")
    stats = get_daily_stats_from_db()
    cf_count = stats.get("codeforces", 0)
    lc_count = stats.get("leetcode", 0)
    total_count = cf_count + lc_count

    if total_count == 0:
        message = "yet another uneventful day."
    else:
        message = (
            f"**📊 Daily Summary**\n\n"
            f"yet another slightly eventful day:\n\n"
            f"**Codeforces:** {cf_count} unique problems\n"
            f"**LeetCode:** {lc_count} unique problems\n"
            f"**Total:** {total_count} unique problems solved today.\n\n"
        )
    
    await app.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True)
    print("Daily summary sent.")

async def schedule_daily_summary(app: Client):
    while True:
        now_utc = datetime.now(pytz.utc)
        tz = pytz.timezone(config.TIMEZONE)
        now_local = now_utc.astimezone(tz)
        
        target_time = now_local.replace(hour=23, minute=59, second=0, microsecond=0)
        if now_local > target_time:
            target_time += timedelta(days=1)
            
        wait_seconds = (target_time - now_local).total_seconds()
        print(f"Scheduler: Waiting {wait_seconds / 3600:.2f} hours until next summary.")
        await asyncio.sleep(wait_seconds)
        
        await send_daily_summary(app)
        
        await asyncio.sleep(60)

async def test_codeforces_submission(app: Client):
    print("--- Testing Codeforces Submission ---")
    try:
        method_name = "user.status"
        params_for_sig = {
            "handle": config.CF_HANDLE,
            "from": 1,
            "count": 1,
            "apiKey": config.CF_API_KEY,
            "time": int(time.time()),
        }
        api_sig_hash = generate_api_sig(method_name, **params_for_sig)
        params = params_for_sig.copy()
        params["apiSig"] = "123456" + api_sig_hash
        response = requests.get(constants.CODEFORCES_API_URL + f"/{method_name}", params=params)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "OK" and data["result"]:
            submission = data["result"][0]
            problem = submission["problem"]
            problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
            verdict = submission.get('verdict', 'N/A')
            message = (
                f"👾 **[TEST] Latest Submission** 👾\n\n"
                f"**Platform:** Codeforces\n"
                f"**Problem:** [{problem['name']}]({problem_url})\n"
                f"**Verdict:** {verdict}\n"
                f"**Language:** {submission['programmingLanguage']}\n"
                f"**Time:** {submission['timeConsumedMillis']} ms\n"
                f"**Memory:** {submission['memoryConsumedBytes'] // 1024} KB"
            )
            await app.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True)
            print(f"Sent Codeforces test notification for submission {submission['id']}.")
        else:
            print(f"Could not fetch latest Codeforces submission. Status: {data.get('comment')}")
    except Exception as e:
        print(f"An error occurred during Codeforces test: {e}")

async def test_leetcode_submission(app: Client):
    print("--- Testing LeetCode Submission ---")
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
            print(f"LeetCode API error on test fetch: {data['errors']}")
            return
        submissions = data.get("data", {}).get("recentAcSubmissionList", [])
        if submissions:
            sub = submissions[0]
            problem_url = f"https://leetcode.com/problems/{sub['titleSlug']}/"
            message = (
                f"👾 **[TEST] Latest Submission** 👾\n\n"
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
            await app.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True)
            print(f"Sent LeetCode test notification for submission ID {sub['id']}")
        else:
            print("Could not find any recent LeetCode submissions to test.")
    except Exception as e:
        print(f"An error occurred during LeetCode test: {e}")

def add_fake_yesterday_entry():
    print("--- Adding fake entry for yesterday's stats to test filtering ---")
    yesterday_date = (datetime.now(pytz.timezone(config.TIMEZONE)) - timedelta(days=1)).strftime("%Y-%m-%d")
    platform = "leetcode"
    problem_id = "3sum"
    with sqlite3.connect(constants.DB_FILE) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO solved_problems (platform, problem_id, first_solve_date) VALUES (?, ?, ?)",
                (platform, problem_id, yesterday_date)
            )
            conn.commit()
            print(f"Ensured fake test entry for '{problem_id}' exists for date {yesterday_date}.")
        except Exception as e:
            print(f"An error occurred while adding fake entry: {e}")

async def stats_handler(client: Client, message):
    """Replies with the current daily stats."""
    stats = get_daily_stats_from_db()
    cf_count = stats.get("codeforces", 0)
    lc_count = stats.get("leetcode", 0)
    total_count = cf_count + lc_count

    if total_count == 0:
        summary_message = "You haven't solved any new problems yet today. Let's get started! 💪"
    else:
        summary_message = (
            f"**📊 Today's Progress So Far**\n\n"
            f"Here's your summary for today:\n\n"
            f"**Codeforces:** {cf_count} unique problems\n"
            f"**LeetCode:** {lc_count} unique problems\n"
            f"**Total:** {total_count} unique problems solved today.\n\n"
        )
    
    await message.reply_text(summary_message, disable_web_page_preview=True)

async def ping_handler(client: Client, message):
    """Replies with a pong message."""
    await message.reply_text("Pong!")

def register_handlers(app: Client):
    """Registers all the message handlers for the bot."""
    app.add_handler(MessageHandler(ping_handler, filters=filters.command("ping") & filters.private))
    app.add_handler(MessageHandler(stats_handler, filters=filters.command("stats") & filters.private)) 