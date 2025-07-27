"""
External platform integrations for Chronos bot.
"""

from .codeforces import (
    get_latest_submission_id, 
    check_codeforces_submissions
)
from .leetcode import (
    get_latest_leetcode_submission_timestamp,
    check_leetcode_submissions,
    get_leetcode_submission_details,
    get_leetcode_cookies,
    get_leetcode_headers
) 