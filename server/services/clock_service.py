"""
Clock Service for providing timezone-aware timestamps.

This service provides configurable, timezone-aware date/time information
that can be injected into LLM prompts for temporal context.
"""

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional, Dict, Any
from functools import lru_cache

# Define logger first (before any imports that might fail)
logger = logging.getLogger(__name__)

# Track which timezone library is available
_using_pytz = False
_timezone_available = False

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    _timezone_available = True
except ImportError:
    try:
        import pytz
        _using_pytz = True
        _timezone_available = True

        # Create wrapper exception for pytz compatibility
        ZoneInfoNotFoundError = pytz.UnknownTimeZoneError

        # Wrapper class to make pytz work like zoneinfo
        class ZoneInfo:
            """Wrapper to provide zoneinfo-compatible API for pytz."""
            def __init__(self, key: str):
                self._tz = pytz.timezone(key)
                self._key = key

            @property
            def key(self) -> str:
                return self._key

            def __repr__(self) -> str:
                return f"ZoneInfo(key='{self._key}')"

    except ImportError:
        logger.error(
            "Neither 'zoneinfo' nor 'pytz' is available. "
            "Clock service will be disabled. "
            "Please install pytz: pip install pytz"
        )
        ZoneInfo = None
        ZoneInfoNotFoundError = Exception


@lru_cache(maxsize=64)
def _get_cached_timezone(tz_name: str):
    """
    Get a cached timezone object.

    Args:
        tz_name: The timezone name (e.g., 'America/New_York')

    Returns:
        A timezone object (ZoneInfo or pytz wrapper)

    Raises:
        ZoneInfoNotFoundError: If the timezone is not found
    """
    if not _timezone_available or ZoneInfo is None:
        return None
    return ZoneInfo(tz_name)


def _get_current_time_for_tz(tz_obj) -> datetime:
    """
    Get the current time for a timezone object, handling pytz vs zoneinfo differences.

    Args:
        tz_obj: A timezone object (ZoneInfo or pytz wrapper)

    Returns:
        A timezone-aware datetime
    """
    if _using_pytz:
        # For pytz, we need to use UTC and then convert
        utc_now = datetime.now(pytz.UTC)
        return utc_now.astimezone(tz_obj._tz)
    else:
        # For zoneinfo, datetime.now(tz) works correctly
        return datetime.now(tz_obj)


class ClockService:
    """
    Service for providing timezone-aware timestamps.

    This service is used to inject current date/time information into LLM
    prompts, enabling temporal awareness in responses.
    """

    DEFAULT_FORMAT = '%Y-%m-%d %H:%M:%S %Z'
    DEFAULT_INSTRUCTION_TEMPLATE = "System: The current date and time is {time}."

    def __init__(self, config: dict):
        """
        Initialize the ClockService.

        Args:
            config: Configuration dictionary with keys:
                - enabled: Whether the service is enabled
                - default_timezone: Default timezone (e.g., 'America/New_York')
                - format: strftime format string
                - instruction_template: Template for time instruction (uses {time} placeholder)
        """
        self.enabled = config.get('enabled', False)
        self.default_timezone = config.get('default_timezone', 'UTC')
        self.format = config.get('format', self.DEFAULT_FORMAT)
        self.instruction_template = config.get(
            'instruction_template',
            self.DEFAULT_INSTRUCTION_TEMPLATE
        )

        # Check if timezone support is available
        if self.enabled and not _timezone_available:
            logger.warning(
                "ClockService is enabled but no timezone library is available. "
                "Service will be disabled."
            )
            self.enabled = False

        # Validate default timezone at startup
        self._default_tz_valid = False
        if self.enabled:
            self._validate_default_timezone()

        if self.enabled:
            logger.info(
                f"ClockService initialized. Enabled: {self.enabled}, "
                f"Default Timezone: {self.default_timezone}, "
                f"Using pytz: {_using_pytz}"
            )

    def _validate_default_timezone(self) -> None:
        """Validate that the default timezone is valid at startup."""
        try:
            _get_cached_timezone(self.default_timezone)
            self._default_tz_valid = True
            logger.debug(f"Default timezone '{self.default_timezone}' validated successfully.")
        except (ZoneInfoNotFoundError, Exception) as e:
            logger.warning(
                f"Default timezone '{self.default_timezone}' is invalid: {e}. "
                f"Falling back to UTC."
            )
            self.default_timezone = 'UTC'
            try:
                _get_cached_timezone('UTC')
                self._default_tz_valid = True
            except Exception:
                logger.error("Failed to validate UTC timezone. Clock service may not work.")
                self._default_tz_valid = False

    def get_current_time_str(
        self,
        timezone_str: Optional[str] = None,
        format_str: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the current time as a formatted string for a given timezone.

        Args:
            timezone_str: Optional timezone to use (defaults to default_timezone)
            format_str: Optional strftime format to use (defaults to configured format)

        Returns:
            Formatted time string, or None if service is disabled or unavailable
        """
        if not self.enabled or not _timezone_available:
            return None

        target_timezone = timezone_str or self.default_timezone
        target_format = format_str or self.format

        try:
            tz = _get_cached_timezone(target_timezone)
            now = _get_current_time_for_tz(tz)
            return now.strftime(target_format)
        except ZoneInfoNotFoundError:
            logger.warning(
                f"Timezone '{target_timezone}' not found. Falling back to default."
            )
            # Fallback to default timezone
            try:
                tz = _get_cached_timezone(self.default_timezone)
                now = _get_current_time_for_tz(tz)
                return now.strftime(target_format)
            except ZoneInfoNotFoundError:
                logger.error(
                    f"Default timezone '{self.default_timezone}' also not found. "
                    f"Returning UTC time."
                )
                return datetime.now(dt_timezone.utc).strftime(target_format)
        except Exception as e:
            logger.error(f"Error getting current time: {e}")
            return None

    def get_time_instruction(
        self,
        timezone_str: Optional[str] = None,
        format_str: Optional[str] = None
    ) -> str:
        """
        Get the formatted time instruction for injection into prompts.

        Args:
            timezone_str: Optional timezone to use
            format_str: Optional strftime format to use

        Returns:
            Formatted instruction string, or empty string if service is disabled
        """
        if not self.enabled:
            return ""

        time_str = self.get_current_time_str(timezone_str, format_str)
        if not time_str:
            return ""

        return self.instruction_template.format(time=time_str)

    def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the clock service.

        Returns:
            Dictionary with service health information:
                - enabled: Whether the service is enabled
                - timezone_library: Which library is being used (zoneinfo/pytz/none)
                - default_timezone: The configured default timezone
                - default_timezone_valid: Whether the default timezone is valid
                - sample_output: A sample formatted timestamp (if enabled)
                - format: The configured format string
                - instruction_template: The configured instruction template
        """
        sample_output = None
        if self.enabled and self._default_tz_valid:
            try:
                sample_output = self.get_current_time_str()
            except Exception as e:
                sample_output = f"Error: {e}"

        timezone_library = "none"
        if _timezone_available:
            timezone_library = "pytz" if _using_pytz else "zoneinfo"

        return {
            "enabled": self.enabled,
            "timezone_library": timezone_library,
            "default_timezone": self.default_timezone,
            "default_timezone_valid": self._default_tz_valid,
            "sample_output": sample_output,
            "format": self.format,
            "instruction_template": self.instruction_template
        }

    def is_healthy(self) -> bool:
        """
        Quick health check for the service.

        Returns:
            True if the service is enabled and working, False otherwise
        """
        if not self.enabled:
            return True  # Disabled is a valid state
        return self._default_tz_valid and self.get_current_time_str() is not None
