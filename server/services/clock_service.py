"""
Clock Service for providing timezone-aware timestamps.
"""

import logging
from datetime import datetime
from typing import Optional

# Use zoneinfo if available (Python 3.9+), otherwise fallback to pytz
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    try:
        from pytz import timezone as ZoneInfo, UnknownTimeZoneError as ZoneInfoNotFoundError
    except ImportError:
        logger.error("Neither 'zoneinfo' nor 'pytz' is available. Please install pytz: pip install pytz")
        ZoneInfo = None
        ZoneInfoNotFoundError = None


logger = logging.getLogger(__name__)

class ClockService:
    def __init__(self, config: dict):
        self.enabled = config.get('enabled', False)
        self.default_timezone = config.get('default_timezone', 'UTC')
        self.format = config.get('format', '%Y-%m-%d %H:%M:%S %Z')
        if self.enabled:
            logger.info(f"ClockService initialized. Enabled: {self.enabled}, Default Timezone: {self.default_timezone}")

    def get_current_time_str(self, timezone_str: Optional[str] = None) -> Optional[str]:
        """
        Get the current time as a formatted string for a given timezone.
        """
        if not self.enabled or not ZoneInfo:
            return None

        target_timezone = timezone_str or self.default_timezone
        try:
            tz = ZoneInfo(target_timezone)
            now = datetime.now(tz)
            return now.strftime(self.format)
        except ZoneInfoNotFoundError:
            logger.warning(f"Timezone '{target_timezone}' not found. Falling back to default.")
            # Fallback to default timezone
            try:
                tz = ZoneInfo(self.default_timezone)
                now = datetime.now(tz)
                return now.strftime(self.format)
            except ZoneInfoNotFoundError:
                logger.error(f"Default timezone '{self.default_timezone}' also not found. Returning UTC time.")
                return datetime.utcnow().strftime(self.format)
        except Exception as e:
            logger.error(f"Error getting current time: {e}")
            return None
