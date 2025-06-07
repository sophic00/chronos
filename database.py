import sqlite3
from datetime import datetime
import pytz
import config
import constants

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    with sqlite3.connect(constants.DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solved_problems (
                platform TEXT,
                problem_id TEXT,
                first_solve_date TEXT,
                PRIMARY KEY (platform, problem_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS key_value_store (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()

def log_problem_solved(platform: str, problem_id: str):
    """Logs a newly solved problem, ignoring duplicates across all time."""
    solve_date = datetime.now(pytz.timezone(config.TIMEZONE)).strftime("%Y-%m-%d")
    with sqlite3.connect(constants.DB_FILE) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO solved_problems (platform, problem_id, first_solve_date) VALUES (?, ?, ?)",
                (platform, problem_id, solve_date)
            )
            conn.commit()
            print(f"Logged new ALL-TIME unique solve: {platform} - {problem_id}")
        except sqlite3.IntegrityError:
            pass

def get_daily_stats_from_db():
    """Gets the count of unique problems first solved today from the database."""
    solve_date = datetime.now(pytz.timezone(config.TIMEZONE)).strftime("%Y-%m-%d")
    stats = {"codeforces": 0, "leetcode": 0}
    with sqlite3.connect(constants.DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT platform, COUNT(problem_id) FROM solved_problems WHERE first_solve_date = ? GROUP BY platform",
            (solve_date,)
        )
        rows = cursor.fetchall()
        for row in rows:
            if row[0] in stats:
                stats[row[0]] = row[1]
    return stats

def get_value(key: str, default: str = None) -> str:
    """Gets a value from the key-value store."""
    with sqlite3.connect(constants.DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM key_value_store WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_value(key: str, value: str):
    """Sets a value in the key-value store."""
    with sqlite3.connect(constants.DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO key_value_store (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit() 