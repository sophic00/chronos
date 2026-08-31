import os
import sys
import logging
from datetime import time, datetime, timedelta, date
import calendar

import pytz
from telegram.ext import Application, ContextTypes

from .config import settings as config
from .data.database import init_db, get_daily_stats_from_db, get_value, set_value
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
    send_summary,
    error_handler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def recover_missed_summaries(application: Application) -> None:
    """Checks the key-value store and recovers any missed scheduled daily, weekly, or monthly summaries."""
    
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz).date()
    
    # --- Daily Summary Recovery ---
    yesterday = now - timedelta(days=1)
    last_daily_raw = get_value("last_sent_daily_summary_date")
    
    if not last_daily_raw:
        # First run: initialize baseline to yesterday to avoid spamming
        set_value("last_sent_daily_summary_date", yesterday.isoformat())
        logger.info(f"Initialized daily summary baseline to {yesterday.isoformat()}")
    else:
        try:
            last_daily = date.fromisoformat(last_daily_raw)
            if last_daily < yesterday:
                logger.warning(f"Detected missed daily summary. Last sent: {last_daily_raw}, expected: {yesterday.isoformat()}. Recovering...")
                # Empty days are not broadcast (consistent with the scheduled sender)
                if get_daily_stats_from_db(yesterday):
                    await send_summary(application.bot, "daily", yesterday, recovered=True)
                else:
                    set_value("last_sent_daily_summary_date", yesterday.isoformat())
                logger.info(f"Successfully recovered daily summary for {yesterday.isoformat()}")
        except ValueError:
            logger.error(f"Invalid date format in DB for last_sent_daily_summary_date: {last_daily_raw}")
            set_value("last_sent_daily_summary_date", yesterday.isoformat())

    # --- Weekly Summary Recovery ---
    start_of_previous_week = _start_of_week(now) - timedelta(days=7)
    last_weekly_raw = get_value("last_sent_weekly_summary_date")
    if not last_weekly_raw:
        # First run: initialize baseline to previous week to avoid spamming
        set_value("last_sent_weekly_summary_date", start_of_previous_week.isoformat())
        logger.info(f"Initialized weekly summary baseline to {start_of_previous_week.isoformat()}")
    else:
        try:
            last_weekly = date.fromisoformat(last_weekly_raw)
            if last_weekly < start_of_previous_week:
                logger.warning(f"Detected missed weekly summary. Last sent: {last_weekly_raw}, expected: {start_of_previous_week.isoformat()}. Recovering...")
                await send_summary(application.bot, "weekly", start_of_previous_week, recovered=True)
                logger.info(f"Successfully recovered weekly summary for {start_of_previous_week.isoformat()}")
        except ValueError:
            logger.error(f"Invalid date format in DB for last_sent_weekly_summary_date: {last_weekly_raw}")
            set_value("last_sent_weekly_summary_date", start_of_previous_week.isoformat())

    # --- Monthly Summary Recovery ---
    first_day_of_previous_month = _first_day_of_previous_month(now)
    last_monthly_raw = get_value("last_sent_monthly_summary_date")
    if not last_monthly_raw:
        set_value("last_sent_monthly_summary_date", first_day_of_previous_month.isoformat())
        logger.info(f"Initialized monthly summary baseline to {first_day_of_previous_month.isoformat()}")
    else:
        try:
            last_monthly = date.fromisoformat(last_monthly_raw)
            if last_monthly < first_day_of_previous_month:
                logger.warning(f"Detected missed monthly summary. Last sent: {last_monthly_raw}, expected: {first_day_of_previous_month.isoformat()}. Recovering...")
                await send_summary(application.bot, "monthly", first_day_of_previous_month, recovered=True)
                logger.info(f"Successfully recovered monthly summary for {first_day_of_previous_month.isoformat()}")
        except ValueError:
            logger.error(f"Invalid date format in DB for last_sent_monthly_summary_date: {last_monthly_raw}")
            set_value("last_sent_monthly_summary_date", first_day_of_previous_month.isoformat())


def _start_of_week(day: date) -> date:
    """Monday of the week containing day."""
    return day - timedelta(days=day.weekday())


def _first_day_of_previous_month(day: date) -> date:
    if day.month == 1:
        return day.replace(year=day.year - 1, month=12, day=1)
    return day.replace(month=day.month - 1, day=1)


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
            await send_summary(application.bot, "daily", mark_sent=False)
        else:
            await test_codeforces_submission(application)
            await test_leetcode_submission(application)
        
        logger.info("--- TEST MODE FINISHED. ---")
        # run_polling() is still in post_init at this point, so the application is
        # not "running" yet and Application.stop() would raise RuntimeError.
        # Raising SystemExit unwinds run_polling and exits the process cleanly.
        raise SystemExit(0)

    # --- Initial State Sync (Async Part) ---
    if get_last_submission_id() == 0:
        logger.info("First run for Codeforces. Initializing with the latest submission ID...")
        latest_id = await get_latest_submission_id()
        if latest_id:
            save_last_submission_id(latest_id)
            logger.info(f"Initialized Codeforces. Will only report submissions newer than ID {latest_id}.")
        else:
            logger.warning("Could not fetch initial Codeforces submission ID.")

    if get_last_leetcode_timestamp() == 0:
        logger.info("First run for LeetCode. Initializing with the latest submission timestamp...")
        latest_ts = await get_latest_leetcode_submission_timestamp()
        if latest_ts:
            save_last_leetcode_timestamp(latest_ts)
            logger.info(f"Initialized LeetCode. Will only report submissions newer than timestamp {latest_ts}.")
        else:
            logger.warning("Could not fetch initial LeetCode submission timestamp.")

    # --- Recover Missed Summaries ---
    await recover_missed_summaries(application)


async def send_monthly_summary(context: ContextTypes.DEFAULT_TYPE, target_date=None):
    """Sends the monthly summary message to the channel."""
    logging.info("Sending monthly summary...")
    await send_summary(context.bot, "monthly", target_date)


async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE, target_date=None):
    """Sends the weekly summary message to the channel."""
    logging.info("Sending weekly summary...")
    await send_summary(context.bot, "weekly", target_date)


async def daily_check_and_send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Checks if today is Sunday and sends weekly summary if so."""
    now = datetime.now(pytz.timezone(config.TIMEZONE)).date()
    
    # Sunday is 6 in weekday() (Monday=0, Sunday=6)
    if now.weekday() == 6:
        logging.info("Today is Sunday, sending weekly summary...")
        await send_weekly_summary(context, now)


async def daily_check_and_send_monthly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Checks if today is the last day of the month and sends monthly summary if so."""
    now = datetime.now(pytz.timezone(config.TIMEZONE)).date()
    last_day_of_month = calendar.monthrange(now.year, now.month)[1]
    
    if now.day == last_day_of_month:
        logging.info("Today is the last day of the month, sending monthly summary...")
        await send_monthly_summary(context, now)


def main() -> None:
    """Sets up and runs the bot."""
    # --- Initial Setup ---
    config.validate_settings()
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