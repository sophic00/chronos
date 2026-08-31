"""
External platform integrations for Chronos bot.
"""

from .codeforces import check_codeforces_submissions, get_latest_submission_id
from .leetcode import (
    check_leetcode_submissions,
    get_latest_leetcode_submission_timestamp,
    get_leetcode_cookies,
    get_leetcode_headers,
    get_leetcode_submission_details,
)

__all__ = [
    "check_codeforces_submissions",
    "get_latest_submission_id",
    "check_leetcode_submissions",
    "get_latest_leetcode_submission_timestamp",
    "get_leetcode_cookies",
    "get_leetcode_headers",
    "get_leetcode_submission_details",
]
