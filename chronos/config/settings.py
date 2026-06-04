import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(var_name, default=None):
    """Gets an environment variable, stripping inline comments, quotes, and whitespace."""
    value = os.getenv(var_name, default)
    if not value:
        return default
    
    if '#' in value:
        value = value.split('#', 1)[0]
    
    # Strip quotes and then any surrounding whitespace
    return value.strip().strip("'\"").strip()

# Database
DATABASE_URL = get_env_var("DATABASE_URL", "sqlite:///data/chronos.db")

# Codeforces
CF_API_KEY = get_env_var("CF_API_KEY")
CF_API_SECRET = get_env_var("CF_API_SECRET")
CF_HANDLE = get_env_var("CF_HANDLE")

# LeetCode
LEETCODE_USERNAME = get_env_var("LEETCODE_USERNAME")
LEETCODE_SESSION = get_env_var("LEETCODE_SESSION")
CSRF_TOKEN = get_env_var("CSRF_TOKEN")

# Telegram
BOT_TOKEN = get_env_var("BOT_TOKEN")
CHANNEL_ID_RAW = get_env_var("CHANNEL_ID")
CHANNEL_ID = None
if CHANNEL_ID_RAW:
    try:
        CHANNEL_ID = int(CHANNEL_ID_RAW)
    except ValueError:
        pass

TIMEZONE = get_env_var("TIMEZONE", "Asia/Kolkata")

# --- Bot Settings ---
# Set to True to send a test message for the latest submission on each platform and then exit.
TEST_MODE = get_env_var("TEST_MODE", "False").lower() in ("true", "1", "t")
# If TEST_MODE is True, set this to True to only test the daily summary.
TEST_MODE_STATS_ONLY = get_env_var("TEST_MODE_STATS_ONLY", "False").lower() in ("true", "1", "t")
# Set to True to include solution code in LeetCode notifications
SEND_SOLUTION_CODE = get_env_var("SEND_SOLUTION_CODE", "False").lower() in ("true", "1", "t")
# NOTE: LeetCode cookies expire after about 2 weeks. You will need to update them periodically.

def validate_settings() -> None:
    """
    Validates required settings and throws informative ValueError if invalid.
    Runs on bot startup.
    """
    errors = []
    
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is missing or empty.")
    
    if not CHANNEL_ID_RAW:
        errors.append("CHANNEL_ID is missing or empty.")
    elif CHANNEL_ID is None:
        errors.append(f"CHANNEL_ID must be a valid integer, got '{CHANNEL_ID_RAW}'.")
        
    if not CF_HANDLE:
        errors.append("CF_HANDLE is missing or empty.")
        
    if not LEETCODE_USERNAME:
        errors.append("LEETCODE_USERNAME is missing or empty.")
        
    if errors:
        raise ValueError("Configuration validation failed:\n" + "\n".join(f"- {err}" for err in errors))
 