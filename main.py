import asyncio
import hashlib
import os
import time

import httpx
import requests
from pyrogram import Client

import config

# --- Globals ---
LAST_SUBMISSION_ID_FILE = "last_submission_id.txt"
CODEFORCES_API_URL = "https://codeforces.com/api"
LAST_LEETCODE_SUBMISSION_TIMESTAMP_FILE = "last_leetcode_submission_timestamp.txt"
LEETCODE_API_URL = "https://leetcode.com/graphql"


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


def get_last_leetcode_timestamp():
    if os.path.exists(LAST_LEETCODE_SUBMISSION_TIMESTAMP_FILE):
        with open(LAST_LEETCODE_SUBMISSION_TIMESTAMP_FILE, "r") as f:
            content = f.read().strip()
            if content:
                return int(content)
    return 0


def save_last_leetcode_timestamp(timestamp):
    with open(LAST_LEETCODE_SUBMISSION_TIMESTAMP_FILE, "w") as f:
        f.write(str(timestamp))


def get_leetcode_headers():
    """Returns a dictionary of headers for LeetCode API requests."""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://leetcode.com/problems/submissions/",
        "x-csrftoken": config.CSRF_TOKEN,
        "x-requested-with": "XMLHttpRequest",
    }


def get_leetcode_cookies():
    """Returns a dictionary of cookies for LeetCode API requests."""
    return {
        "LEETCODE_SESSION": config.LEETCODE_SESSION,
        "csrftoken": config.CSRF_TOKEN,
    }


def generate_api_sig(method_name, **kwargs):
    rand = "123456"  # 6-digit random string
    params = "&".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
    return hashlib.sha512(
        f"{rand}/{method_name}?{params}#{config.CF_API_SECRET}".encode("utf-8")
    ).hexdigest()


def get_latest_submission_id():
    """Fetches the ID of the most recent submission from Codeforces."""
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

        response = requests.get(f"{CODEFORCES_API_URL}/{method_name}", params=params)
        response.raise_for_status()
        data = response.json()

        if data["status"] == "OK" and data["result"]:
            return data["result"][0]["id"]
        elif data["status"] != "OK":
            print(f"Codeforces API error on init: {data.get('comment')}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred during initial submission fetch: {e}")
    return 0


async def get_latest_leetcode_submission_timestamp():
    """Fetches the timestamp of the most recent AC LeetCode submission."""
    graphql_query = {
        "query": """
            query recentAcSubmissions($username: String!, $limit: Int!) {
                recentAcSubmissionList(username: $username, limit: $limit) {
                    timestamp
                }
            }
        """,
        "variables": {
            "username": config.LEETCODE_USERNAME,
            "limit": 1
        }
    }
    cookies = get_leetcode_cookies()
    headers = get_leetcode_headers()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"LeetCode API error on init: {data['errors']}")
                return 0

            submissions = data.get("data", {}).get("recentAcSubmissionList", [])
            if submissions:
                return int(submissions[0]["timestamp"])
        except httpx.RequestError as e:
            print(f"An error occurred during initial LeetCode submission fetch: {e}")
    return 0


async def get_leetcode_submission_details(submission_id: int):
    """Fetches details for a specific LeetCode submission."""
    graphql_query = {
        "query": """
            query submissionDetails($submissionId: Int!) {
                submissionDetails(submissionId: $submissionId) {
                    runtime
                    memory
                }
            }
        """,
        "variables": {"submissionId": submission_id},
    }
    cookies = get_leetcode_cookies()
    headers = get_leetcode_headers()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                print(f"LeetCode API error on submission detail fetch: {data['errors']}")
                return None
            return data.get("data", {}).get("submissionDetails")
        except httpx.RequestError as e:
            print(f"An error occurred during LeetCode submission detail fetch: {e}")
    return None


async def check_codeforces_submissions(app: Client):
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
            print(f"An unexpected error occurred in Codeforces check: {e}")

        await asyncio.sleep(60)


async def check_leetcode_submissions(app: Client):
    """Checks for new AC LeetCode submissions and sends notifications."""
    while True:
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
            "variables": {
                "username": config.LEETCODE_USERNAME,
                "limit": 15
            }
        }
        cookies = get_leetcode_cookies()
        headers = get_leetcode_headers()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    print(f"LeetCode API returned an error: {data['errors']}")
                else:
                    last_timestamp = get_last_leetcode_timestamp()
                    new_submissions = []

                    submissions = data.get("data", {}).get("recentAcSubmissionList", [])
                    for sub in submissions:
                        if int(sub["timestamp"]) > last_timestamp:
                            new_submissions.append(sub)

                    if new_submissions:
                        for sub in sorted(new_submissions, key=lambda x: int(x["timestamp"])):
                            problem_url = f"https://leetcode.com/problems/{sub['titleSlug']}/"
                            message = (
                                f"**✅ Solved on LeetCode:** [{sub['title']}]({problem_url})\n\n"
                                f"**Language:** {sub['lang']}"
                            )
                            
                            details = await get_leetcode_submission_details(int(sub['id']))
                            if details and details.get('runtime') is not None and details.get('memory') is not None:
                                memory_kb = details['memory'] // 1024
                                message += f"\n**Runtime:** {details['runtime']} ms\n**Memory:** {memory_kb} KB"

                            await app.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True)
                            print(f"Sent LeetCode notification for submission ID {sub['id']}")
                            save_last_leetcode_timestamp(int(sub["timestamp"]))
                            await asyncio.sleep(1)

        except httpx.RequestError as e:
            print(f"An error occurred with LeetCode API: {e}")
        except Exception as e:
            print(f"An unexpected error occurred in LeetCode check: {e}")
        
        await asyncio.sleep(60)


async def test_codeforces_submission(app: Client):
    """Fetches the latest Codeforces submission and sends a test notification."""
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
        response = requests.get(f"{CODEFORCES_API_URL}/{method_name}", params=params)
        response.raise_for_status()
        data = response.json()

        if data["status"] == "OK" and data["result"]:
            submission = data["result"][0]
            problem = submission["problem"]
            problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
            verdict = submission.get('verdict', 'N/A')
            message = (
                f"**[TEST] Latest Codeforces Submission:**\n"
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
    """Fetches the latest LeetCode submission and sends a test notification."""
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
            response = await client.post(LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
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
                f"**[TEST] Latest LeetCode Submission:**\n"
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


async def main():
    app = Client(
        "cf_notifier_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN
    )

    # # --- TEST MODE ---
    # # To test, set TEST_MODE = True in config.py and uncomment the following lines.
    # # It will send one notification for the latest submission on each platform and then exit.
    if config.TEST_MODE:
        print("--- RUNNING IN TEST MODE ---")
        async with app:
            await test_codeforces_submission(app)
            await test_leetcode_submission(app)
        print("--- TEST MODE FINISHED ---")
        return  # Exit after testing
    # # --- END TEST MODE ---

    # Initialize last submission ID on first run for Codeforces
    if not os.path.exists(LAST_SUBMISSION_ID_FILE):
        print("First run detected for Codeforces. Initializing with the latest submission ID...")
        latest_id = get_latest_submission_id()
        if latest_id:
            save_last_submission_id(latest_id)
            print(f"Initialized Codeforces. Will only report submissions newer than ID {latest_id}.")
        else:
            print("Could not fetch initial Codeforces submission ID. Will start from 0.")
    
    # Initialize last submission timestamp on first run for LeetCode
    if not os.path.exists(LAST_LEETCODE_SUBMISSION_TIMESTAMP_FILE):
        print("First run detected for LeetCode. Initializing with the latest submission timestamp...")
        latest_ts = await get_latest_leetcode_submission_timestamp()
        if latest_ts:
            save_last_leetcode_timestamp(latest_ts)
            print(f"Initialized LeetCode. Will only report submissions newer than timestamp {latest_ts}.")
        else:
            print("Could not fetch initial LeetCode submission timestamp. Will start from 0.")

    async with app:
        print("Bot started! Checking for new submissions on Codeforces and LeetCode...")
        await asyncio.gather(
            check_codeforces_submissions(app),
            check_leetcode_submissions(app)
        )

if __name__ == "__main__":
    asyncio.run(main()) 