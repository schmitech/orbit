import pytest
import sys
import os
from datetime import datetime

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.clock_service import (
    ClockService,
    ZoneInfo,
    _get_cached_timezone,
    _using_pytz
)


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


@pytest.fixture
def custom_template_config():
    return {
        'enabled': True,
        'default_timezone': 'UTC',
        'format': '%Y-%m-%d %H:%M:%S %Z',
        'instruction_template': 'Current time: {time}'
    }


class TestClockServiceInitialization:
    """Tests for ClockService initialization."""

    def test_service_initialization(self, enabled_config):
        """Test that the ClockService initializes correctly."""
        service = ClockService(enabled_config)
        assert service.enabled is True
        assert service.default_timezone == 'UTC'
        assert service.format == '%Y-%m-%d %H:%M:%S %Z'

    def test_service_disabled(self, disabled_config):
        """Test that the service is properly disabled."""
        service = ClockService(disabled_config)
        assert service.enabled is False
        assert service.get_current_time_str() is None

    def test_custom_instruction_template(self, custom_template_config):
        """Test custom instruction template configuration."""
        service = ClockService(custom_template_config)
        assert service.instruction_template == 'Current time: {time}'

    def test_default_instruction_template(self, enabled_config):
        """Test default instruction template."""
        service = ClockService(enabled_config)
        assert 'current date and time' in service.instruction_template.lower()


class TestTimezoneValidation:
    """Tests for timezone validation at startup."""

    def test_valid_default_timezone(self, enabled_config):
        """Test that a valid default timezone is accepted."""
        service = ClockService(enabled_config)
        assert service._default_tz_valid is True

    def test_invalid_default_timezone_falls_back_to_utc(self):
        """Test that invalid default timezone falls back to UTC."""
        config = {
            'enabled': True,
            'default_timezone': 'Invalid/Timezone',
            'format': '%Y-%m-%d %H:%M:%S %Z'
        }
        service = ClockService(config)
        # Should have fallen back to UTC
        assert service.default_timezone == 'UTC'
        assert service._default_tz_valid is True


class TestGetCurrentTimeStr:
    """Tests for get_current_time_str method."""

    def test_get_time_default_timezone(self, enabled_config):
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

    def test_get_time_specific_timezone(self, enabled_config):
        """Test getting time with a specific, valid timezone."""
        service = ClockService(enabled_config)
        timezone = "America/New_York"
        time_str = service.get_current_time_str(timezone)
        assert isinstance(time_str, str)
        # Check for EST or EDT
        assert time_str.endswith(('EST', 'EDT'))

    def test_get_time_invalid_timezone(self, enabled_config):
        """Test fallback behavior with an invalid timezone."""
        service = ClockService(enabled_config)
        # This should log a warning and fall back to the default (UTC)
        time_str = service.get_current_time_str("Invalid/Timezone")
        assert isinstance(time_str, str)
        assert time_str.endswith('UTC')

    def test_get_time_with_custom_format(self, enabled_config):
        """Test getting time with a custom format override."""
        service = ClockService(enabled_config)
        custom_format = "%Y-%m-%d"
        time_str = service.get_current_time_str(format_str=custom_format)
        assert isinstance(time_str, str)
        # Should match date-only format
        try:
            datetime.strptime(time_str, custom_format)
        except ValueError:
            pytest.fail("Custom format was not applied correctly.")

    def test_custom_time_format(self, enabled_config):
        """Test using a custom time format string."""
        custom_format = "%A, %d %B %Y - %H:%M"
        enabled_config['format'] = custom_format
        service = ClockService(enabled_config)
        time_str = service.get_current_time_str()

        # Verify the format was used
        now = datetime.now(ZoneInfo("UTC") if not _using_pytz else ZoneInfo("UTC"))
        # For pytz wrapper, handle specially
        if _using_pytz:
            import pytz
            now = datetime.now(pytz.UTC)
        expected_start = now.strftime("%A, %d %B %Y")
        assert expected_start in time_str


class TestGetTimeInstruction:
    """Tests for get_time_instruction method."""

    def test_get_time_instruction_default_template(self, enabled_config):
        """Test time instruction with default template."""
        service = ClockService(enabled_config)
        instruction = service.get_time_instruction()
        assert isinstance(instruction, str)
        assert 'current date and time' in instruction.lower()
        assert 'UTC' in instruction

    def test_get_time_instruction_custom_template(self, custom_template_config):
        """Test time instruction with custom template."""
        service = ClockService(custom_template_config)
        instruction = service.get_time_instruction()
        assert instruction.startswith('Current time:')

    def test_get_time_instruction_disabled(self, disabled_config):
        """Test time instruction returns empty when disabled."""
        service = ClockService(disabled_config)
        instruction = service.get_time_instruction()
        assert instruction == ""

    def test_get_time_instruction_with_timezone(self, enabled_config):
        """Test time instruction with specific timezone."""
        service = ClockService(enabled_config)
        instruction = service.get_time_instruction("America/New_York")
        assert isinstance(instruction, str)
        assert ('EST' in instruction or 'EDT' in instruction)


class TestHealthCheck:
    """Tests for health check functionality."""

    def test_health_check_enabled(self, enabled_config):
        """Test health check when service is enabled."""
        service = ClockService(enabled_config)
        health = service.health_check()

        assert health['enabled'] is True
        assert health['timezone_library'] in ('zoneinfo', 'pytz')
        assert health['default_timezone'] == 'UTC'
        assert health['default_timezone_valid'] is True
        assert health['sample_output'] is not None
        assert isinstance(health['sample_output'], str)
        assert health['format'] == '%Y-%m-%d %H:%M:%S %Z'

    def test_health_check_disabled(self, disabled_config):
        """Test health check when service is disabled."""
        service = ClockService(disabled_config)
        health = service.health_check()

        assert health['enabled'] is False
        assert health['sample_output'] is None

    def test_is_healthy_enabled(self, enabled_config):
        """Test is_healthy returns True when working correctly."""
        service = ClockService(enabled_config)
        assert service.is_healthy() is True

    def test_is_healthy_disabled(self, disabled_config):
        """Test is_healthy returns True when disabled (disabled is valid state)."""
        service = ClockService(disabled_config)
        assert service.is_healthy() is True


class TestTimezoneCaching:
    """Tests for timezone caching functionality."""

    def test_timezone_caching(self, enabled_config):
        """Test that timezone objects are cached."""
        service = ClockService(enabled_config)

        # Clear cache first
        _get_cached_timezone.cache_clear()

        # Get time multiple times with same timezone
        for _ in range(5):
            service.get_current_time_str("America/New_York")

        # Check cache info
        cache_info = _get_cached_timezone.cache_info()
        # Should have hits after the first call
        assert cache_info.hits >= 4  # At least 4 hits after 5 calls

    def test_different_timezones_cached_separately(self, enabled_config):
        """Test that different timezones are cached separately."""
        service = ClockService(enabled_config)

        # Clear cache first
        _get_cached_timezone.cache_clear()

        # Get time with different timezones
        service.get_current_time_str("America/New_York")
        service.get_current_time_str("Europe/London")
        service.get_current_time_str("Asia/Tokyo")

        # Check cache info
        cache_info = _get_cached_timezone.cache_info()
        assert cache_info.misses >= 3  # Each timezone is a cache miss first time


class TestOfflineCapability:
    """Tests for offline functionality."""

    def test_offline_functionality(self):
        """
        This test implicitly demonstrates offline capability.
        It requires no network calls and relies only on the system clock
        and local timezone database.
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


class TestPytzCompatibility:
    """Tests specifically for pytz compatibility (when applicable)."""

    @pytest.mark.skipif(not _using_pytz, reason="pytz not in use")
    def test_pytz_timezone_wrapper(self):
        """Test that pytz timezone wrapper works correctly."""
        config = {
            'enabled': True,
            'default_timezone': 'America/New_York',
            'format': '%Y-%m-%d %H:%M:%S %Z'
        }
        service = ClockService(config)

        # Get time for a timezone with DST
        time_str = service.get_current_time_str()
        assert isinstance(time_str, str)
        # Should end with EST or EDT depending on time of year
        assert time_str.endswith(('EST', 'EDT'))

    @pytest.mark.skipif(not _using_pytz, reason="pytz not in use")
    def test_pytz_dst_handling(self):
        """Test that DST is handled correctly with pytz."""
        config = {
            'enabled': True,
            'default_timezone': 'America/New_York',
            'format': '%Z'  # Just timezone abbreviation
        }
        service = ClockService(config)

        time_str = service.get_current_time_str()
        # Should be either EST or EDT
        assert time_str in ('EST', 'EDT')


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_config(self):
        """Test with empty config defaults to disabled."""
        service = ClockService({})
        assert service.enabled is False

    def test_none_timezone_uses_default(self, enabled_config):
        """Test that None timezone uses default."""
        service = ClockService(enabled_config)
        time_str = service.get_current_time_str(timezone_str=None)
        assert time_str.endswith('UTC')

    def test_instruction_template_placeholder(self):
        """Test that {time} placeholder in template works."""
        config = {
            'enabled': True,
            'default_timezone': 'UTC',
            'format': '%H:%M',
            'instruction_template': 'The time is exactly {time}.'
        }
        service = ClockService(config)
        instruction = service.get_time_instruction()
        assert 'The time is exactly' in instruction
        assert '{time}' not in instruction  # Placeholder should be replaced


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
