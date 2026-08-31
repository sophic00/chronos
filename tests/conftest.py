import os

import pytest

# Override environment variables for isolated testing before importing chronos modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["BOT_TOKEN"] = "mock_bot_token"
os.environ["CHANNEL_ID"] = "123456789"
os.environ["CF_HANDLE"] = "mock_cf_handle"
os.environ["LEETCODE_USERNAME"] = "mock_lc_username"
os.environ["TIMEZONE"] = "UTC"

from chronos.config import settings
from chronos.data.database import Base, db_service


@pytest.fixture(scope="session", autouse=True)
def init_test_settings():
    """Ensures test settings are fully validated and ready."""
    settings.validate_settings()

@pytest.fixture(autouse=True)
def clean_db():
    """Wipes and recreates the database tables before every test to ensure isolation."""
    Base.metadata.create_all(bind=db_service.engine)
    yield db_service
    Base.metadata.drop_all(bind=db_service.engine)
