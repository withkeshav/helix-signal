import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
from providers.settings import Setting

_tmpdb_path = None
_orig_token = None

@pytest.fixture(scope="module")
def test_app():
    global _tmpdb_path, _orig_token
    # Save + set admin token (conftest may have overridden it)
    _orig_token = os.environ.get("HELIX_ADMIN_TOKEN")
    os.environ["HELIX_ADMIN_TOKEN"] = "test_token"
    # Use a temp file so all sessions share the same database
    _tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmpdb.close()
    _tmpdb_path = _tmpdb.name
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{_tmpdb.name}"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Override the get_db dependency
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    
    # Create all tables in the test database
    Base.metadata.create_all(bind=engine)
    
    # Add some test settings data
    db = TestingSessionLocal()
    try:
        # Add some sample settings for testing
        test_settings = [
            ("ai_mode", "ai_full"),
            ("ai_daily_token_budget", "50000"),
            ("feature_ai_summary", "true"),
            ("provider_coingecko", "true"),
        ]
        
        for key, value in test_settings:
            db.add(Setting(key=key, value=value))
        
        db.commit()
    finally:
        db.close()
    
    yield app
    
    # Clean up
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    if _tmpdb_path and os.path.exists(_tmpdb_path):
        os.unlink(_tmpdb_path)
    # Restore original admin token
    if _orig_token is not None:
        os.environ["HELIX_ADMIN_TOKEN"] = _orig_token
    else:
        os.environ.pop("HELIX_ADMIN_TOKEN", None)

@pytest.fixture
def client(test_app):
    return TestClient(test_app)

def test_settings_search(client):
    """Test settings search functionality"""
    # Test search by key
    response = client.get("/api/settings?search=ai", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    
    # Should have AI-related settings
    assert len(settings) > 0
    assert any("ai" in setting["key"].lower() for setting in settings)
    
    # Test search by label
    response = client.get("/api/settings?search=AI Mode", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    
    # Should find the AI mode setting
    assert len(settings) > 0
    assert any("ai_mode" == setting["key"] for setting in settings)
    
    # Test search with no results
    response = client.get("/api/settings?search=nonexistentsetting", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    assert len(settings) == 0

def test_settings_group_filter(client):
    """Test settings group filtering"""
    # Test filter by group - need to URL encode the group name
    response = client.get("/api/settings?group=AI%20%26%20Intelligence", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    
    # Should only have settings from AI & Intelligence group
    assert len(settings) > 0
    
    # Test filter by non-existent group
    response = client.get("/api/settings?group=NonExistentGroup", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    assert len(settings) == 0

def test_settings_combined_search_and_group(client):
    """Test combined search and group filtering"""
    # Test search within a specific group - need to URL encode the group name
    response = client.get("/api/settings?search=ai&group=AI%20%26%20Intelligence", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    
    # Should have AI settings from AI & Intelligence group
    assert len(settings) > 0

def test_settings_no_filters(client):
    """Test settings endpoint without filters"""
    response = client.get("/api/settings", headers={"X-Admin-Token": "test_token"})
    assert response.status_code == 200
    settings = response.json()
    
    # Should have all settings
    assert len(settings) > 0