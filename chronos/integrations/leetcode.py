import io
import httpx
import asyncio
import logging
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

import pytz
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..config import settings as config
from ..config import constants
from ..data.database import log_problem_solved, is_problem_solved
from ..data.state_manager import (
    get_last_leetcode_timestamp,
    save_last_leetcode_timestamp,
    get_last_leetcode_boundary_ids,
    save_last_leetcode_boundary_ids,
)
from ..bot.messaging import format_new_solve_message, format_bytes, prettify_language, escape_md
from ..bot.image_generator import generate_solve_card

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

@asynccontextmanager
async def _get_client(client: Optional[httpx.AsyncClient] = None):
    """Helper to reuse an existing AsyncClient or yield a newly created one."""
    if client is not None:
        yield client
    else:
        async with httpx.AsyncClient(timeout=30.0) as new_client:
            yield new_client

async def get_latest_leetcode_submission_timestamp(client: Optional[httpx.AsyncClient] = None):
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
    async with _get_client(client) as active_client:
        try:
            response = await active_client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
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

async def get_leetcode_submission_details(submission_id: int, client: Optional[httpx.AsyncClient] = None):
    graphql_query = {
        "query": """
            query submissionDetails($submissionId: Int!) {
                submissionDetails(submissionId: $submissionId) {
                    runtime
                    memory
                    runtimePercentile
                    memoryPercentile
                }
            }
        """,
        "variables": {"submissionId": submission_id},
    }
    cookies = get_leetcode_cookies()
    headers = get_leetcode_headers()
    async with _get_client(client) as active_client:
        try:
            response = await active_client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                logging.error(f"LeetCode API error on submission detail fetch: {data['errors']}")
                return None
            return data.get("data", {}).get("submissionDetails")
        except httpx.RequestError as e:
            logging.error(f"An error occurred during LeetCode submission detail fetch: {e}")
    return None

async def get_leetcode_problem_difficulty(title_slug: str, client: Optional[httpx.AsyncClient] = None):
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
    async with _get_client(client) as active_client:
        try:
            response = await active_client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                logging.error(f"LeetCode API error on problem difficulty fetch: {data['errors']}")
                return None
            return data.get("data", {}).get("question", {}).get("difficulty")
        except httpx.RequestError as e:
            logging.error(f"An error occurred during LeetCode problem difficulty fetch: {e}")
    return None

async def get_submission_code(submission_id: int, client: Optional[httpx.AsyncClient] = None) -> str:
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
    async with _get_client(client) as active_client:
        try:
            response = await active_client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
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
            "limit": 30
        }
    }
    cookies = get_leetcode_cookies()
    headers = get_leetcode_headers()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(constants.LEETCODE_API_URL, json=graphql_query, cookies=cookies, headers=headers)
            response.raise_for_status()
            data = response.json()
        
            if "errors" in data:
                logging.error(f"LeetCode API returned an error: {data['errors']}")
                return

            last_timestamp = get_last_leetcode_timestamp()
            boundary_ids = get_last_leetcode_boundary_ids()
            submissions = data.get("data", {}).get("recentAcSubmissionList", [])
            
            if submissions and last_timestamp == 0:
                latest_ts = int(submissions[0]["timestamp"])
                save_last_leetcode_timestamp(latest_ts)
                save_last_leetcode_boundary_ids({str(submissions[0]["id"])})
                logging.warning(
                    f"LeetCode state was uninitialized (timestamp = 0). "
                    f"Initialized baseline timestamp to {latest_ts} without sending notifications."
                )
                return

            # A submission is new if its timestamp is past the watermark, or it
            # shares the watermark timestamp but was never processed (several
            # submissions can land in the same second).
            new_submissions = [
                sub for sub in submissions
                if int(sub["timestamp"]) > last_timestamp
                or (
                    int(sub["timestamp"]) == last_timestamp
                    and str(sub["id"]) not in boundary_ids
                )
            ]

            if submissions and last_timestamp != 0:
                oldest_ts = min(int(s["timestamp"]) for s in submissions)
                if oldest_ts > last_timestamp:
                    logging.warning(
                        f"Oldest fetched LeetCode submission ({oldest_ts}) is newer than the "
                        f"last processed timestamp ({last_timestamp}); submissions in between may have been missed."
                    )
            
            if new_submissions:
                for sub in sorted(new_submissions, key=lambda x: int(x["timestamp"])):
                    problem_id = sub["titleSlug"]
                    
                    if is_problem_solved("leetcode", problem_id):
                        logging.info(f"Skipping notification and API queries for already solved problem: LC submission {sub['id']}")
                        continue

                    difficulty = await get_leetcode_problem_difficulty(sub['titleSlug'], client=client)
                    is_new_unique_solve = log_problem_solved(
                        platform="leetcode", 
                        problem_id=problem_id,
                        rating=difficulty
                    )
                    
                    # Only send a notification for the first time a problem is solved.
                    if is_new_unique_solve:
                        problem_url = f"https://leetcode.com/problems/{sub['titleSlug']}/"
                        
                        details = await get_leetcode_submission_details(int(sub['id']), client=client)

                        runtime = memory = beats = None
                        if details:
                            if details.get('runtime') is not None:
                                runtime = f"{details['runtime']} ms"
                            if details.get('memory') is not None:
                                memory = format_bytes(details['memory'])
                            if details.get('runtimePercentile') is not None:
                                beats = f"{details['runtimePercentile']:.1f}%"

                        # Get and parse the submission code only if enabled
                        code = None
                        language_ext = None
                        if config.SEND_SOLUTION_CODE:
                            code = await get_submission_code(int(sub['id']), client=client)
                            code = parse_submission_code(code)
                            language_ext = get_language_extension(sub['lang'])

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
                                    title=sub['title'],
                                    difficulty=difficulty if difficulty else "N/A",
                                    stats=stats,
                                    footer_left=solve_dt.strftime("%d %b %Y, %I:%M %p"),
                                    footer_right=f"@{config.LEETCODE_USERNAME}"
                                )
                                
                                caption = (
                                    f"👾 *New Solve on LeetCode!*\n"
                                    f"📘 *Problem:* [{escape_md(sub['title'])}]({problem_url})\n"
                                    f"🏷️ *Difficulty:* {escape_md(difficulty if difficulty else 'N/A')}"
                                )
                                
                                await context.bot.send_photo(
                                    chat_id=config.CHANNEL_ID,
                                    photo=io.BytesIO(image_bytes),
                                    caption=caption,
                                    parse_mode=ParseMode.MARKDOWN
                                )
                                logging.info(f"Sent photo notification for new unique problem: LC submission {sub['id']}")
                            except Exception as img_err:
                                logging.error(f"Failed to generate/send image notification for LC {sub['id']}: {img_err}. Falling back to text.", exc_info=True)
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
                        else:
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
                        await asyncio.sleep(1) # Avoid rate-limiting Telegram
                    else:
                        logging.info(f"Skipping notification for already solved problem: LC submission {sub['id']}")

                # Advance the watermark only after the whole batch is processed;
                # record the IDs sharing the newest timestamp so they are not
                # re-notified (or dropped) on the next poll.
                max_ts = max(int(s["timestamp"]) for s in new_submissions)
                boundary = {str(s["id"]) for s in new_submissions if int(s["timestamp"]) == max_ts}
                save_last_leetcode_timestamp(max_ts)
                save_last_leetcode_boundary_ids(boundary)

    except httpx.RequestError as e:
        logging.error(f"An error occurred with LeetCode API: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred in LeetCode check: {e}", exc_info=True)

