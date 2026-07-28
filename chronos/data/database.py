"""
Database operations using ORM abstraction.
This module provides backward compatibility while using SQLAlchemy ORM under the hood.
"""

import logging
from .database_orm import db_service

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    db_service.init_db()

def log_problem_solved(platform: str, problem_id: str, rating: str) -> bool:
    """
    Logs a newly solved problem if it's the first time ever for this user.
    Returns True if it's a new unique solve, False otherwise.
    """
    return db_service.log_problem_solved(platform, problem_id, rating)

def get_daily_stats_from_db(target_date=None):
    """Gets the count of unique problems first solved on target_date, grouped by platform and rating."""
    return db_service.get_daily_stats(target_date)

def get_monthly_stats_from_db(target_date=None):
    """Gets the count of unique problems first solved in the month of target_date, grouped by platform and rating."""
    return db_service.get_monthly_stats(target_date)

def get_weekly_stats_from_db(target_date=None):
    """Gets the count of unique problems first solved in the week of target_date, grouped by platform and rating."""
    return db_service.get_weekly_stats(target_date)

def get_past_day_stats_from_db():
    """Gets the count of unique problems first solved yesterday, grouped by platform and rating."""
    return db_service.get_past_day_stats()

def get_past_week_stats_from_db():
    """Gets the count of unique problems first solved in the previous week (Monday to Sunday), grouped by platform and rating."""
    return db_service.get_past_week_stats()

def get_daily_breakdown_from_db(start_date, end_date):
    """Gets the count of unique problems first solved per day in [start_date, end_date]."""
    return db_service.get_daily_breakdown(start_date, end_date)

def get_current_streak():
    """Gets the current streak of consecutive days with at least one unique solve."""
    return db_service.get_current_streak()

def get_value(key: str, default: str = None) -> str:
    """Gets a value from the key-value store."""
    return db_service.get_value(key, default)

def set_value(key: str, value: str):
    """Sets a value in the key-value store."""
    db_service.set_value(key, value)


def set_leetcode_target(target_type: str, easy: int, medium: int, hard: int) -> bool:
    """Sets LeetCode targets for daily, weekly, or monthly."""
    return db_service.set_leetcode_target(target_type, easy, medium, hard)


def get_leetcode_target(target_type: str) -> dict:
    """Gets LeetCode targets for daily, weekly, or monthly."""
    return db_service.get_leetcode_target(target_type) 

def is_problem_solved(platform: str, problem_id: str) -> bool:
    """Checks if the problem has already been solved by the user."""
    return db_service.is_problem_solved(platform, problem_id) 