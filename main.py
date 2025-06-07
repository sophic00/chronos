import asyncio
import hashlib
import os
import time

import requests
from pyrogram import Client

import config

# --- Globals ---
LAST_SUBMISSION_ID_FILE = "last_submission_id.txt"
CODEFORCES_API_URL = "https://codeforces.com/api"


def get_last_submission_id():
    if os.path.exists(LAST_SUBMISSION_ID_FILE):
        with open(LAST_SUBMISSION_ID_FILE, "r") as f:
            content = f.read().strip()
            if content:
                return int(content)
    return 0


def save_last_submission_id(submission_id):
    with open(LAST_SUBMISSION_ID_FILE, "w") as f:
        f.write(str(submission_id))


def generate_api_sig(method_name, **kwargs):
    rand = "123456"  # 6-digit random string
    params = "&".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
    return hashlib.sha512(
        f"{rand}/{method_name}?{params}#{config.CF_API_SECRET}".encode("utf-8")
    ).hexdigest()


async def check_submissions(app: Client):
    while True:
        try:
            method_name = "user.status"
            params_for_sig = {
                "handle": config.CF_HANDLE,
                "from": 1,
                "count": 10,
                "apiKey": config.CF_API_KEY,
                "time": int(time.time()),
            }

            api_sig_hash = generate_api_sig(method_name, **params_for_sig)

            params = params_for_sig.copy()
            params["apiSig"] = "123456" + api_sig_hash

            response = requests.get(f"{CODEFORCES_API_URL}/{method_name}", params=params)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "OK":
                last_processed_id = get_last_submission_id()
                new_successful_submissions = []

                for submission in data["result"]:
                    if submission["id"] > last_processed_id and submission.get("verdict") == "OK":
                        new_successful_submissions.append(submission)

                if new_successful_submissions:
                    # Process oldest first to maintain order
                    for submission in sorted(new_successful_submissions, key=lambda x: x['creationTimeSeconds']):
                        problem = submission["problem"]
                        problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
                        
                        message = (
                            f"✅ **New Accepted Submission!**\n\n"
                            f"**Problem:** [{problem['name']}]({problem_url})\n"
                            f"**Language:** {submission['programmingLanguage']}\n"
                            f"**Time:** {submission['timeConsumedMillis']} ms\n"
                            f"**Memory:** {submission['memoryConsumedBytes'] // 1024} KB"
                        )
                        
                        await app.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True)
                        print(f"Sent notification for submission {submission['id']}")
                        save_last_submission_id(submission["id"])
                        await asyncio.sleep(1) # a small delay to avoid hitting rate limits when multiple submissions get accepted at once

            else:
                print(f"Codeforces API returned status: {data.get('comment')}")

        except requests.exceptions.RequestException as e:
            print(f"An error occurred with Codeforces API: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

        await asyncio.sleep(60)


async def main():
    app = Client(
        "cf_notifier_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN
    )

    async with app:
        print("Bot started! Checking for new submissions...")
        await check_submissions(app)

if __name__ == "__main__":
    asyncio.run(main()) 