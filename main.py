import asyncio
import os
import sys
from pyrogram import Client

import config
from database import init_db
from state_manager import (
    get_last_submission_id,
    save_last_submission_id,
    get_last_leetcode_timestamp,
    save_last_leetcode_timestamp
)
from codeforces import get_latest_submission_id, check_codeforces_submissions
from leetcode import get_latest_leetcode_submission_timestamp, check_leetcode_submissions
from bot import (
    schedule_daily_summary,
    test_codeforces_submission,
    test_leetcode_submission,
    add_fake_yesterday_entry,
    send_daily_summary,
    register_handlers
)

async def main():
    # Ensure the data directory exists
    os.makedirs("data", exist_ok=True)
    
    session_file = "data/cf_notifier_bot.session"

    # Handle session reset
    if "--new-session" in sys.argv:
        print("--- Detected --new-session flag. Removing old session file. ---")
        if os.path.exists(session_file):
            os.remove(session_file)

    app = Client(
        "data/cf_notifier_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN
    )

    init_db()
    register_handlers(app)

    if config.TEST_MODE:
        print("--- RUNNING IN TEST MODE ---")
        async with app:
            if config.TEST_MODE_STATS_ONLY:
                add_fake_yesterday_entry()
                await send_daily_summary(app)
            else:
                await test_codeforces_submission(app)
                await test_leetcode_submission(app)
        print("--- TEST MODE FINISHED ---")
        return

    # Initial setup on first run
    if get_last_submission_id() == 0:
        print("First run for Codeforces. Initializing with the latest submission ID...")
        latest_id = get_latest_submission_id()
        if latest_id:
            save_last_submission_id(latest_id)
            print(f"Initialized Codeforces. Will only report submissions newer than ID {latest_id}.")
        else:
            print("Could not fetch initial Codeforces submission ID. Will start from 0.")
    
    if get_last_leetcode_timestamp() == 0:
        print("First run for LeetCode. Initializing with the latest submission timestamp...")
        latest_ts = await get_latest_leetcode_submission_timestamp()
        if latest_ts:
            save_last_leetcode_timestamp(latest_ts)
            print(f"Initialized LeetCode. Will only report submissions newer than timestamp {latest_ts}.")
        else:
            print("Could not fetch initial LeetCode submission timestamp. Will start from 0.")

    async with app:
        print("Bot started! Checking for new submissions...")
        await asyncio.gather(
            check_codeforces_submissions(app),
            check_leetcode_submissions(app),
            schedule_daily_summary(app)
        )

if __name__ == "__main__":
    asyncio.run(main()) 