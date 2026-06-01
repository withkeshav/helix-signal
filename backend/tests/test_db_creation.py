import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import Base
from providers.settings import Setting

# Set admin token for tests
os.environ["HELIX_ADMIN_TOKEN"] = "test_token"

# Create a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_db_table_creation():
    """Test that database tables are created correctly"""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Check if settings table exists
    db = TestingSessionLocal()
    try:
        # Try to query the settings table
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")).fetchone()
        assert result is not None, "Settings table should exist"
        
        # Try to insert a setting
        db.add(Setting(key="test_key", value="test_value"))
        db.commit()
        
        # Try to query the setting
        setting = db.query(Setting).filter(Setting.key == "test_key").first()
        assert setting is not None, "Setting should exist"
        assert setting.value == "test_value", "Setting value should match"
    finally:
        db.close()
        
    # Clean up
    Base.metadata.drop_all(bind=engine)