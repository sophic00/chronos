import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(var_name, default=None):
    """Gets an environment variable, stripping inline comments."""
    value = os.getenv(var_name, default)
    if value and '#' in value:
        value = value.split('#', 1)[0].strip()
    return value

# Codeforces
CF_API_KEY = get_env_var("CF_API_KEY")
CF_API_SECRET = get_env_var("CF_API_SECRET")
CF_HANDLE = get_env_var("CF_HANDLE")

# LeetCode
LEETCODE_USERNAME = get_env_var("LEETCODE_USERNAME")
LEETCODE_SESSION = get_env_var("LEETCODE_SESSION")
CSRF_TOKEN = get_env_var("CSRF_TOKEN")

# Telegram
API_ID = int(get_env_var("API_ID"))
API_HASH = get_env_var("API_HASH")
BOT_TOKEN = get_env_var("BOT_TOKEN")
CHANNEL_ID = int(get_env_var("CHANNEL_ID"))
TIMEZONE = get_env_var("TIMEZONE", "Asia/Kolkata")

# --- Bot Settings ---
# Set to True to send a test message for the latest submission on each platform and then exit.
TEST_MODE = get_env_var("TEST_MODE", "False").lower() in ("true", "1", "t")
# If TEST_MODE is True, set this to True to only test the daily summary.
TEST_MODE_STATS_ONLY = get_env_var("TEST_MODE_STATS_ONLY", "False").lower() in ("true", "1", "t")
# NOTE: LeetCode cookies expire after about 2 weeks. You will need to update them periodically. 