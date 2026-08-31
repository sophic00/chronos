from ..config import constants
from .database import get_value, set_value


def get_last_submission_id():
    value = get_value(constants.LAST_CF_SUBMISSION_ID_KEY, "0")
    return int(value)

def save_last_submission_id(submission_id):
    set_value(constants.LAST_CF_SUBMISSION_ID_KEY, str(submission_id))

def get_last_leetcode_timestamp():
    value = get_value(constants.LAST_LC_TIMESTAMP_KEY, "0")
    return int(value)

def save_last_leetcode_timestamp(timestamp):
    set_value(constants.LAST_LC_TIMESTAMP_KEY, str(timestamp))

def get_last_leetcode_boundary_ids():
    """IDs of submissions sharing the newest processed timestamp.

    Multiple AC submissions can share the same second, so the timestamp
    watermark alone cannot tell whether a submission was already processed.
    """
    value = get_value(constants.LAST_LC_BOUNDARY_IDS_KEY, "")
    return {v for v in value.split(",") if v}

def save_last_leetcode_boundary_ids(ids):
    set_value(constants.LAST_LC_BOUNDARY_IDS_KEY, ",".join(str(i) for i in ids)) 