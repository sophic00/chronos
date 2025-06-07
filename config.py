import os
from dotenv import load_dotenv

load_dotenv()

# Codeforces
CF_API_KEY = os.getenv("CF_API_KEY")
CF_API_SECRET = os.getenv("CF_API_SECRET")
CF_HANDLE = os.getenv("CF_HANDLE")

# LeetCode
LEETCODE_USERNAME = os.getenv("LEETCODE_USERNAME")
LEETCODE_SESSION = os.getenv("LEETCODE_SESSION")
CSRF_TOKEN = os.getenv("CSRF_TOKEN")

# Telegram
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

# --- Bot Settings ---
# Set to True to send a test message for the latest submission on each platform and then exit.
TEST_MODE = os.getenv("TEST_MODE", "False").lower() in ("true", "1", "t")
# If TEST_MODE is True, set this to True to only test the daily summary.
TEST_MODE_STATS_ONLY = os.getenv("TEST_MODE_STATS_ONLY", "False").lower() in ("true", "1", "t")
# NOTE: LeetCode cookies expire after about 2 weeks. You will need to update them periodically. 