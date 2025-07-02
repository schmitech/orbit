"""Global constants for ORBIT CLI."""

from pathlib import Path

# Configuration directories and files
DEFAULT_CONFIG_DIR = Path.home() / ".orbit"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_ENV_FILE = DEFAULT_CONFIG_DIR / ".env"  # Kept for backward compatibility
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"

# Keyring configuration
KEYRING_SERVICE = "orbit-cli"
KEYRING_TOKEN_KEY = "auth-token"
KEYRING_SERVER_KEY = "server-url"

# Default server configuration
DEFAULT_SERVER_URL = "http://localhost:3000"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_ATTEMPTS = 3

# CLI defaults
DEFAULT_OUTPUT_FORMAT = "table"
DEFAULT_SESSION_DURATION_HOURS = 12
DEFAULT_HISTORY_MAX_ENTRIES = 1000

# Server process management
DEFAULT_PID_FILE = "server.pid"
DEFAULT_SERVER_LOG_FILE = "orbit.log"