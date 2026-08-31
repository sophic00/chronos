"""Database operations using SQLAlchemy ORM."""

import calendar
import logging

logger = logging.getLogger(__name__)
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

import pytz
from sqlalchemy import and_, create_engine, func, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings as config
from .models import Base, KeyValueStore, LeetCodeTarget, SolvedProblem


class DatabaseService:
    """Service class for database operations using SQLAlchemy ORM."""
    
    def __init__(self):
        if not config.DATABASE_URL:
            raise ValueError("DATABASE_URL is not set in the environment.")
        
        self.engine = create_engine(config.DATABASE_URL, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    @contextmanager
    def get_session(self) -> Session:
        """Get a database session with automatic cleanup."""
        session = self.SessionLocal()
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def init_db(self):
        """Initialize the database and create tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            self._ensure_indexes()
            logger.info("Database initialized successfully with ORM.")
        except SQLAlchemyError as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def _ensure_indexes(self):
        """create_all() only applies indexes for brand-new tables; add any
        missing ones for databases created before they were declared."""
        inspector = inspect(self.engine)
        if "solved_problems" not in inspector.get_table_names():
            return
        existing = {ix["name"] for ix in inspector.get_indexes("solved_problems")}
        if "ix_solved_problems_first_solve_date" not in existing:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX ix_solved_problems_first_solve_date "
                    "ON solved_problems (first_solve_date)"
                ))
            logger.info("Created index ix_solved_problems_first_solve_date.")
    
    def log_problem_solved(self, platform: str, problem_id: str, rating: str) -> bool:
        """
        Log a newly solved problem if it's the first time ever for this user.
        Returns True if it's a new unique solve, False otherwise.

        The insert relies on the composite primary key (platform, problem_id)
        for uniqueness, making the check-and-insert atomic even under
        concurrent jobs.
        """
        solve_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
        
        try:
            with self.get_session() as session:
                session.add(SolvedProblem(
                    platform=platform,
                    problem_id=problem_id,
                    first_solve_date=solve_date,
                    rating=str(rating)
                ))
                session.commit()
                
            logger.info(f"Logged new ALL-TIME unique solve: {platform} - {problem_id}")
            return True
                
        except IntegrityError:
            # Composite PK (platform, problem_id) violated: already solved before
            logger.info(f"Skipping duplicate solve: {platform} - {problem_id}")
            return False
        except SQLAlchemyError as e:
            logger.error(f"Error logging solved problem: {e}")
            return False
            
    def is_problem_solved(self, platform: str, problem_id: str) -> bool:
        """Check if a problem has already been solved."""
        try:
            with self.get_session() as session:
                existing = session.query(SolvedProblem).filter(
                    and_(
                        SolvedProblem.platform == platform,
                        SolvedProblem.problem_id == problem_id
                    )
                ).first()
                return existing is not None
        except SQLAlchemyError as e:
            logger.error(f"Error checking if problem is solved: {e}")
            return False
    
    def get_daily_stats(self, target_date: date | None = None) -> dict[str, dict[str, int]]:
        """Get the count of unique problems first solved on target_date (or today if None), grouped by platform and rating."""
        if target_date is None:
            target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
        stats = {}
        
        try:
            with self.get_session() as session:
                results = session.query(
                    SolvedProblem.platform,
                    SolvedProblem.rating,
                    func.count(SolvedProblem.problem_id).label('count')
                ).filter(
                    SolvedProblem.first_solve_date == target_date
                ).group_by(
                    SolvedProblem.platform,
                    SolvedProblem.rating
                ).all()
                
                for platform, rating, count in results:
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting daily stats: {e}")
        
        return stats
    
    def get_monthly_stats(self, target_date: date | None = None) -> dict[str, dict[str, int]]:
        """Get the count of unique problems first solved in the month of target_date (or current month if None), grouped by platform and rating."""
        if target_date is None:
            target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
            
        first_day_of_month = target_date.replace(day=1)
        last_day = calendar.monthrange(target_date.year, target_date.month)[1]
        last_day_of_month = target_date.replace(day=last_day)
        stats = {}
        
        try:
            with self.get_session() as session:
                results = session.query(
                    SolvedProblem.platform,
                    SolvedProblem.rating,
                    func.count(SolvedProblem.problem_id).label('count')
                ).filter(
                    and_(
                        SolvedProblem.first_solve_date >= first_day_of_month,
                        SolvedProblem.first_solve_date <= last_day_of_month
                    )
                ).group_by(
                    SolvedProblem.platform,
                    SolvedProblem.rating
                ).all()
                
                for platform, rating, count in results:
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting monthly stats: {e}")
        
        return stats
    
    def get_weekly_stats(self, target_date: date | None = None) -> dict[str, dict[str, int]]:
        """Get the count of unique problems first solved in the week of target_date (Monday to Sunday) (or current week if None), grouped by platform and rating."""
        if target_date is None:
            target_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
            
        days_since_monday = target_date.weekday()  # Monday is 0, Sunday is 6
        start_of_week = target_date - timedelta(days=days_since_monday)
        end_of_week = start_of_week + timedelta(days=6)
        stats = {}
        
        try:
            with self.get_session() as session:
                results = session.query(
                    SolvedProblem.platform,
                    SolvedProblem.rating,
                    func.count(SolvedProblem.problem_id).label('count')
                ).filter(
                    and_(
                        SolvedProblem.first_solve_date >= start_of_week,
                        SolvedProblem.first_solve_date <= end_of_week
                    )
                ).group_by(
                    SolvedProblem.platform,
                    SolvedProblem.rating
                ).all()
                
                for platform, rating, count in results:
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting weekly stats: {e}")
        
        return stats
    
    def get_past_day_stats(self) -> dict[str, dict[str, int]]:
        """Get the count of unique problems first solved yesterday, grouped by platform and rating."""
        current_date = datetime.now(pytz.timezone(config.TIMEZONE))
        yesterday = (current_date - timedelta(days=1)).date()
        stats = {}
        
        try:
            with self.get_session() as session:
                results = session.query(
                    SolvedProblem.platform,
                    SolvedProblem.rating,
                    func.count(SolvedProblem.problem_id).label('count')
                ).filter(
                    SolvedProblem.first_solve_date == yesterday
                ).group_by(
                    SolvedProblem.platform,
                    SolvedProblem.rating
                ).all()
                
                for platform, rating, count in results:
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting past day stats: {e}")
        
        return stats
    
    def get_past_week_stats(self) -> dict[str, dict[str, int]]:
        """Get the count of unique problems first solved in the previous week (Monday to Sunday), grouped by platform and rating."""
        current_date = datetime.now(pytz.timezone(config.TIMEZONE))
        # Calculate the start of the current week (Monday)
        days_since_monday = current_date.weekday()  # Monday is 0, Sunday is 6
        start_of_current_week = (current_date - timedelta(days=days_since_monday)).date()
        # Previous week is 7 days before current week
        start_of_previous_week = start_of_current_week - timedelta(days=7)
        end_of_previous_week = start_of_current_week - timedelta(days=1)
        stats = {}
        
        try:
            with self.get_session() as session:
                results = session.query(
                    SolvedProblem.platform,
                    SolvedProblem.rating,
                    func.count(SolvedProblem.problem_id).label('count')
                ).filter(
                    and_(
                        SolvedProblem.first_solve_date >= start_of_previous_week,
                        SolvedProblem.first_solve_date <= end_of_previous_week
                    )
                ).group_by(
                    SolvedProblem.platform,
                    SolvedProblem.rating
                ).all()
                
                for platform, rating, count in results:
                    if platform not in stats:
                        stats[platform] = {}
                    stats[platform][rating] = count
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting past week stats: {e}")
        
        return stats
    
    def get_value(self, key: str, default: str | None = None) -> str | None:
        """Get a value from the key-value store."""
        try:
            with self.get_session() as session:
                kv_pair = session.query(KeyValueStore).filter(KeyValueStore.key == key).first()
                return kv_pair.value if kv_pair else default
        except SQLAlchemyError as e:
            logger.error(f"Error getting value for key '{key}': {e}")
            return default
    
    def set_value(self, key: str, value: str) -> bool:
        """Set a value in the key-value store."""
        try:
            with self.get_session() as session:
                kv_pair = session.query(KeyValueStore).filter(KeyValueStore.key == key).first()
                if kv_pair:
                    kv_pair.value = str(value)
                else:
                    kv_pair = KeyValueStore(key=key, value=str(value))
                    session.add(kv_pair)
                
                session.commit()
                return True
        except SQLAlchemyError as e:
            logger.error(f"Error setting value for key '{key}': {e}")
            return False
    
    def set_leetcode_target(self, target_type: str, easy: int, medium: int, hard: int) -> bool:
        """Set LeetCode targets for daily, weekly, or monthly."""
        if target_type not in ['daily', 'weekly', 'monthly']:
            raise ValueError("target_type must be 'daily', 'weekly', or 'monthly'")
        
        try:
            with self.get_session() as session:
                target = session.query(LeetCodeTarget).filter(
                    LeetCodeTarget.target_type == target_type
                ).first()
                
                if target:
                    target.easy_target = easy
                    target.medium_target = medium
                    target.hard_target = hard
                    target.updated_at = datetime.now(UTC).replace(tzinfo=None)
                else:
                    target = LeetCodeTarget(
                        target_type=target_type,
                        easy_target=easy,
                        medium_target=medium,
                        hard_target=hard
                    )
                    session.add(target)
                
                session.commit()
                logger.info(f"Set {target_type} LeetCode target: Easy={easy}, Medium={medium}, Hard={hard}")
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Error setting {target_type} target: {e}")
            return False
    
    def get_leetcode_target(self, target_type: str) -> dict[str, int]:
        """Get LeetCode targets for daily, weekly, or monthly."""
        if target_type not in ['daily', 'weekly', 'monthly']:
            raise ValueError("target_type must be 'daily', 'weekly', or 'monthly'")
        
        try:
            with self.get_session() as session:
                target = session.query(LeetCodeTarget).filter(
                    LeetCodeTarget.target_type == target_type
                ).first()
                
                if target:
                    return {
                        'easy': target.easy_target,
                        'medium': target.medium_target,
                        'hard': target.hard_target
                    }
                else:
                    return {'easy': 0, 'medium': 0, 'hard': 0}
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting {target_type} target: {e}")
            return {'easy': 0, 'medium': 0, 'hard': 0}

    def get_daily_breakdown(self, start_date: date, end_date: date) -> dict[date, int]:
        """Get the count of unique problems first solved per day in [start_date, end_date]."""
        breakdown = {}
        try:
            with self.get_session() as session:
                results = session.query(
                    SolvedProblem.first_solve_date,
                    func.count(SolvedProblem.problem_id).label('count')
                ).filter(
                    and_(
                        SolvedProblem.first_solve_date >= start_date,
                        SolvedProblem.first_solve_date <= end_date
                    )
                ).group_by(
                    SolvedProblem.first_solve_date
                ).all()

                for solve_date, count in results:
                    breakdown[solve_date] = count

        except SQLAlchemyError as e:
            logger.error(f"Error getting daily breakdown: {e}")

        return breakdown

    def get_current_streak(self) -> int:
        """Get the current streak of consecutive days with at least one unique solve.

        If nothing has been solved yet today, the streak counts up to yesterday.
        """
        today = datetime.now(pytz.timezone(config.TIMEZONE)).date()
        try:
            with self.get_session() as session:
                rows = session.query(SolvedProblem.first_solve_date).distinct().all()
                solve_dates = {row[0] for row in rows}
        except SQLAlchemyError as e:
            logger.error(f"Error getting current streak: {e}")
            return 0

        streak = 0
        day = today
        if day not in solve_dates:
            day -= timedelta(days=1)
        while day in solve_dates:
            streak += 1
            day -= timedelta(days=1)
        return streak


# Create a singleton instance
db_service = DatabaseService()


# --- Module-level convenience wrappers ---
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