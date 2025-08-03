"""SQLAlchemy models for the database."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import ENUM

Base = declarative_base()


class SolvedProblem(Base):
    """Model for tracking solved problems."""
    __tablename__ = 'solved_problems'
    
    platform = Column(String, primary_key=True, nullable=False)
    problem_id = Column(String, primary_key=True, nullable=False)
    first_solve_date = Column(Date, nullable=False)
    rating = Column(String)
    
    def __repr__(self):
        return f"<SolvedProblem(platform='{self.platform}', problem_id='{self.problem_id}')>"


class KeyValueStore(Base):
    """Model for generic key-value storage."""
    __tablename__ = 'key_value_store'
    
    key = Column(String, primary_key=True, nullable=False)
    value = Column(Text)
    
    def __repr__(self):
        return f"<KeyValueStore(key='{self.key}')>"


class LeetCodeTarget(Base):
    """Model for LeetCode targets (daily, weekly, monthly)."""
    __tablename__ = 'leetcode_targets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    target_type = Column(String, nullable=False, unique=True)
    easy_target = Column(Integer, default=0)
    medium_target = Column(Integer, default=0)
    hard_target = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint("target_type IN ('daily', 'weekly', 'monthly')", name='check_target_type'),
    )
    
    def __repr__(self):
        return f"<LeetCodeTarget(target_type='{self.target_type}')>"