import hashlib
import time
import httpx
import asyncio
import logging

from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..config import settings as config
from ..config import constants
from ..data.database import log_problem_solved
from ..data.state_manager import get_last_submission_id, save_last_submission_id
from ..bot.messaging import format_new_solve_message

def generate_api_sig(method_name, **kwargs):
    rand = "123456"
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
        with httpx.Client(timeout=30.0) as client:
            response = client.get(constants.CODEFORCES_API_URL + f"/{method_name}", params=params)
            response.raise_for_status()
            data = response.json()
        if data["status"] == "OK" and data["result"]:
            return data["result"][0]["id"]
        elif data["status"] != "OK":
            logging.warning(f"Codeforces API error on init: {data.get('comment')}")
    except httpx.RequestError as e:
        logging.error(f"An error occurred during initial submission fetch: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(f"Codeforces API returned error status {e.response.status_code} during init: {e}")
    except httpx.TimeoutException as e:
        logging.error(f"Codeforces API request timed out during init: {e}")
    return 0

async def check_codeforces_submissions(context: ContextTypes.DEFAULT_TYPE):
    """Checks for new successful Codeforces submissions and sends notifications."""
    logging.info("Checking for new Codeforces submissions...")
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
        # Use async httpx to prevent blocking other scheduled jobs
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(constants.CODEFORCES_API_URL + f"/{method_name}", params=params)
            response.raise_for_status()
            data = response.json()

        if data["status"] == "OK":
            last_processed_id = get_last_submission_id()
            new_successful_submissions = []
            if "result" in data:
                for submission in data["result"]:
                    if submission["id"] > last_processed_id and submission.get("verdict") == "OK":
                        new_successful_submissions.append(submission)

            if new_successful_submissions:
                # Process them chronologically
                for submission in sorted(new_successful_submissions, key=lambda x: x['creationTimeSeconds']):
                    problem = submission["problem"]
                    problem_id = f"{problem.get('contestId')}-{problem.get('index')}"
                    rating = problem.get('rating', 'NA')

                    is_new_unique_solve = log_problem_solved(
                        platform="codeforces", 
                        problem_id=problem_id,
                        rating=rating
                    )

                    # Only send a notification for the first time a problem is solved.
                    if is_new_unique_solve:
                        problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
                        
                        message = format_new_solve_message(
                            platform="Codeforces",
                            problem_name=problem['name'],
                            problem_url=problem_url,
                            difficulty=str(rating),
                            language=submission['programmingLanguage'],
                            runtime=f"{submission['timeConsumedMillis']} ms",
                            memory=f"{submission['memoryConsumedBytes'] // 1024} KB"
                        )
                        
                        await context.bot.send_message(
                            config.CHANNEL_ID, 
                            message, 
                            disable_web_page_preview=True,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        logging.info(f"Sent notification for new unique problem: CF submission {submission['id']}")
                        await asyncio.sleep(1) # Avoid rate-limiting Telegram on new solves
                    else:
                        logging.info(f"Skipping notification for already solved problem: CF submission {submission['id']}")
                    
                    # ALWAYS update the last processed ID to mark this submission as seen.
                    save_last_submission_id(submission["id"])
        else:
            logging.warning(f"Codeforces API returned status: {data.get('comment')}")
    except httpx.RequestError as e:
        logging.error(f"An error occurred with Codeforces API: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(f"Codeforces API returned error status {e.response.status_code}: {e}")
    except httpx.TimeoutException as e:
        logging.error(f"Codeforces API request timed out: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred in Codeforces check: {e}", exc_info=True)
