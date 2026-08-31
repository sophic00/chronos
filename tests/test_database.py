from datetime import date, timedelta
from chronos.data.database import db_service

def test_log_problem_solved():
    """Verify logging unique solves and rejecting duplicate solves."""
    assert db_service.log_problem_solved("leetcode", "two-sum", "Easy") is True
    assert db_service.log_problem_solved("leetcode", "two-sum", "Easy") is False
    assert db_service.log_problem_solved("codeforces", "1-A", "800") is True

def test_key_value_store():
    """Verify CRUD operations in key-value store."""
    assert db_service.get_value("nonexistent", "default_val") == "default_val"
    assert db_service.set_value("my_key", "my_val") is True
    assert db_service.get_value("my_key") == "my_val"
    assert db_service.set_value("my_key", "new_val") is True
    assert db_service.get_value("my_key") == "new_val"

def test_leetcode_targets():
    """Verify targets setter and getter."""
    assert db_service.get_leetcode_target("daily") == {"easy": 0, "medium": 0, "hard": 0}
    assert db_service.set_leetcode_target("daily", 2, 1, 0) is True
    assert db_service.get_leetcode_target("daily") == {"easy": 2, "medium": 1, "hard": 0}

def test_stats_aggregation():
    """Verify stats aggregation logic across daily, weekly, and monthly periods."""
    today = date.today()
    
    # Log a few solves on today's date
    assert db_service.log_problem_solved("leetcode", "p1", "Easy") is True
    assert db_service.log_problem_solved("leetcode", "p2", "Medium") is True
    assert db_service.log_problem_solved("codeforces", "c1", "1200") is True
    
    # Verify daily stats for today
    stats_today = db_service.get_daily_stats(today)
    assert stats_today["leetcode"]["Easy"] == 1
    assert stats_today["leetcode"]["Medium"] == 1
    assert stats_today["codeforces"]["1200"] == 1
    
    # Verify daily stats for yesterday is empty
    yesterday = today - timedelta(days=1)
    assert db_service.get_daily_stats(yesterday) == {}
    
    # Verify weekly stats
    weekly_stats = db_service.get_weekly_stats(today)
    assert weekly_stats["leetcode"]["Easy"] == 1
    
    # Verify monthly stats
    monthly_stats = db_service.get_monthly_stats(today)
    assert monthly_stats["leetcode"]["Medium"] == 1

def test_is_problem_solved():
    """Verify is_problem_solved correctly checks existence."""
    assert db_service.is_problem_solved("leetcode", "two-sum") is False
    db_service.log_problem_solved("leetcode", "two-sum", "Easy")
    assert db_service.is_problem_solved("leetcode", "two-sum") is True
    assert db_service.is_problem_solved("leetcode", "nonexistent") is False
