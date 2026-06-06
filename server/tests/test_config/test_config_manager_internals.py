"""
Unit tests for config_manager.py internals:
_process_env_vars, _process_imports, _merge_configs, _mask_url,
_resolve_inference_preset, _validate_required_config.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config.config_manager import (
    clear_config_cache,
    load_config,
    reload_config,
    _mask_url,
    _merge_configs,
    _process_env_vars,
    _process_imports,
    _resolve_inference_preset,
    _validate_required_config,
    was_resolved_from_preset,
)


# ---------------------------------------------------------------------------
# _process_env_vars
# ---------------------------------------------------------------------------

class TestProcessEnvVars:
    def test_whole_value_substituted(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'hello')
        assert _process_env_vars({'key': '${MY_VAR}'})['key'] == 'hello'

    def test_default_used_when_var_absent(self):
        result = _process_env_vars({'key': '${DEFINITELY_ABSENT_XYZ:-fallback}'})
        assert result['key'] == 'fallback'

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'from_env')
        result = _process_env_vars({'key': '${MY_VAR:-default}'})
        assert result['key'] == 'from_env'

    def test_missing_required_var_returns_empty_string(self):
        result = _process_env_vars({'key': '${DEFINITELY_ABSENT_XYZ}'})
        assert result['key'] == ''

    def test_partial_string_substituted(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'world')
        result = _process_env_vars({'key': 'prefix-${MY_VAR}'})
        assert result['key'] == 'prefix-world'

    def test_multiple_tokens_substituted(self, monkeypatch):
        monkeypatch.setenv('HOST', 'localhost')
        monkeypatch.setenv('PORT', '8080')
        result = _process_env_vars({'url': 'http://${HOST}:${PORT}/api'})
        assert result['url'] == 'http://localhost:8080/api'

    def test_non_string_values_unchanged(self):
        result = _process_env_vars({'enabled': True, 'count': 42, 'ratio': 3.14})
        assert result['enabled'] is True
        assert result['count'] == 42
        assert result['ratio'] == 3.14

    def test_nested_dict_substituted(self, monkeypatch):
        monkeypatch.setenv('DB_PASS', 'secret')
        result = _process_env_vars({'db': {'password': '${DB_PASS}'}})
        assert result['db']['password'] == 'secret'

    def test_list_items_substituted(self, monkeypatch):
        monkeypatch.setenv('ITEM', 'value')
        result = _process_env_vars({'items': ['${ITEM}', 'literal']})
        assert result['items'][0] == 'value'
        assert result['items'][1] == 'literal'


# ---------------------------------------------------------------------------
# _merge_configs
# ---------------------------------------------------------------------------

class TestMergeConfigs:
    def test_main_takes_precedence(self):
        result = _merge_configs({'key': 'main'}, {'key': 'imported'})
        assert result['key'] == 'main'

    def test_imported_keys_added(self):
        result = _merge_configs({'a': 1}, {'b': 2})
        assert result == {'a': 1, 'b': 2}

    def test_nested_dicts_merged_recursively(self):
        result = _merge_configs({'s': {'a': 1}}, {'s': {'b': 2}})
        assert result['s'] == {'a': 1, 'b': 2}

    def test_nested_main_key_wins(self):
        result = _merge_configs({'s': {'k': 'main'}}, {'s': {'k': 'imported'}})
        assert result['s']['k'] == 'main'

    def test_lists_concatenated(self):
        result = _merge_configs({'items': [1, 2]}, {'items': [3, 4]})
        assert result['items'] == [1, 2, 3, 4]

    def test_empty_imported_returns_main_unchanged(self):
        assert _merge_configs({'a': 1}, {}) == {'a': 1}

    def test_empty_main_returns_imported(self):
        assert _merge_configs({}, {'b': 2}) == {'b': 2}


# ---------------------------------------------------------------------------
# _mask_url
# ---------------------------------------------------------------------------

class TestMaskUrl:
    def test_credentials_masked(self):
        url = 'https://user:password@host.example.com/path'
        result = _mask_url(url)
        assert 'password' not in result
        assert '[REDACTED]' in result
        assert 'host.example.com' in result

    def test_plain_url_unchanged(self):
        url = 'https://host.example.com/path'
        assert _mask_url(url) == url

    def test_api_key_query_param_masked(self):
        url = 'https://api.example.com/ep?api_key=secret123&format=json'
        result = _mask_url(url)
        assert 'secret123' not in result
        assert '[REDACTED]' in result
        assert 'format=json' in result

    def test_token_query_param_masked(self):
        url = 'https://api.example.com/ep?token=abc&other=1'
        result = _mask_url(url)
        assert 'abc' not in result
        assert 'other=1' in result

    def test_none_returns_none(self):
        assert _mask_url(None) is None

    def test_empty_string_returns_empty(self):
        assert _mask_url('') == ''


# ---------------------------------------------------------------------------
# _resolve_inference_preset
# ---------------------------------------------------------------------------

class TestResolveInferencePreset:
    def _config(self):
        return {
            'inference': {'ollama': {'enabled': True, 'use_preset': 'fast'}},
            'ollama_presets': {'fast': {'model': 'llama3:1b', 'num_gpu': 1}},
        }

    def test_model_resolved_from_preset(self):
        result = _resolve_inference_preset(self._config(), 'ollama', 'ollama_presets')
        assert result['inference']['ollama']['model'] == 'llama3:1b'

    def test_all_preset_keys_applied(self):
        result = _resolve_inference_preset(self._config(), 'ollama', 'ollama_presets')
        assert result['inference']['ollama']['num_gpu'] == 1

    def test_enabled_flag_preserved_true(self):
        config = self._config()
        config['inference']['ollama']['enabled'] = True
        result = _resolve_inference_preset(config, 'ollama', 'ollama_presets')
        assert result['inference']['ollama']['enabled'] is True

    def test_enabled_flag_preserved_false(self):
        config = self._config()
        config['inference']['ollama']['enabled'] = False
        result = _resolve_inference_preset(config, 'ollama', 'ollama_presets')
        assert result['inference']['ollama']['enabled'] is False

    def test_use_preset_removed_from_result(self):
        result = _resolve_inference_preset(self._config(), 'ollama', 'ollama_presets')
        assert 'use_preset' not in result['inference']['ollama']

    def test_preset_metadata_recorded_without_marker(self):
        result = _resolve_inference_preset(self._config(), 'ollama', 'ollama_presets')
        assert '_from_preset' not in result['inference']['ollama']
        assert was_resolved_from_preset('ollama') == 'fast'

    def test_missing_preset_returns_config_unchanged(self):
        config = self._config()
        config['inference']['ollama']['use_preset'] = 'nonexistent'
        result = _resolve_inference_preset(config, 'ollama', 'ollama_presets')
        assert result['inference']['ollama'].get('use_preset') == 'nonexistent'

    def test_no_use_preset_key_returns_unchanged(self):
        config = {'inference': {'ollama': {'enabled': True}}, 'ollama_presets': {}}
        original = config['inference']['ollama'].copy()
        result = _resolve_inference_preset(config, 'ollama', 'ollama_presets')
        assert result['inference']['ollama'] == original

    def test_llama_cpp_provider_resolved(self):
        config = {
            'inference': {'llama_cpp': {'enabled': True, 'use_preset': 'cpu-small'}},
            'llama_cpp_presets': {'cpu-small': {'model': './models/small.gguf', 'n_ctx': 2048}},
        }
        result = _resolve_inference_preset(config, 'llama_cpp', 'llama_cpp_presets')
        assert result['inference']['llama_cpp']['model'] == './models/small.gguf'
        assert result['inference']['llama_cpp']['n_ctx'] == 2048


# ---------------------------------------------------------------------------
# _validate_required_config
# ---------------------------------------------------------------------------

class TestValidateRequiredConfig:
    def test_valid_config_passes(self):
        _validate_required_config({'auth': {'default_admin_password': 'secure123'}})

    def test_empty_password_raises(self):
        with pytest.raises(RuntimeError, match='default_admin_password'):
            _validate_required_config({'auth': {'default_admin_password': ''}})

    def test_missing_auth_section_raises(self):
        with pytest.raises(RuntimeError, match='default_admin_password'):
            _validate_required_config({})

    def test_missing_password_key_raises(self):
        with pytest.raises(RuntimeError, match='default_admin_password'):
            _validate_required_config({'auth': {}})

    def test_cors_wildcard_with_credentials_raises(self):
        config = {
            'auth': {'default_admin_password': 'secure123'},
            'security': {
                'cors': {
                    'allow_credentials': True,
                    'allowed_origins': ['*'],
                }
            },
        }
        with pytest.raises(RuntimeError, match='allow_credentials'):
            _validate_required_config(config)

    def test_mongodb_backend_requires_password(self):
        config = {
            'auth': {'default_admin_password': 'secure123'},
            'internal_services': {
                'backend': {'type': 'mongodb'},
                'mongodb': {
                    'host': 'localhost',
                    'username': 'user',
                    'password': '',
                    'database': 'orbit',
                },
            },
        }
        with pytest.raises(RuntimeError, match='mongodb.password'):
            _validate_required_config(config)


# ---------------------------------------------------------------------------
# _process_imports
# ---------------------------------------------------------------------------

class TestProcessImports:
    def test_no_imports_returns_config_unchanged(self, tmp_path):
        config = {'key': 'value', 'section': {'nested': True}}
        result = _process_imports(config.copy(), str(tmp_path))
        assert result == config

    def test_single_import_string_merged(self, tmp_path):
        (tmp_path / 'extra.yaml').write_text('extra_key: extra_value\n')
        config = {'import': 'extra.yaml', 'main_key': 'main_value'}
        result = _process_imports(config, str(tmp_path))
        assert result['main_key'] == 'main_value'
        assert result['extra_key'] == 'extra_value'
        assert 'import' not in result

    def test_import_list_merged(self, tmp_path):
        (tmp_path / 'a.yaml').write_text('key_a: val_a\n')
        (tmp_path / 'b.yaml').write_text('key_b: val_b\n')
        config = {'import': ['a.yaml', 'b.yaml']}
        result = _process_imports(config, str(tmp_path))
        assert result['key_a'] == 'val_a'
        assert result['key_b'] == 'val_b'

    def test_main_key_wins_over_imported(self, tmp_path):
        (tmp_path / 'extra.yaml').write_text('key: from_import\n')
        config = {'import': 'extra.yaml', 'key': 'from_main'}
        result = _process_imports(config, str(tmp_path))
        assert result['key'] == 'from_main'

    def test_missing_import_file_skipped(self, tmp_path):
        config = {'import': 'nonexistent.yaml', 'key': 'value'}
        result = _process_imports(config, str(tmp_path))
        assert result['key'] == 'value'
        assert 'import' not in result

    def test_path_traversal_blocked(self, tmp_path):
        config = {'import': '../../../etc/passwd', 'key': 'safe'}
        result = _process_imports(config, str(tmp_path))
        assert result['key'] == 'safe'
        assert 'root' not in result


# ---------------------------------------------------------------------------
# load_config/reload_config
# ---------------------------------------------------------------------------

class TestLoadConfigCaching:
    def test_load_config_singleton_ignores_argument_keying(self, tmp_path, monkeypatch):
        monkeypatch.setenv('ADMIN_PASS', 'secure123')
        first_path = tmp_path / 'first.yaml'
        second_path = tmp_path / 'second.yaml'
        first_path.write_text('auth:\n  default_admin_password: ${ADMIN_PASS}\nvalue: first\n')
        second_path.write_text('auth:\n  default_admin_password: ${ADMIN_PASS}\nvalue: second\n')

        clear_config_cache()
        try:
            first = load_config(str(first_path))
            second = load_config(str(second_path))

            assert first is second
            assert second['value'] == 'first'

            reloaded = reload_config(str(second_path))
            assert reloaded is load_config()
            assert reloaded['value'] == 'second'
        finally:
            clear_config_cache()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
