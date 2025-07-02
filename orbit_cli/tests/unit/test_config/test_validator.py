"""
Unit tests for configuration validator.
"""

import pytest
from unittest.mock import Mock, patch

from orbit_cli.config.validator import ConfigValidator
from orbit_cli.core.exceptions import ConfigurationError


class TestConfigValidator:
    """Test cases for ConfigValidator class."""

    @pytest.mark.unit
    def test_init(self):
        """Test ConfigValidator initialization."""
        validator = ConfigValidator()
        assert validator is not None

    @pytest.mark.unit
    def test_validate_valid_config(self, sample_config):
        """Test validating a valid configuration."""
        validator = ConfigValidator()
        
        # Should not raise an exception
        validator.validate(sample_config)

    @pytest.mark.unit
    def test_validate_missing_server_section(self):
        """Test validating config with missing server section."""
        config = {
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Missing required section: server"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_missing_auth_section(self):
        """Test validating config with missing auth section."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Missing required section: auth"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_missing_api_section(self):
        """Test validating config with missing api section."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Missing required section: api"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_server_host_invalid(self):
        """Test validating config with invalid server host."""
        config = {
            "server": {"host": "invalid-host", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Invalid server host"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_server_port_invalid_type(self):
        """Test validating config with invalid server port type."""
        config = {
            "server": {"host": "localhost", "port": "invalid"},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Server port must be an integer"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_server_port_out_of_range(self):
        """Test validating config with server port out of range."""
        config = {
            "server": {"host": "localhost", "port": 99999},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Server port must be between 1024 and 65535"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_auth_enabled_invalid_type(self):
        """Test validating config with invalid auth enabled type."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": "invalid"},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Auth enabled must be a boolean"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_auth_token_expiry_invalid(self):
        """Test validating config with invalid auth token expiry."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True, "token_expiry": -1},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Auth token expiry must be positive"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_api_base_url_invalid(self):
        """Test validating config with invalid API base URL."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "invalid-url"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Invalid API base URL"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_api_timeout_invalid(self):
        """Test validating config with invalid API timeout."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000", "timeout": -1}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="API timeout must be positive"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_server_debug_optional(self):
        """Test that server debug is optional and defaults to False."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        # Should not raise an exception
        validator.validate(config)

    @pytest.mark.unit
    def test_validate_server_debug_valid(self):
        """Test validating config with valid server debug setting."""
        config = {
            "server": {"host": "localhost", "port": 8000, "debug": True},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        # Should not raise an exception
        validator.validate(config)

    @pytest.mark.unit
    def test_validate_server_debug_invalid_type(self):
        """Test validating config with invalid server debug type."""
        config = {
            "server": {"host": "localhost", "port": 8000, "debug": "invalid"},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Server debug must be a boolean"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_auth_token_expiry_optional(self):
        """Test that auth token expiry is optional and has default."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        # Should not raise an exception
        validator.validate(config)

    @pytest.mark.unit
    def test_validate_api_timeout_optional(self):
        """Test that API timeout is optional and has default."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"}
        }
        
        validator = ConfigValidator()
        
        # Should not raise an exception
        validator.validate(config)

    @pytest.mark.unit
    def test_validate_extra_sections_allowed(self):
        """Test that extra sections are allowed in config."""
        config = {
            "server": {"host": "localhost", "port": 8000},
            "auth": {"enabled": True},
            "api": {"base_url": "http://localhost:8000"},
            "extra_section": {"key": "value"}
        }
        
        validator = ConfigValidator()
        
        # Should not raise an exception
        validator.validate(config)

    @pytest.mark.unit
    def test_validate_empty_config(self):
        """Test validating empty configuration."""
        config = {}
        
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Missing required section: server"):
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_none_config(self):
        """Test validating None configuration."""
        validator = ConfigValidator()
        
        with pytest.raises(ConfigurationError, match="Configuration cannot be None"):
            validator.validate(None)

    @pytest.mark.unit
    def test_validate_server_host_valid_values(self):
        """Test validating server host with valid values."""
        valid_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
        
        validator = ConfigValidator()
        
        for host in valid_hosts:
            config = {
                "server": {"host": host, "port": 8000},
                "auth": {"enabled": True},
                "api": {"base_url": "http://localhost:8000"}
            }
            
            # Should not raise an exception
            validator.validate(config)

    @pytest.mark.unit
    def test_validate_api_base_url_valid_formats(self):
        """Test validating API base URL with valid formats."""
        valid_urls = [
            "http://localhost:8000",
            "https://api.example.com",
            "http://127.0.0.1:9000"
        ]
        
        validator = ConfigValidator()
        
        for url in valid_urls:
            config = {
                "server": {"host": "localhost", "port": 8000},
                "auth": {"enabled": True},
                "api": {"base_url": url}
            }
            
            # Should not raise an exception
            validator.validate(config) 