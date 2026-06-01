"""Tests for Telegram bot functionality."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from helix_telegram.models import TelegramUser
from helix_telegram.templates import TelegramTemplates
from helix_telegram.service import format_alert_message

def test_telegram_user_model():
    """Test TelegramUser model creation."""
    # Create in-memory database for testing
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    
    try:
        # Create a test user
        user = TelegramUser(
            telegram_id=123456789,
            username="testuser",
            first_name="Test",
            last_name="User",
            is_subscribed=True,
            preferred_assets="USDT,USDC",
            alert_types="signal,anomaly",
            min_severity="medium",
            timezone="America/New_York",
            receive_digest=True,
            digest_time="09:00"
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Verify user was created correctly
        assert user.telegram_id == 123456789
        assert user.username == "testuser"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.is_subscribed == True
        assert user.preferred_assets == "USDT,USDC"
        assert user.alert_types == "signal,anomaly"
        assert user.min_severity == "medium"
        assert user.timezone == "America/New_York"
        assert user.receive_digest == True
        assert user.digest_time == "09:00"
        
        # Test string representation
        assert "TelegramUser" in str(user)
        assert "123456789" in str(user)
        
    finally:
        db.close()

def test_format_signal_event():
    """Test formatting of signal events."""
    event_data = {
        "asset_symbol": "USDT",
        "event_type": "depeg",
        "severity": "high",
        "title": "Depeg Detected",
        "summary": "USDT has deviated from its peg by more than 0.5%",
        "chain_key": "ethereum",
        "timestamp": "2026-06-01T10:30:00Z"
    }
    
    message = TelegramTemplates.format_signal_event(event_data)
    
    # Check that key elements are present
    assert "🔴" in message or "🟠" in message  # High severity emoji
    assert "Depeg Detected" in message
    assert "USDT" in message
    assert "HIGH" in message
    assert "ethereum" in message
    assert "🔗 *View Details:*" in message

def test_format_anomaly_alert():
    """Test formatting of anomaly alerts."""
    anomaly_data = {
        "asset": "USDC",
        "metric": "supply_velocity",
        "value": "2.5",
        "threshold": "2.0",
        "zscore": "3.2"
    }
    
    message = TelegramTemplates.format_anomaly_alert(anomaly_data)
    
    # Check that key elements are present
    assert "🔍" in message
    assert "Anomaly Detected" in message
    assert "USDC" in message
    assert "supply_velocity" in message
    assert "3.2" in message  # Z-score

def test_format_osint_article():
    """Test formatting of OSINT articles."""
    article_data = {
        "title": "Stablecoin Regulations Tighten",
        "source": "CoinDesk",
        "summary": "New regulatory framework proposed for stablecoin issuers in the EU",
        "sentiment_label": "negative",
        "url": "https://coindesk.com/article",
        "published_at": "2026-06-01T09:00:00Z"
    }
    
    message = TelegramTemplates.format_osint_article(article_data)
    
    # Check that key elements are present
    assert "📰" in message
    assert "Stablecoin Regulations Tighten" in message
    assert "CoinDesk" in message
    assert "🔴" in message  # Negative sentiment
    assert "New regulatory framework" in message

def test_format_system_status():
    """Test formatting of system status updates."""
    status_data = {
        "status": "ok",
        "db": True,
        "sources_down": 0,
        "version": "3.8.2.1"
    }
    
    message = TelegramTemplates.format_system_status(status_data)
    
    # Check that key elements are present
    assert "✅" in message
    assert "System Status Update" in message
    assert "OK" in message
    assert "3.8.2.1" in message

def test_format_forecast_update():
    """Test formatting of forecast updates."""
    forecast_data = {
        "asset": "DAI",
        "direction": "increase",
        "confidence": 0.85,
        "timestamp": "2026-06-01T10:00:00Z"
    }
    
    message = TelegramTemplates.format_forecast_update(forecast_data)
    
    # Check that key elements are present
    assert "📈" in message  # Increase direction
    assert "Forecast Update" in message
    assert "DAI" in message
    assert "85%" in message

@pytest.mark.asyncio
@patch('helix_telegram.bot.BOT_TOKEN', 'test_token')
@patch('helix_telegram.bot.Application')
async def test_send_alert_to_user(mock_application):
    """Test sending alert to user."""
    from helix_telegram.bot import send_alert_to_user
    
    # Mock the application and bot
    mock_app_instance = Mock()
    mock_application.builder.return_value.token.return_value.build.return_value = mock_app_instance
    mock_app_instance.bot.send_message = AsyncMock()
    
    # Test sending alert
    success = await send_alert_to_user(123456789, "Test message")
    
    # Verify the bot send_message was called
    mock_app_instance.bot.send_message.assert_called_once_with(
        chat_id=123456789,
        text="Test message",
        parse_mode="Markdown"
    )
    
    # Should return True (success)
    assert success == True

@pytest.mark.asyncio
@patch('helix_telegram.bot.BOT_TOKEN', 'test_token')
@patch('helix_telegram.bot.Application')
async def test_send_alert_to_channel(mock_application):
    """Test sending alert to channel."""
    from helix_telegram.bot import send_alert_to_channel
    
    # Mock the application and bot
    mock_app_instance = Mock()
    mock_application.builder.return_value.token.return_value.build.return_value = mock_app_instance
    mock_app_instance.bot.send_message = AsyncMock()
    
    # Test sending alert
    success = await send_alert_to_channel("@testchannel", "Test message")
    
    # Verify the bot send_message was called
    mock_app_instance.bot.send_message.assert_called_once_with(
        chat_id="@testchannel",
        text="Test message",
        parse_mode="Markdown"
    )
    
    # Should return True (success)
    assert success == True

def test_templates_constants():
    """Test template constants."""
    from helix_telegram.templates import (
        WELCOME_MESSAGE, HELP_MESSAGE, SUBSCRIBE_SUCCESS, 
        UNSUBSCRIBE_SUCCESS, STATUS_SUBSCRIBED, STATUS_UNSUBSCRIBED
    )
    
    # Verify templates exist and are strings
    assert isinstance(WELCOME_MESSAGE, str)
    assert "Welcome" in WELCOME_MESSAGE
    assert isinstance(HELP_MESSAGE, str)
    assert "Commands" in HELP_MESSAGE
    assert isinstance(SUBSCRIBE_SUCCESS, str)
    assert "subscribed" in SUBSCRIBE_SUCCESS.lower()
    assert isinstance(UNSUBSCRIBE_SUCCESS, str)
    assert "unsubscribed" in UNSUBSCRIBE_SUCCESS.lower()
    assert isinstance(STATUS_SUBSCRIBED, str)
    assert isinstance(STATUS_UNSUBSCRIBED, str)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])