"""
Unit tests for configuration management components.

Tests:
- AdapterConfigManager
- ConfigChangeDetector
"""

import pytest
import sys
import os

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.config.adapter_config_manager import AdapterConfigManager
from services.config.config_change_detector import ConfigChangeDetector


class TestConfigChangeDetector:
    """Test ConfigChangeDetector class"""

    def test_configs_differ_identical(self):
        """Test configs_differ returns False for identical configs"""
        config1 = {'name': 'test', 'enabled': True, 'model': 'gpt-4'}
        config2 = {'name': 'test', 'enabled': True, 'model': 'gpt-4'}

        assert ConfigChangeDetector.configs_differ(config1, config2) is False

    def test_configs_differ_different(self):
        """Test configs_differ returns True for different configs"""
        config1 = {'name': 'test', 'enabled': True, 'model': 'gpt-4'}
        config2 = {'name': 'test', 'enabled': True, 'model': 'gpt-3.5'}

        assert ConfigChangeDetector.configs_differ(config1, config2) is True

    def test_configs_differ_nested(self):
        """Test configs_differ detects nested differences"""
        config1 = {'name': 'test', 'config': {'param1': 'value1'}}
        config2 = {'name': 'test', 'config': {'param1': 'value2'}}

        assert ConfigChangeDetector.configs_differ(config1, config2) is True

    def test_configs_differ_order_independent(self):
        """Test configs_differ is order independent"""
        config1 = {'b': 2, 'a': 1}
        config2 = {'a': 1, 'b': 2}

        assert ConfigChangeDetector.configs_differ(config1, config2) is False

    def test_detect_changes_no_changes(self):
        """Test detect_changes returns empty list when no changes"""
        config1 = {'name': 'test', 'inference_provider': 'openai', 'model': 'gpt-4'}
        config2 = {'name': 'test', 'inference_provider': 'openai', 'model': 'gpt-4'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert changes == []

    def test_detect_changes_inference_provider(self):
        """Test detect_changes detects inference_provider change"""
        config1 = {'inference_provider': 'openai'}
        config2 = {'inference_provider': 'anthropic'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'inference_provider: openai -> anthropic' in changes

    def test_detect_changes_model(self):
        """Test detect_changes detects model change"""
        config1 = {'model': 'gpt-4'}
        config2 = {'model': 'gpt-4-turbo'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'model: gpt-4 -> gpt-4-turbo' in changes

    def test_detect_changes_enabled(self):
        """Test detect_changes detects enabled status change"""
        config1 = {'enabled': True}
        config2 = {'enabled': False}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'enabled: True -> False' in changes

    def test_detect_changes_embedding_provider(self):
        """Test detect_changes detects embedding_provider change"""
        config1 = {'embedding_provider': 'openai'}
        config2 = {'embedding_provider': 'ollama'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'embedding_provider: openai -> ollama' in changes

    def test_detect_changes_reranker_provider(self):
        """Test detect_changes detects reranker_provider change"""
        config1 = {'reranker_provider': 'cohere'}
        config2 = {'reranker_provider': 'flashrank'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'reranker_provider: cohere -> flashrank' in changes

    def test_detect_changes_database(self):
        """Test detect_changes detects database change"""
        config1 = {'database': 'db1'}
        config2 = {'database': 'db2'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'database: db1 -> db2' in changes

    def test_detect_changes_nested_config(self):
        """Test detect_changes detects nested config changes"""
        config1 = {'config': {'param1': 'value1', 'param2': 'value2'}}
        config2 = {'config': {'param1': 'new_value1', 'param2': 'value2'}}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'config.param1: value1 -> new_value1' in changes

    def test_detect_changes_nested_config_limit(self):
        """Test detect_changes limits nested changes to 3"""
        config1 = {'config': {'p1': 'v1', 'p2': 'v2', 'p3': 'v3', 'p4': 'v4', 'p5': 'v5'}}
        config2 = {'config': {'p1': 'n1', 'p2': 'n2', 'p3': 'n3', 'p4': 'n4', 'p5': 'n5'}}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        nested_changes = [c for c in changes if c.startswith('config.')]
        assert len(nested_changes) == 3
        # Should have a "... and X more" message
        assert any('more nested config changes' in c for c in changes)

    def test_detect_changes_added_field(self):
        """Test detect_changes detects added field"""
        config1 = {}
        config2 = {'model': 'gpt-4'}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'model: None -> gpt-4' in changes

    def test_detect_changes_removed_field(self):
        """Test detect_changes detects removed field"""
        config1 = {'model': 'gpt-4'}
        config2 = {}

        changes = ConfigChangeDetector.detect_changes(config1, config2)
        assert 'model: gpt-4 -> None' in changes

    def test_get_affected_services_provider_change(self):
        """Test get_affected_services detects provider-related changes"""
        config1 = {'inference_provider': 'openai'}
        config2 = {'inference_provider': 'anthropic'}

        affected = ConfigChangeDetector.get_affected_services(config1, config2)
        assert affected['provider'] is True
        assert affected['adapter'] is True

    def test_get_affected_services_model_change(self):
        """Test get_affected_services detects model changes"""
        config1 = {'model': 'gpt-4'}
        config2 = {'model': 'gpt-4-turbo'}

        affected = ConfigChangeDetector.get_affected_services(config1, config2)
        assert affected['provider'] is True
        assert affected['adapter'] is True

    def test_get_affected_services_embedding_change(self):
        """Test get_affected_services detects embedding changes"""
        config1 = {'embedding_provider': 'openai'}
        config2 = {'embedding_provider': 'ollama'}

        affected = ConfigChangeDetector.get_affected_services(config1, config2)
        assert affected['embedding'] is True
        assert affected['adapter'] is True

    def test_get_affected_services_reranker_change(self):
        """Test get_affected_services detects reranker changes"""
        config1 = {'reranker_provider': 'cohere'}
        config2 = {'reranker_provider': 'flashrank'}

        affected = ConfigChangeDetector.get_affected_services(config1, config2)
        assert affected['reranker'] is True
        assert affected['adapter'] is True

    def test_get_affected_services_database_change(self):
        """Test get_affected_services detects database changes"""
        config1 = {'database': 'db1'}
        config2 = {'database': 'db2'}

        affected = ConfigChangeDetector.get_affected_services(config1, config2)
        assert affected['adapter'] is True
        assert affected['provider'] is False
        assert affected['embedding'] is False

    def test_get_affected_services_no_changes(self):
        """Test get_affected_services returns all False when no changes"""
        config1 = {'inference_provider': 'openai', 'model': 'gpt-4'}
        config2 = {'inference_provider': 'openai', 'model': 'gpt-4'}

        affected = ConfigChangeDetector.get_affected_services(config1, config2)
        assert affected['provider'] is False
        assert affected['embedding'] is False
        assert affected['reranker'] is False
        assert affected['adapter'] is False


class TestAdapterConfigManager:
    """Test AdapterConfigManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'adapters': [
                {
                    'name': 'qa-sql',
                    'enabled': True,
                    'inference_provider': 'openai',
                    'model': 'gpt-4'
                },
                {
                    'name': 'qa-file',
                    'enabled': True,
                    'inference_provider': 'anthropic',
                    'model': 'claude-3'
                },
                {
                    'name': 'disabled-adapter',
                    'enabled': False,
                    'inference_provider': 'ollama',
                    'model': 'llama3'
                }
            ]
        }
        self.config_manager = AdapterConfigManager(self.config)

    def test_init_loads_enabled_adapters(self):
        """Test initialization loads only enabled adapters"""
        assert 'qa-sql' in self.config_manager._adapter_configs
        assert 'qa-file' in self.config_manager._adapter_configs
        assert 'disabled-adapter' not in self.config_manager._adapter_configs

    def test_get_returns_config(self):
        """Test get returns adapter config"""
        config = self.config_manager.get('qa-sql')
        assert config is not None
        assert config['name'] == 'qa-sql'
        assert config['inference_provider'] == 'openai'

    def test_get_returns_none_for_nonexistent(self):
        """Test get returns None for nonexistent adapter"""
        config = self.config_manager.get('nonexistent')
        assert config is None

    def test_contains_true(self):
        """Test contains returns True for existing adapter"""
        assert self.config_manager.contains('qa-sql') is True

    def test_contains_false(self):
        """Test contains returns False for nonexistent adapter"""
        assert self.config_manager.contains('nonexistent') is False

    def test_put_adds_config(self):
        """Test put adds a new adapter config"""
        new_config = {'name': 'new-adapter', 'enabled': True}
        self.config_manager.put('new-adapter', new_config)

        assert self.config_manager.contains('new-adapter') is True
        assert self.config_manager.get('new-adapter') == new_config

    def test_remove_removes_config(self):
        """Test remove removes an adapter config"""
        removed = self.config_manager.remove('qa-sql')
        assert removed is not None
        assert self.config_manager.contains('qa-sql') is False

    def test_remove_returns_none_for_nonexistent(self):
        """Test remove returns None for nonexistent adapter"""
        removed = self.config_manager.remove('nonexistent')
        assert removed is None

    def test_get_available_adapters(self):
        """Test get_available_adapters returns list of adapter names"""
        adapters = self.config_manager.get_available_adapters()
        assert set(adapters) == {'qa-sql', 'qa-file'}

    def test_get_adapter_count(self):
        """Test get_adapter_count returns correct count"""
        assert self.config_manager.get_adapter_count() == 2

    def test_get_all_configs(self):
        """Test get_all_configs returns copy of all configs"""
        configs = self.config_manager.get_all_configs()
        assert 'qa-sql' in configs
        assert 'qa-file' in configs
        assert len(configs) == 2

        # Verify it's a copy
        configs['new'] = {}
        assert 'new' not in self.config_manager._adapter_configs

    def test_find_adapter_in_config_list_found(self):
        """Test find_adapter_in_config_list finds adapter"""
        config_list = [
            {'name': 'adapter1', 'enabled': True},
            {'name': 'adapter2', 'enabled': True},
            {'name': 'adapter3', 'enabled': False}
        ]

        result = self.config_manager.find_adapter_in_config_list('adapter2', config_list)
        assert result is not None
        assert result['name'] == 'adapter2'

    def test_find_adapter_in_config_list_not_found(self):
        """Test find_adapter_in_config_list returns None when not found"""
        config_list = [
            {'name': 'adapter1', 'enabled': True},
        ]

        result = self.config_manager.find_adapter_in_config_list('nonexistent', config_list)
        assert result is None

    def test_reload_from_config_added(self):
        """Test reload_from_config detects added adapters"""
        new_config = {
            'adapters': [
                {'name': 'qa-sql', 'enabled': True, 'model': 'gpt-4'},
                {'name': 'qa-file', 'enabled': True, 'model': 'claude-3'},
                {'name': 'new-adapter', 'enabled': True, 'model': 'new-model'}
            ]
        }

        result = self.config_manager.reload_from_config(new_config)
        assert 'new-adapter' in result['added']
        assert len(result['added']) == 1

    def test_reload_from_config_removed(self):
        """Test reload_from_config detects removed adapters"""
        new_config = {
            'adapters': [
                {'name': 'qa-sql', 'enabled': True, 'model': 'gpt-4'}
                # qa-file is removed
            ]
        }

        result = self.config_manager.reload_from_config(new_config)
        assert 'qa-file' in result['removed']
        assert len(result['removed']) == 1

    def test_reload_from_config_updated(self):
        """Test reload_from_config detects updated adapters"""
        new_config = {
            'adapters': [
                {'name': 'qa-sql', 'enabled': True, 'inference_provider': 'openai', 'model': 'gpt-4-turbo'},  # model changed
                {'name': 'qa-file', 'enabled': True, 'inference_provider': 'anthropic', 'model': 'claude-3'}  # unchanged
            ]
        }

        result = self.config_manager.reload_from_config(new_config)
        assert 'qa-sql' in result['updated']
        assert len(result['updated']) == 1

    def test_reload_from_config_unchanged(self):
        """Test reload_from_config tracks unchanged adapters"""
        new_config = {
            'adapters': [
                {'name': 'qa-sql', 'enabled': True, 'inference_provider': 'openai', 'model': 'gpt-4'},
                {'name': 'qa-file', 'enabled': True, 'inference_provider': 'anthropic', 'model': 'claude-3'}
            ]
        }

        result = self.config_manager.reload_from_config(new_config)
        assert len(result['unchanged']) == 2
        assert len(result['added']) == 0
        assert len(result['removed']) == 0
        assert len(result['updated']) == 0

    def test_reload_from_config_disabled_treated_as_removed(self):
        """Test reload_from_config treats disabled adapters as removed"""
        new_config = {
            'adapters': [
                {'name': 'qa-sql', 'enabled': False, 'inference_provider': 'openai', 'model': 'gpt-4'},  # disabled
                {'name': 'qa-file', 'enabled': True, 'inference_provider': 'anthropic', 'model': 'claude-3'}  # unchanged
            ]
        }

        result = self.config_manager.reload_from_config(new_config)
        assert 'qa-sql' in result['removed']
        assert 'qa-file' in result['unchanged']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
