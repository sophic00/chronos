import asyncio
import hashlib
import io
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import httpx
import pytz
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..bot.image_generator import generate_solve_card
from ..bot.messaging import format_new_solve_message, format_bytes, prettify_language
from ..config import constants
from ..config import settings as config
from ..data.database import log_problem_solved
from ..data.state_manager import get_last_submission_id, save_last_submission_id


def generate_api_sig(method_name, **kwargs):
    rand = "123456"
    params = "&".join([f"{k}={v}" for k, v in sorted(kwargs.items())])
    return hashlib.sha512(
        f"{rand}/{method_name}?{params}#{config.CF_API_SECRET}".encode("utf-8")
    ).hexdigest()


@asynccontextmanager
async def _get_client(client: Optional[httpx.AsyncClient] = None):
    """Helper to reuse an existing AsyncClient or yield a newly created one."""
    if client is not None:
        yield client
    else:
        async with httpx.AsyncClient(timeout=30.0) as new_client:
            yield new_client


async def get_latest_submission_id(client: Optional[httpx.AsyncClient] = None):
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
        async with _get_client(client) as active_client:
            response = await active_client.get(
                constants.CODEFORCES_API_URL + f"/{method_name}", params=params
            )
            response.raise_for_status()
            data = response.json()
        if data["status"] == "OK" and data["result"]:
            return data["result"][0]["id"]
        elif data["status"] != "OK":
            logging.warning(f"Codeforces API error on init: {data.get('comment')}")
    except httpx.RequestError as e:
        logging.error(f"An error occurred during initial submission fetch: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(
            f"Codeforces API returned error status {e.response.status_code} during init: {e}"
        )
    return 0


async def check_codeforces_submissions(
    context: ContextTypes.DEFAULT_TYPE, client: Optional[httpx.AsyncClient] = None
):
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
        # Use async httpx and support reusable client
        async with _get_client(client) as active_client:
            response = await active_client.get(
                constants.CODEFORCES_API_URL + f"/{method_name}", params=params
            )
            response.raise_for_status()
            data = response.json()

        if data["status"] == "OK":
            last_processed_id = get_last_submission_id()
            submissions = data.get("result", [])

            if submissions and last_processed_id == 0:
                latest_id = submissions[0]["id"]
                save_last_submission_id(latest_id)
                logging.warning(
                    f"Codeforces state was uninitialized (ID = 0). "
                    f"Initialized baseline submission ID to {latest_id} without sending notifications."
                )
                return

            new_successful_submissions = []
            for submission in submissions:
                if (
                    submission["id"] > last_processed_id
                    and submission.get("verdict") == "OK"
                ):
                    new_successful_submissions.append(submission)

            if new_successful_submissions:
                # Process them chronologically
                for submission in sorted(
                    new_successful_submissions, key=lambda x: x["creationTimeSeconds"]
                ):
                    problem = submission["problem"]
                    problem_id = f"{problem.get('contestId')}-{problem.get('index')}"
                    rating = problem.get("rating", "NA")

                    is_new_unique_solve = log_problem_solved(
                        platform="codeforces", problem_id=problem_id, rating=rating
                    )

                    # Only send a notification for the first time a problem is solved.
                    if is_new_unique_solve:
                        problem_url = f"https://codeforces.com/contest/{problem['contestId']}/problem/{problem['index']}"
                        if config.SEND_AS_IMAGE:
                            try:
                                stats = [
                                    ("Language", prettify_language(submission["programmingLanguage"])),
                                    ("Time", f"{submission['timeConsumedMillis']} ms"),
                                    ("Memory", format_bytes(submission["memoryConsumedBytes"])),
                                    ("Problem", f"{problem.get('contestId')}{problem.get('index')}"),
                                ]
                                solve_dt = datetime.fromtimestamp(
                                    submission["creationTimeSeconds"],
                                    tz=pytz.timezone(config.TIMEZONE),
                                )
                                image_bytes = generate_solve_card(
                                    platform="Codeforces",
                                    title=problem["name"],
                                    difficulty=str(rating),
                                    stats=stats,
                                    tags=problem.get("tags", [])[:3],
                                    footer_left=solve_dt.strftime("%d %b %Y, %I:%M %p"),
                                    footer_right=f"@{config.CF_HANDLE}",
                                )

                                caption = (
                                    f"👾 *New Solve on Codeforces!*\n"
                                    f"📘 *Problem:* [{problem['name']}]({problem_url})\n"
                                    f"🏷️ *Rating:* {rating}"
                                )

                                await context.bot.send_photo(
                                    chat_id=config.CHANNEL_ID,
                                    photo=io.BytesIO(image_bytes),
                                    caption=caption,
                                    parse_mode=ParseMode.MARKDOWN,
                                )
                                logging.info(
                                    f"Sent photo notification for new unique problem: CF submission {submission['id']}"
                                )
                            except Exception as img_err:
                                logging.error(
                                    f"Failed to generate/send image notification for CF {submission['id']}: {img_err}. Falling back to text.",
                                    exc_info=True,
                                )
                                message = format_new_solve_message(
                                    platform="Codeforces",
                                    problem_name=problem["name"],
                                    problem_url=problem_url,
                                    difficulty=str(rating),
                                    language=submission["programmingLanguage"],
                                    runtime=f"{submission['timeConsumedMillis']} ms",
                                    memory=format_bytes(submission["memoryConsumedBytes"]),
                                )
                                await context.bot.send_message(
                                    config.CHANNEL_ID,
                                    message,
                                    disable_web_page_preview=True,
                                    parse_mode=ParseMode.MARKDOWN,
                                )
                        else:
                            message = format_new_solve_message(
                                platform="Codeforces",
                                problem_name=problem["name"],
                                problem_url=problem_url,
                                difficulty=str(rating),
                                language=submission["programmingLanguage"],
                                runtime=f"{submission['timeConsumedMillis']} ms",
                                memory=f"{submission['memoryConsumedBytes'] // 1024} KB",
                            )
                            await context.bot.send_message(
                                config.CHANNEL_ID,
                                message,
                                disable_web_page_preview=True,
                                parse_mode=ParseMode.MARKDOWN,
                            )
                        await asyncio.sleep(
                            1
                        )  # Avoid rate-limiting Telegram on new solves
                    else:
                        logging.info(
                            f"Skipping notification for already solved problem: CF submission {submission['id']}"
                        )

                    # ALWAYS update the last processed ID to mark this submission as seen.
                    save_last_submission_id(submission["id"])
        else:
            logging.warning(f"Codeforces API returned status: {data.get('comment')}")
    except httpx.RequestError as e:
        logging.error(f"An error occurred with Codeforces API: {e}")
    except httpx.HTTPStatusError as e:
        logging.error(
            f"Codeforces API returned error status {e.response.status_code}: {e}"
        )
    except Exception as e:
        logging.error(
            f"An unexpected error occurred in Codeforces check: {e}", exc_info=True
        )
