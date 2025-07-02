"""Unit tests for ConfigManager."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

from orbit_cli.config.manager import ConfigManager
from orbit_cli.core.exceptions import ConfigurationError


class TestConfigManager:
    """Test cases for ConfigManager."""
    
    def test_init(self, temp_config_dir):
        """Test ConfigManager initialization."""
        manager = ConfigManager(config_dir=temp_config_dir)
        assert manager.config_dir == temp_config_dir
        assert manager.config_file == temp_config_dir / "config.json"
        assert temp_config_dir.exists()
    
    def test_ensure_config_dir(self, temp_dir):
        """Test config directory creation."""
        config_dir = temp_dir / "test_orbit"
        manager = ConfigManager(config_dir=config_dir)
        
        assert config_dir.exists()
        assert config_dir.stat().st_mode & 0o777 == 0o700
    
    def test_load_config_default(self, temp_config_dir):
        """Test loading default configuration."""
        manager = ConfigManager(config_dir=temp_config_dir)
        config = manager.load_config()
        
        assert isinstance(config, dict)
        assert "server" in config
        assert "auth" in config
        assert "output" in config
    
    def test_load_config_from_file(self, temp_config_dir):
        """Test loading configuration from file."""
        config_file = temp_config_dir / "config.json"
        test_config = {
            "server": {"default_url": "http://test:8080"},
            "output": {"format": "json"}
        }
        
        with open(config_file, 'w') as f:
            json.dump(test_config, f)
        
        manager = ConfigManager(config_dir=temp_config_dir)
        config = manager.load_config()
        
        assert config["server"]["default_url"] == "http://test:8080"
        assert config["output"]["format"] == "json"
    
    def test_load_config_invalid_json(self, temp_config_dir):
        """Test loading invalid JSON configuration."""
        config_file = temp_config_dir / "config.json"
        
        with open(config_file, 'w') as f:
            f.write("invalid json")
        
        manager = ConfigManager(config_dir=temp_config_dir)
        
        with pytest.raises(ConfigurationError) as exc_info:
            manager.load_config()
        
        assert "Invalid configuration file" in str(exc_info.value)
    
    def test_save_config(self, temp_config_dir):
        """Test saving configuration."""
        manager = ConfigManager(config_dir=temp_config_dir)
        test_config = {"test": "value"}
        
        manager.save_config(test_config)
        
        # Verify file was created with correct permissions
        assert manager.config_file.exists()
        assert manager.config_file.stat().st_mode & 0o777 == 0o600
        
        # Verify content
        with open(manager.config_file, 'r') as f:
            saved = json.load(f)
        assert saved == test_config
    
    def test_get_value(self, temp_config_dir):
        """Test getting configuration values."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Test getting existing value
        value = manager.get("server.default_url")
        assert value == "http://localhost:3000"
        
        # Test getting nested value
        value = manager.get("server.timeout")
        assert value == 30
        
        # Test getting non-existent value with default
        value = manager.get("non.existent", "default")
        assert value == "default"
    
    def test_set_value(self, temp_config_dir):
        """Test setting configuration values."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Set a new value
        manager.set("test.key", "test_value")
        
        # Verify it was set
        assert manager.get("test.key") == "test_value"
        
        # Verify it was saved
        with open(manager.config_file, 'r') as f:
            saved = json.load(f)
        assert saved["test"]["key"] == "test_value"
    
    def test_get_server_url(self, temp_config_dir):
        """Test getting server URL with precedence."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Test default
        url = manager.get_server_url()
        assert url == "http://localhost:3000"
        
        # Test override
        url = manager.get_server_url("http://override:8080")
        assert url == "http://override:8080"
        
        # Test trailing slash removal
        url = manager.get_server_url("http://test:8080/")
        assert url == "http://test:8080"
    
    @patch('orbit_cli.config.manager.KEYRING_AVAILABLE', True)
    def test_get_auth_storage_method_keyring(self, temp_config_dir):
        """Test getting auth storage method with keyring available."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Default should prefer keyring if available
        method = manager.get_auth_storage_method()
        assert method == "keyring"
    
    @patch('orbit_cli.config.manager.KEYRING_AVAILABLE', False)
    def test_get_auth_storage_method_no_keyring(self, temp_config_dir):
        """Test getting auth storage method without keyring."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Should fall back to file
        method = manager.get_auth_storage_method()
        assert method == "file"
    
    def test_config_caching(self, temp_config_dir):
        """Test configuration caching."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Load config first time
        config1 = manager.load_config()
        
        # Modify the file
        manager.config_file.write_text('{"modified": true}')
        
        # Should still get cached version
        config2 = manager.load_config()
        assert config1 == config2
        
        # Invalidate cache
        manager._config_cache = None
        
        # Now should get new version
        config3 = manager.load_config()
        assert config3 != config1
        assert config3["modified"] is True
    
    def test_get_effective_config(self, temp_config_dir):
        """Test getting effective configuration."""
        manager = ConfigManager(config_dir=temp_config_dir)
        
        # Set a CLI config value
        manager.set("server.timeout", 60)
        
        # Get effective config
        effective = manager.get_effective_config()
        
        assert "cli_config" in effective
        assert "server_config" in effective
        assert "effective_values" in effective
        assert "sources" in effective
        
        # Check that CLI config overrides default
        assert effective["effective_values"]["server.timeout"] == 60
        assert effective["sources"]["server.timeout"] == "cli_config"