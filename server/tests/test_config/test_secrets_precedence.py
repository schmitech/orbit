"""
Unit tests for the secrets-backend resolution precedence added to
_process_env_vars: secrets backend -> os.environ -> default -> warn+empty.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config.config_manager import _process_env_vars


class _StubSecretsBackend:
    """Minimal SecretsBackend stub for precedence testing."""

    def __init__(self, secrets=None, raise_for=None):
        self._secrets = secrets or {}
        self._raise_for = raise_for or set()

    def get_secret(self, name):
        if name in self._raise_for:
            raise RuntimeError(f"simulated lookup failure for {name}")
        return self._secrets.get(name)


class TestSecretsBackendPrecedence:
    def test_secret_wins_over_conflicting_env_var(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'from_env')
        backend = _StubSecretsBackend(secrets={'MY_VAR': 'from_vault'})
        result = _process_env_vars({'key': '${MY_VAR}'}, backend)
        assert result['key'] == 'from_vault'

    def test_falls_back_to_env_when_secret_absent(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'from_env')
        backend = _StubSecretsBackend(secrets={})
        result = _process_env_vars({'key': '${MY_VAR}'}, backend)
        assert result['key'] == 'from_env'

    def test_falls_back_to_default_when_absent_from_both(self):
        backend = _StubSecretsBackend(secrets={})
        result = _process_env_vars({'key': '${DEFINITELY_ABSENT_XYZ:-fallback}'}, backend)
        assert result['key'] == 'fallback'

    def test_absent_from_both_no_default_returns_empty(self):
        backend = _StubSecretsBackend(secrets={})
        result = _process_env_vars({'key': '${DEFINITELY_ABSENT_XYZ}'}, backend)
        assert result['key'] == ''

    def test_backend_lookup_failure_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'from_env')
        backend = _StubSecretsBackend(raise_for={'MY_VAR'})
        result = _process_env_vars({'key': '${MY_VAR}'}, backend)
        assert result['key'] == 'from_env'

    def test_backend_lookup_failure_falls_back_to_default(self):
        backend = _StubSecretsBackend(raise_for={'MY_VAR'})
        result = _process_env_vars({'key': '${MY_VAR:-fallback}'}, backend)
        assert result['key'] == 'fallback'

    def test_no_backend_behaves_as_before(self, monkeypatch):
        monkeypatch.setenv('MY_VAR', 'from_env')
        result = _process_env_vars({'key': '${MY_VAR}'})
        assert result['key'] == 'from_env'
