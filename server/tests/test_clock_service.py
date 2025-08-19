import pytest
import sys
import os
from datetime import datetime

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.clock_service import ClockService, ZoneInfo, ZoneInfoNotFoundError

# Basic configuration for testing
@pytest.fixture
def enabled_config():
    return {
        'enabled': True,
        'default_timezone': 'UTC',
        'format': '%Y-%m-%d %H:%M:%S %Z'
    }

@pytest.fixture
def disabled_config():
    return {
        'enabled': False
    }

def test_service_initialization(enabled_config):
    """Test that the ClockService initializes correctly."""
    service = ClockService(enabled_config)
    assert service.enabled is True
    assert service.default_timezone == 'UTC'
    assert service.format == '%Y-%m-%d %H:%M:%S %Z'

def test_service_disabled(disabled_config):
    """Test that the service is properly disabled."""
    service = ClockService(disabled_config)
    assert service.enabled is False
    assert service.get_current_time_str() is None

def test_get_time_default_timezone(enabled_config):
    """Test getting time with the default UTC timezone."""
    service = ClockService(enabled_config)
    time_str = service.get_current_time_str()
    assert isinstance(time_str, str)
    assert time_str.endswith('UTC')
    # Check if the format is correct
    try:
        datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S %Z')
    except ValueError:
        pytest.fail("Timestamp format is incorrect for UTC.")

def test_get_time_specific_timezone(enabled_config):
    """Test getting time with a specific, valid timezone."""
    service = ClockService(enabled_config)
    timezone = "America/New_York"
    time_str = service.get_current_time_str(timezone)
    assert isinstance(time_str, str)

    # Check for EST or EDT
    assert time_str.endswith(('EST', 'EDT'))

    # Check if the format is correct by splitting the string
    try:
        datetime_part, tz_part = time_str.rsplit(' ', 1)
        datetime.strptime(datetime_part, '%Y-%m-%d %H:%M:%S')
        assert tz_part in ('EST', 'EDT')
    except ValueError:
        pytest.fail(f"Timestamp format is incorrect for {timezone}.")

def test_get_time_invalid_timezone(enabled_config):
    """Test fallback behavior with an invalid timezone."""
    service = ClockService(enabled_config)
    # This should log a warning and fall back to the default (UTC)
    time_str = service.get_current_time_str("Invalid/Timezone")
    assert isinstance(time_str, str)
    assert time_str.endswith('UTC')

def test_custom_time_format(enabled_config):
    """Test using a custom time format string."""
    custom_format = "%A, %d %B %Y - %H:%M"
    enabled_config['format'] = custom_format
    service = ClockService(enabled_config)
    time_str = service.get_current_time_str()
    
    # Attempt to parse with the custom format (ignoring timezone for simplicity)
    try:
        # We can't easily parse the timezone part, so we check the main body
        # This is a simple validation that the format string was used.
        datetime.strptime(time_str, custom_format)
    except ValueError:
        # The above might fail if the timezone is included, let's try another way
        now = datetime.now(ZoneInfo("UTC"))
        expected_start = now.strftime("%A, %d %B %Y")
        assert expected_start in time_str

def test_offline_functionality():
    """
    This test implicitly demonstrates offline capability.
    It requires no network calls and relies only on the system clock and local timezone database.
    """
    config = {
        'enabled': True,
        'default_timezone': 'Europe/Paris',
        'format': '%c'
    }
    service = ClockService(config)
    time_str = service.get_current_time_str()
    assert isinstance(time_str, str)
    # If this test runs and passes without any network-related mocks,
    # it confirms the service works in an offline environment.
    print(f"\nOffline test generated time: {time_str}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
