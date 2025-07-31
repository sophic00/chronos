import os
import sys
import logging
from datetime import time, datetime, timedelta
import calendar

import pytz
from telegram.ext import Application, ContextTypes
from telegram.constants import ParseMode

from .config import settings as config
from .data.database import init_db, get_monthly_stats_from_db, get_weekly_stats_from_db
from .data.state_manager import (
    get_last_submission_id,
    save_last_submission_id,
    get_last_leetcode_timestamp,
    save_last_leetcode_timestamp
)
from .integrations.codeforces import get_latest_submission_id, check_codeforces_submissions
from .integrations.leetcode import get_latest_leetcode_submission_timestamp, check_leetcode_submissions
from .bot.handlers import (
    register_handlers,
    test_codeforces_submission,
    test_leetcode_submission,
    send_daily_summary,
    get_daily_summary_message,
    error_handler,
    _format_summary_message,
    weekly_stats_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_initialization(application: Application):
    """
    This coroutine is executed once after the application has been initialized.
    It handles all asynchronous setup tasks.
    """
    # --- Startup Verification ---
    try:
        logger.info(f"--- Verifying access to channel {config.CHANNEL_ID} ---")
        await application.bot.get_chat(config.CHANNEL_ID)
        logger.info("--- Channel access verified successfully! ---")
    except Exception as e:
        logger.critical(f"CRITICAL: Could not access channel {config.CHANNEL_ID}.")
        logger.critical("Please ensure the bot is in the channel with admin rights.")
        logger.critical(f"Error details: {e}")
        # Raising an exception here will cause the application to shut down gracefully.
        raise

    # --- Test Mode ---
    if config.TEST_MODE:
        logger.info("--- RUNNING IN TEST MODE ---")
        if config.TEST_MODE_STATS_ONLY:
            logger.info("--- Testing Daily Summary Only ---")
            message = get_daily_summary_message()
            await application.bot.send_message(
                config.CHANNEL_ID,
                message,
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await test_codeforces_submission(application)
            await test_leetcode_submission(application)
        
        logger.info("--- TEST MODE FINISHED. ---")
        # Stop the application, which will cause run_polling() to exit.
        application.stop()
        return

    # --- Initial State Sync (Async Part) ---
    if get_last_leetcode_timestamp() == 0:
        logger.info("First run for LeetCode. Initializing with the latest submission timestamp...")
        latest_ts = await get_latest_leetcode_submission_timestamp()
        if latest_ts:
            save_last_leetcode_timestamp(latest_ts)
            logger.info(f"Initialized LeetCode. Will only report submissions newer than timestamp {latest_ts}.")
        else:
            logger.warning("Could not fetch initial LeetCode submission timestamp.")


async def send_monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Sends the monthly summary message to the channel."""
    logging.info("Sending monthly summary...")
    stats = get_monthly_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'monthly')

    if grand_total == 0:
        message = "No problems were solved this month. Let's do better next month! 💪"
    else:
        current_date = datetime.now()
        month_year = current_date.strftime("%B %Y")
        message = (
            f"📊 *Monthly Progress Report*\n"
            f"🗓️ *Period:* {month_year}\n"
            f"🚀 *Progress Overview*\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{summary_details}\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🎯 *Grand Total Solved This Month:* {grand_total}"
        )

    await context.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    logging.info("Monthly summary sent.")


async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Sends the weekly summary message to the channel."""
    logging.info("Sending weekly summary...")
    stats = get_weekly_stats_from_db()
    summary_details, grand_total = _format_summary_message(stats, 'weekly')

    if grand_total == 0:
        message = "No problems were solved this week. Let's step up next week! 💪"
    else:
        current_date = datetime.now()
        # Calculate week range (Monday to Sunday)
        days_since_monday = current_date.weekday()
        start_of_week = current_date - timedelta(days=days_since_monday)
        end_of_week = start_of_week + timedelta(days=6)
        week_range = f"{start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d, %Y')}"
        
        message = (
            f"📊 *Weekly Progress Report*\n"
            f"🗓️ *Period:* {week_range}\n"
            f"🚀 *Progress Overview*\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{summary_details}\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🎯 *Grand Total Solved This Week:* {grand_total}"
        )

    await context.bot.send_message(config.CHANNEL_ID, message, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    logging.info("Weekly summary sent.")


async def daily_check_and_send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Checks if today is Sunday and sends weekly summary if so."""
    now = datetime.now(pytz.timezone(config.TIMEZONE))
    
    # Sunday is 6 in weekday() (Monday=0, Sunday=6)
    if now.weekday() == 6:
        logging.info("Today is Sunday, sending weekly summary...")
        await send_weekly_summary(context)


async def daily_check_and_send_monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Checks if today is the last day of the month and sends monthly summary if so."""
    now = datetime.now(pytz.timezone(config.TIMEZONE))
    last_day_of_month = calendar.monthrange(now.year, now.month)[1]
    
    if now.day == last_day_of_month:
        logging.info("Today is the last day of the month, sending monthly summary...")
        await send_monthly_summary(context)


def main() -> None:
    """Sets up and runs the bot."""
    # --- Initial Setup ---
    os.makedirs("data", exist_ok=True)
    if "--new-session" in sys.argv:
        logger.warning("The --new-session flag is deprecated and has no effect.")

    # --- Bot Setup ---
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_initialization)
        .build()
    )

    # --- Database and Command Handlers ---
    init_db()
    register_handlers(application)
    application.add_error_handler(error_handler)

    # --- Initial State Sync (Sync Part) ---
    if get_last_submission_id() == 0:
        logger.info("First run for Codeforces. Initializing with the latest submission ID...")
        latest_id = get_latest_submission_id()
        if latest_id:
            save_last_submission_id(latest_id)
            logger.info(f"Initialized Codeforces. Will only report submissions newer than ID {latest_id}.")
        else:
            logger.warning("Could not fetch initial Codeforces submission ID.")

    # --- Schedule Jobs ---
    job_queue = application.job_queue
    tz = pytz.timezone(config.TIMEZONE)

    # Daily summary at 23:59
    job_queue.run_daily(
        send_daily_summary,
        time=time(hour=23, minute=59, second=0, tzinfo=tz),
        name="daily_summary",
    )

    # Weekly summary at 23:59 on Sunday
    job_queue.run_daily(
        daily_check_and_send_weekly_summary,
        time=time(hour=23, minute=59, second=0, tzinfo=tz),
        name="weekly_summary",
    )

    # Monthly summary at 23:59 on the last day of each month
    job_queue.run_daily(
        daily_check_and_send_monthly_summary,
        time=time(hour=23, minute=59, second=0, tzinfo=tz),
        name="monthly_summary",
    )

    # Codeforces and LeetCode checkers
    job_queue.run_repeating(
        check_codeforces_submissions,
        interval=60,
        first=10,
        name="cf_checker",
    )
    job_queue.run_repeating(
        check_leetcode_submissions,
        interval=60,
        first=20,
        name="lc_checker",
    )

    # --- Start Bot ---
    logger.info("Bot started! Now polling for updates...")
    application.run_polling()


if __name__ == "__main__":
    main() 