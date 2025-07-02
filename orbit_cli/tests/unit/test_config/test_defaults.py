"""
Unit tests for configuration defaults.
"""

import pytest
from unittest.mock import patch

from orbit_cli.config.defaults import (
    DEFAULT_CONFIG,
    get_default_config,
    get_server_defaults,
    get_auth_defaults,
    get_api_defaults,
    get_logging_defaults
)


class TestDefaults:
    """Test cases for configuration defaults."""

    @pytest.mark.unit
    def test_default_config_structure(self):
        """Test that default config has required sections."""
        assert "server" in DEFAULT_CONFIG
        assert "auth" in DEFAULT_CONFIG
        assert "api" in DEFAULT_CONFIG
        assert "logging" in DEFAULT_CONFIG

    @pytest.mark.unit
    def test_get_default_config(self):
        """Test getting default configuration."""
        config = get_default_config()
        
        assert isinstance(config, dict)
        assert config == DEFAULT_CONFIG

    @pytest.mark.unit
    def test_get_server_defaults(self):
        """Test getting server defaults."""
        server_defaults = get_server_defaults()
        
        assert isinstance(server_defaults, dict)
        assert "host" in server_defaults
        assert "port" in server_defaults
        assert "debug" in server_defaults
        assert server_defaults["host"] == "localhost"
        assert isinstance(server_defaults["port"], int)
        assert isinstance(server_defaults["debug"], bool)

    @pytest.mark.unit
    def test_get_auth_defaults(self):
        """Test getting auth defaults."""
        auth_defaults = get_auth_defaults()
        
        assert isinstance(auth_defaults, dict)
        assert "enabled" in auth_defaults
        assert "token_expiry" in auth_defaults
        assert isinstance(auth_defaults["enabled"], bool)
        assert isinstance(auth_defaults["token_expiry"], int)

    @pytest.mark.unit
    def test_get_api_defaults(self):
        """Test getting API defaults."""
        api_defaults = get_api_defaults()
        
        assert isinstance(api_defaults, dict)
        assert "base_url" in api_defaults
        assert "timeout" in api_defaults
        assert isinstance(api_defaults["timeout"], int)

    @pytest.mark.unit
    def test_get_logging_defaults(self):
        """Test getting logging defaults."""
        logging_defaults = get_logging_defaults()
        
        assert isinstance(logging_defaults, dict)
        assert "level" in logging_defaults
        assert "format" in logging_defaults
        assert "file" in logging_defaults

    @pytest.mark.unit
    def test_server_port_range(self):
        """Test that server port is within valid range."""
        server_defaults = get_server_defaults()
        port = server_defaults["port"]
        
        assert 1024 <= port <= 65535

    @pytest.mark.unit
    def test_auth_token_expiry_positive(self):
        """Test that auth token expiry is positive."""
        auth_defaults = get_auth_defaults()
        token_expiry = auth_defaults["token_expiry"]
        
        assert token_expiry > 0

    @pytest.mark.unit
    def test_api_timeout_positive(self):
        """Test that API timeout is positive."""
        api_defaults = get_api_defaults()
        timeout = api_defaults["timeout"]
        
        assert timeout > 0

    @pytest.mark.unit
    def test_logging_level_valid(self):
        """Test that logging level is valid."""
        logging_defaults = get_logging_defaults()
        level = logging_defaults["level"]
        
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert level in valid_levels

    @pytest.mark.unit
    def test_default_config_immutability(self):
        """Test that default config is not modified when accessed."""
        original_config = DEFAULT_CONFIG.copy()
        
        # Access the config multiple times
        get_default_config()
        get_default_config()
        
        assert DEFAULT_CONFIG == original_config

    @pytest.mark.unit
    def test_server_host_valid(self):
        """Test that server host is a valid value."""
        server_defaults = get_server_defaults()
        host = server_defaults["host"]
        
        assert host in ["localhost", "127.0.0.1", "0.0.0.0"]

    @pytest.mark.unit
    def test_api_base_url_format(self):
        """Test that API base URL has correct format."""
        api_defaults = get_api_defaults()
        base_url = api_defaults["base_url"]
        
        assert base_url.startswith(("http://", "https://"))
        assert "://" in base_url

    @pytest.mark.unit
    def test_logging_format_valid(self):
        """Test that logging format is a valid string."""
        logging_defaults = get_logging_defaults()
        log_format = logging_defaults["format"]
        
        assert isinstance(log_format, str)
        assert len(log_format) > 0
        assert "%" in log_format  # Should contain format specifiers

    @pytest.mark.unit
    def test_default_config_deep_copy(self):
        """Test that default config returns a deep copy."""
        config1 = get_default_config()
        config2 = get_default_config()
        
        # Modify one config
        config1["server"]["port"] = 9999
        
        # Other config should remain unchanged
        assert config2["server"]["port"] != 9999

    @pytest.mark.unit
    def test_auth_enabled_default(self):
        """Test that auth is enabled by default."""
        auth_defaults = get_auth_defaults()
        
        assert auth_defaults["enabled"] is True

    @pytest.mark.unit
    def test_server_debug_default(self):
        """Test that server debug is disabled by default."""
        server_defaults = get_server_defaults()
        
        assert server_defaults["debug"] is False 