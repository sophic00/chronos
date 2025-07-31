import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime, timedelta
import pytz
import logging
from ..config import settings as config

@contextmanager
def get_db_connection():
    """Provides a transactional database connection."""
    if not config.DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the environment.")
    
    conn = None
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        yield conn
    except psycopg2.DatabaseError as e:
        logging.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS solved_problems (
                    platform TEXT,
                    problem_id TEXT,
                    first_solve_date DATE,
                    rating TEXT,
                    PRIMARY KEY (platform, problem_id)
                )
            """)
            
            # --- Schema Migration ---
            # This handles migrating old setups by adding the 'rating' column if it's missing.
            cursor.execute("SELECT 1 FROM information_schema.columns WHERE table_name='solved_problems' AND column_name='rating'")
            if cursor.fetchone() is None:
                logging.info("Old database schema detected. Migrating: adding 'rating' column...")
                cursor.execute("ALTER TABLE solved_problems ADD COLUMN rating TEXT")
                logging.info("Migration complete. 'rating' column added.")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS key_value_store (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leetcode_targets (
                    id SERIAL PRIMARY KEY,
                    target_type TEXT NOT NULL CHECK (target_type IN ('daily', 'weekly', 'monthly')),
                    easy_target INTEGER DEFAULT 0,
                    medium_target INTEGER DEFAULT 0,
                    hard_target INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Ensure only one target per type
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS unique_target_type 
                ON leetcode_targets (target_type)
            """)
            
            conn.commit()
    logging.info("Database initialized successfully.")

def log_problem_solved(platform: str, problem_id: str, rating: str) -> bool:
    """
    Logs a newly solved problem if it's the first time ever for this user.
    Returns True if it's a new unique solve, False otherwise.
    """
    solve_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO solved_problems (platform, problem_id, first_solve_date, rating) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (platform, problem_id) DO NOTHING
                    """,
                    (platform, problem_id, solve_date, str(rating))
                )
                conn.commit()
                # The query returns 1 if a row was inserted, 0 otherwise.
                was_inserted = cursor.rowcount > 0
                if was_inserted:
                    logging.info(f"Logged new ALL-TIME unique solve: {platform} - {problem_id}")
                return was_inserted
            except psycopg2.DatabaseError as e:
                logging.error(f"Error logging solved problem: {e}")
                conn.rollback()
                return False

def get_daily_stats_from_db():
    """Gets the count of unique problems first solved today, grouped by platform and rating."""
    solve_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
    stats = {}
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            try:
                cursor.execute(
                    """
                    SELECT platform, rating, COUNT(problem_id) AS count 
                    FROM solved_problems 
                    WHERE first_solve_date = %s 
                    GROUP BY platform, rating
                    """,
                    (solve_date,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    platform = row['platform']
                    rating = row['rating']
                    count = row['count']
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
            except psycopg2.DatabaseError as e:
                logging.error(f"Error getting daily stats: {e}")
    return stats

def get_monthly_stats_from_db():
    """Gets the count of unique problems first solved in the current month, grouped by platform and rating."""
    current_date = datetime.now(pytz.timezone(config.TIMEZONE))
    first_day_of_month = current_date.replace(day=1).date()
    stats = {}
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            try:
                cursor.execute(
                    """
                    SELECT platform, rating, COUNT(problem_id) AS count 
                    FROM solved_problems 
                    WHERE first_solve_date >= %s 
                    GROUP BY platform, rating
                    """,
                    (first_day_of_month,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    platform = row['platform']
                    rating = row['rating']
                    count = row['count']
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
            except psycopg2.DatabaseError as e:
                logging.error(f"Error getting monthly stats: {e}")
    return stats

def get_weekly_stats_from_db():
    """Gets the count of unique problems first solved in the current week (Monday to Sunday), grouped by platform and rating."""
    current_date = datetime.now(pytz.timezone(config.TIMEZONE))
    # Calculate the start of the current week (Monday)
    days_since_monday = current_date.weekday()  # Monday is 0, Sunday is 6
    start_of_week = (current_date - timedelta(days=days_since_monday)).date()
    stats = {}
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            try:
                cursor.execute(
                    """
                    SELECT platform, rating, COUNT(problem_id) AS count 
                    FROM solved_problems 
                    WHERE first_solve_date >= %s 
                    GROUP BY platform, rating
                    """,
                    (start_of_week,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    platform = row['platform']
                    rating = row['rating']
                    count = row['count']
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
            except psycopg2.DatabaseError as e:
                logging.error(f"Error getting weekly stats: {e}")
    return stats

def get_value(key: str, default: str = None) -> str:
    """Gets a value from the key-value store."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT value FROM key_value_store WHERE key = %s", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
            except psycopg2.DatabaseError as e:
                logging.error(f"Error getting value for key '{key}': {e}")
                return default

def set_value(key: str, value: str):
    """Sets a value in the key-value store."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO key_value_store (key, value) 
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    (key, str(value))
                )
                conn.commit()
            except psycopg2.DatabaseError as e:
                logging.error(f"Error setting value for key '{key}': {e}")
                conn.rollback()


def set_leetcode_target(target_type: str, easy: int, medium: int, hard: int) -> bool:
    """Sets LeetCode targets for daily, weekly, or monthly."""
    if target_type not in ['daily', 'weekly', 'monthly']:
        raise ValueError("target_type must be 'daily', 'weekly', or 'monthly'")
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO leetcode_targets (target_type, easy_target, medium_target, hard_target, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (target_type) 
                    DO UPDATE SET 
                        easy_target = EXCLUDED.easy_target,
                        medium_target = EXCLUDED.medium_target,
                        hard_target = EXCLUDED.hard_target,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (target_type, easy, medium, hard)
                )
                conn.commit()
                logging.info(f"Set {target_type} LeetCode target: Easy={easy}, Medium={medium}, Hard={hard}")
                return True
            except psycopg2.DatabaseError as e:
                logging.error(f"Error setting {target_type} target: {e}")
                conn.rollback()
                return False


def get_leetcode_target(target_type: str) -> dict:
    """Gets LeetCode targets for daily, weekly, or monthly."""
    if target_type not in ['daily', 'weekly', 'monthly']:
        raise ValueError("target_type must be 'daily', 'weekly', or 'monthly'")
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            try:
                cursor.execute(
                    """
                    SELECT easy_target, medium_target, hard_target 
                    FROM leetcode_targets 
                    WHERE target_type = %s
                    """,
                    (target_type,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        'easy': row['easy_target'],
                        'medium': row['medium_target'],
                        'hard': row['hard_target']
                    }
                else:
                    return {'easy': 0, 'medium': 0, 'hard': 0}
            except psycopg2.DatabaseError as e:
                logging.error(f"Error getting {target_type} target: {e}")
                return {'easy': 0, 'medium': 0, 'hard': 0} 