from database import get_value, set_value
import constants

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