"""ORM-based database operations using SQLAlchemy."""

import logging
from datetime import datetime, timedelta, date, timezone
import calendar
from typing import Dict, Optional, List
import pytz
from contextlib import contextmanager

from sqlalchemy import create_engine, func, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from .models import Base, SolvedProblem, KeyValueStore, LeetCodeTarget
from ..config import settings as config


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
            logging.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def init_db(self):
        """Initialize the database and create tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logging.info("Database initialized successfully with ORM.")
        except SQLAlchemyError as e:
            logging.error(f"Error initializing database: {e}")
            raise
    
    def log_problem_solved(self, platform: str, problem_id: str, rating: str) -> bool:
        """
        Log a newly solved problem if it's the first time ever for this user.
        Returns True if it's a new unique solve, False otherwise.
        """
        solve_date = datetime.now(pytz.timezone(config.TIMEZONE)).date()
        
        try:
            with self.get_session() as session:
                # Check if the problem already exists
                existing = session.query(SolvedProblem).filter(
                    and_(
                        SolvedProblem.platform == platform,
                        SolvedProblem.problem_id == problem_id
                    )
                ).first()
                
                if existing:
                    return False  # Already solved before
                
                # Create new solved problem record
                new_solve = SolvedProblem(
                    platform=platform,
                    problem_id=problem_id,
                    first_solve_date=solve_date,
                    rating=str(rating)
                )
                session.add(new_solve)
                session.commit()
                
                logging.info(f"Logged new ALL-TIME unique solve: {platform} - {problem_id}")
                return True
                
        except SQLAlchemyError as e:
            logging.error(f"Error logging solved problem: {e}")
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
            logging.error(f"Error checking if problem is solved: {e}")
            return False
    
    def get_daily_stats(self, target_date: Optional[date] = None) -> Dict[str, Dict[str, int]]:
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
            logging.error(f"Error getting daily stats: {e}")
        
        return stats
    
    def get_monthly_stats(self, target_date: Optional[date] = None) -> Dict[str, Dict[str, int]]:
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
            logging.error(f"Error getting monthly stats: {e}")
        
        return stats
    
    def get_weekly_stats(self, target_date: Optional[date] = None) -> Dict[str, Dict[str, int]]:
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
            logging.error(f"Error getting weekly stats: {e}")
        
        return stats
    
    def get_past_day_stats(self) -> Dict[str, Dict[str, int]]:
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
            logging.error(f"Error getting past day stats: {e}")
        
        return stats
    
    def get_past_week_stats(self) -> Dict[str, Dict[str, int]]:
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
            logging.error(f"Error getting past week stats: {e}")
        
        return stats
    
    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a value from the key-value store."""
        try:
            with self.get_session() as session:
                kv_pair = session.query(KeyValueStore).filter(KeyValueStore.key == key).first()
                return kv_pair.value if kv_pair else default
        except SQLAlchemyError as e:
            logging.error(f"Error getting value for key '{key}': {e}")
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
            logging.error(f"Error setting value for key '{key}': {e}")
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
                    target.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                else:
                    target = LeetCodeTarget(
                        target_type=target_type,
                        easy_target=easy,
                        medium_target=medium,
                        hard_target=hard
                    )
                    session.add(target)
                
                session.commit()
                logging.info(f"Set {target_type} LeetCode target: Easy={easy}, Medium={medium}, Hard={hard}")
                return True
                
        except SQLAlchemyError as e:
            logging.error(f"Error setting {target_type} target: {e}")
            return False
    
    def get_leetcode_target(self, target_type: str) -> Dict[str, int]:
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
            logging.error(f"Error getting {target_type} target: {e}")
            return {'easy': 0, 'medium': 0, 'hard': 0}

    def get_daily_breakdown(self, start_date: date, end_date: date) -> Dict[date, int]:
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
            logging.error(f"Error getting daily breakdown: {e}")

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
            logging.error(f"Error getting current streak: {e}")
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