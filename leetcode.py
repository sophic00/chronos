import httpx
import asyncio
import logging

from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
import constants
from database import log_problem_solved
from state_manager import get_last_leetcode_timestamp, save_last_leetcode_timestamp
from messaging import format_new_solve_message

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

async def get_leetcode_problem_difficulty(title_slug: str):
    graphql_query = {
        "query": """
            query questionData($titleSlug: String!) {
                question(titleSlug: $titleSlug) {
                    difficulty
                }
            }
        """,
        "variables": {"titleSlug": title_slug},
    }
    cookies = get_leetcode_cookies()
    headers = get_leetcode_headers()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                logging.error(f"LeetCode API error on problem difficulty fetch: {data['errors']}")
                return None
            return data.get("data", {}).get("question", {}).get("difficulty")
        except httpx.RequestError as e:
            logging.error(f"An error occurred during LeetCode problem difficulty fetch: {e}")
    return None

async def get_submission_code(submission_id: int) -> str:
    """Gets the code for a LeetCode submission."""
    graphql_query = {
        "query": """
            query submissionDetails($submissionId: Int!) {
                submissionDetails(submissionId: $submissionId) {
                    code
                }
            }
        """,
        "variables": {
            "submissionId": submission_id
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
                logging.error(f"LeetCode API error getting submission code: {data['errors']}")
                return ""
            return data.get("data", {}).get("submissionDetails", {}).get("code", "")
        except httpx.RequestError as e:
            logging.error(f"Error getting submission code: {e}")
            return ""

def parse_submission_code(code: str) -> str:
    """Parses the submission code to extract the relevant part."""
    if not code:
        return ""
    
    # Check if it's a LeetCode submission with @lc markers
    start_marker = "// @lc code=start"
    end_marker = "// @lc code=end"
    
    if start_marker in code and end_marker in code:
        start_idx = code.find(start_marker) + len(start_marker)
        end_idx = code.find(end_marker)
        if start_idx != -1 and end_idx != -1:
            code = code[start_idx:end_idx].strip()
    
    # Remove any leading/trailing whitespace and newlines
    return code.strip()

def get_language_extension(language: str) -> str:
    """Maps LeetCode language names to file extensions for syntax highlighting."""
    language_map = {
        "cpp": "cpp",
        "java": "java",
        "python": "python",
        "python3": "python",
        "c": "c",
        "csharp": "cs",
        "javascript": "javascript",
        "typescript": "typescript",
        "ruby": "ruby",
        "swift": "swift",
        "go": "go",
        "rust": "rust",
        "kotlin": "kotlin",
        "scala": "scala",
        "php": "php",
    }
    return language_map.get(language.lower(), "text")

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
                problem_id = sub["titleSlug"]
                difficulty = await get_leetcode_problem_difficulty(sub['titleSlug'])
                is_new_unique_solve = log_problem_solved(
                    platform="leetcode", 
                    problem_id=problem_id,
                    rating=difficulty
                )
                
                # Only send a notification for the first time a problem is solved.
                if is_new_unique_solve:
                    problem_url = f"https://leetcode.com/problems/{sub['titleSlug']}/"
                    
                    details = await get_leetcode_submission_details(int(sub['id']))
                    
                    runtime = memory = None
                    if details and details.get('runtime') is not None and details.get('memory') is not None:
                        runtime = f"{details['runtime']} ms"
                        memory = f"{details['memory'] // 1024} KB"

                    # Get and parse the submission code only if enabled
                    code = None
                    language_ext = None
                    if config.SEND_SOLUTION_CODE:
                        code = await get_submission_code(int(sub['id']))
                        code = parse_submission_code(code)
                        language_ext = get_language_extension(sub['lang'])

                    message = format_new_solve_message(
                        platform="LeetCode",
                        problem_name=sub['title'],
                        problem_url=problem_url,
                        difficulty=difficulty,
                        language=sub['lang'],
                        runtime=runtime,
                        memory=memory,
                        code=code,
                        language_ext=language_ext
                    )

                    await context.bot.send_message(
                        config.CHANNEL_ID, 
                        message, 
                        disable_web_page_preview=True,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    logging.info(f"Sent notification for new unique problem: LC submission {sub['id']}")
                    await asyncio.sleep(1) # Avoid rate-limiting Telegram
                else:
                    logging.info(f"Skipping notification for already solved problem: LC submission {sub['id']}")
                
                # ALWAYS update the last processed timestamp
                save_last_leetcode_timestamp(int(sub["timestamp"]))

    except httpx.RequestError as e:
        logging.error(f"An error occurred with LeetCode API: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred in LeetCode check: {e}", exc_info=True)
