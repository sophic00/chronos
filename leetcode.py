import httpx
import asyncio
import logging

from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
import constants
from database import log_problem_solved
from state_manager import get_last_leetcode_timestamp, save_last_leetcode_timestamp

def get_leetcode_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://leetcode.com/problems/submissions/",
        "x-csrftoken": config.CSRF_TOKEN,
        "x-requested-with": "XMLHttpRequest",
    }

def get_leetcode_cookies():
    return {
        "LEETCODE_SESSION": config.LEETCODE_SESSION,
        "csrftoken": config.CSRF_TOKEN,
    }

async def get_latest_leetcode_submission_timestamp():
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
            response = await client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                logging.error(f"LeetCode API error on init: {data['errors']}")
                return 0
            submissions = data.get("data", {}).get("recentAcSubmissionList", [])
            if submissions:
                return int(submissions[0]["timestamp"])
        except httpx.RequestError as e:
            logging.error(f"An error occurred during initial LeetCode submission fetch: {e}")
    return 0

async def get_leetcode_submission_details(submission_id: int):
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
            response = await client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                logging.error(f"LeetCode API error on submission detail fetch: {data['errors']}")
                return None
            return data.get("data", {}).get("submissionDetails")
        except httpx.RequestError as e:
            logging.error(f"An error occurred during LeetCode submission detail fetch: {e}")
    return None

async def check_leetcode_submissions(context: ContextTypes.DEFAULT_TYPE):
    """Checks for new successful LeetCode submissions and sends notifications."""
    logging.info("Checking for new LeetCode submissions...")
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
            response = await client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        if "errors" in data:
            logging.error(f"LeetCode API returned an error: {data['errors']}")
            return

        last_timestamp = get_last_leetcode_timestamp()
        new_submissions = []
        submissions = data.get("data", {}).get("recentAcSubmissionList", [])
        if submissions:
            for sub in submissions:
                if int(sub["timestamp"]) > last_timestamp:
                    new_submissions.append(sub)
        
        if new_submissions:
            for sub in sorted(new_submissions, key=lambda x: int(x["timestamp"])):
                problem_url = f"https://leetcode.com/problems/{sub['titleSlug']}/"
                is_newly_solved = log_problem_solved(platform="leetcode", problem_id=sub["titleSlug"])
                
                message = (
                    f"👾 **New Accepted Submission!**\n\n"
                    f"**Platform:** LeetCode\n"
                    f"**Problem:** [{sub['title']}]({problem_url})\n"
                    f"**Language:** {sub['lang']}"
                )
                
                details = await get_leetcode_submission_details(int(sub['id']))
                if details and details.get('runtime') is not None and details.get('memory') is not None:
                    memory_kb = details['memory'] // 1024
                    message += f"\n**Runtime:** {details['runtime']} ms\n**Memory:** {memory_kb} KB"

                if is_newly_solved:
                    message += "\n\n*This is a new unique problem solved today!* 🎉"

                await context.bot.send_message(
                    config.CHANNEL_ID, 
                    message, 
                    disable_web_page_preview=True,
                    parse_mode=ParseMode.MARKDOWN
                )
                logging.info(f"Sent LeetCode notification for submission ID {sub['id']}")
                save_last_leetcode_timestamp(int(sub["timestamp"]))
                await asyncio.sleep(1) # Avoid rate-limiting
                
    except httpx.RequestError as e:
        logging.error(f"An error occurred with LeetCode API: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred in LeetCode check: {e}", exc_info=True)
