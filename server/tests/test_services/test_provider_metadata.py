"""
Provider Metadata Consolidation Tests
======================================

Table-driven regression guard for the Phase 3 consolidation
(docs/roadmap/complete/chat-history-service-followups.md): asserts every provider
previously listed in any of the four dicts this module replaces
(ChatHistoryService._CONTEXT_WINDOW_PARAM_NAMES, its inline
default_context_windows dict, ProviderCacheManager._CONTEXT_WINDOW_ALIASES,
and ._MAX_TOKENS_ALIASES) resolves to the identical values through the new
shared lookup, and that both consumers still produce the same behavior they
did before the consolidation.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.provider_metadata import get_provider_context_window_info
from services.chat_history_service import ChatHistoryService
from services.cache.provider_cache_manager import ProviderCacheManager

# The exact values from the four dicts before consolidation.
EXPECTED_CONTEXT_WINDOW_PARAMS = {
    'ollama': 'num_ctx',
    'ollama_cloud': 'num_ctx',
    'ollama_remote': 'num_ctx',
    'llama_cpp': 'n_ctx',
    'bitnet': 'n_ctx',
    'vllm': 'max_model_len',
    'tensorrt': 'max_model_len',
    'huggingface': 'max_length',
}

EXPECTED_MAX_TOKENS_PARAMS = {
    'ollama': 'num_predict',
    'ollama_cloud': 'num_predict',
    'ollama_remote': 'num_predict',
}

EXPECTED_DEFAULT_CONTEXT_WINDOWS = {
    'ollama': 8192,
    'ollama_cloud': 32768,
    'ollama_remote': 8192,
    'llama_cpp': 4096,
    'openai': 128000,
    'anthropic': 200000,
    'gemini': 1000000,
    'groq': 131072,
    'deepseek': 65536,
    'together': 32768,
    'xai': 131072,
    'vllm': 8192,
    'tensorrt': 4096,
    'shimmy': 65536,
    'azure': 128000,
    'vertex': 1000000,
    'aws': 200000,
    'huggingface': 2048,
    'mistral': 32768,
    'openrouter': 131072,
    'cohere': 288000,
    'watson': 8192,
    'perplexity': 32768,
    'fireworks': 4096,
    'replicate': 4096,
    'nvidia': 8192,
    'bitnet': 2048,
    'transformers': 4096,
    'zai': 128000,
}


@pytest.mark.parametrize("provider,expected_param", EXPECTED_CONTEXT_WINDOW_PARAMS.items())
def test_context_window_param_matches_old_alias_dicts(provider, expected_param):
  info = get_provider_context_window_info(provider)
  assert info.context_window_param == expected_param


@pytest.mark.parametrize("provider,expected_param", EXPECTED_MAX_TOKENS_PARAMS.items())
def test_max_tokens_param_matches_old_alias_dict(provider, expected_param):
  info = get_provider_context_window_info(provider)
  assert info.max_tokens_param == expected_param


@pytest.mark.parametrize("provider,expected_default", EXPECTED_DEFAULT_CONTEXT_WINDOWS.items())
def test_default_context_window_matches_old_dict(provider, expected_default):
  info = get_provider_context_window_info(provider)
  assert info.default_context_window == expected_default


def test_providers_without_a_native_alias_get_the_generic_key():
  """Every cloud provider not listed in the old alias dicts must resolve to
  the generic 'context_window'/'max_tokens' key names, matching the implicit
  fallback both prior consumers had (no alias found -> use the generic key)."""
  for provider in EXPECTED_DEFAULT_CONTEXT_WINDOWS:
    if provider in EXPECTED_CONTEXT_WINDOW_PARAMS:
      continue
    info = get_provider_context_window_info(provider)
    assert info.context_window_param == 'context_window'
    assert info.max_tokens_param == 'max_tokens'


def test_unknown_provider_gets_generic_defaults():
  info = get_provider_context_window_info("some-provider-nobody-configured")
  assert info.context_window_param == 'context_window'
  assert info.max_tokens_param == 'max_tokens'
  assert info.default_context_window == 4096


def test_chat_history_service_default_context_window_uses_shared_lookup():
  """ChatHistoryService._get_context_window_size must fall back to the same
  provider-specific default it did before Phase 3, sourced from the shared
  module rather than a local dict."""
  service = ChatHistoryService(
    {'general': {'inference_provider': 'openai'}, 'inference': {}},
    database_service=MagicMock(),
    thread_dataset_service=MagicMock(),
  )
  assert service._get_context_window_size('anthropic', {}) == 200000
  assert service._get_context_window_size('ollama', {}) == 8192
  # An explicit native-param value still wins over the default
  assert service._get_context_window_size('ollama', {'num_ctx': 16384}) == 16384


def test_chat_history_service_writes_native_key_for_adapter_override():
  """An adapter-level context_window override must still be written under
  the provider's native config key (e.g. Ollama's num_ctx), not just the
  generic 'context_window' key, so the actual LLM call sees it too."""
  adapter_manager = MagicMock()
  adapter_manager.get_adapter_config.return_value = {
    'inference_provider': 'ollama',
    'context_window': 4096,
  }
  service = ChatHistoryService(
    {'general': {'inference_provider': 'openai'}, 'inference': {'ollama': {}}},
    database_service=MagicMock(),
    thread_dataset_service=MagicMock(),
    adapter_manager=adapter_manager,
  )

  budget = service._get_token_budget_for_adapter('ollama-adapter')

  # 4096 context - (1024 default max_tokens + 1200 default overhead) = 1872
  assert budget == 1872


def test_provider_cache_manager_writes_native_alias_for_ollama():
  """ProviderCacheManager must still write both the generic and native keys
  for a provider with an alias (Ollama's num_ctx/num_predict)."""
  cache_manager = ProviderCacheManager({'inference': {}}, thread_pool=None)
  config_for_provider = {'inference': {}}

  cache_manager._apply_param_overrides(
    config_for_provider, 'ollama', {'context_window': 16384, 'max_tokens': 2048}
  )

  ollama_config = config_for_provider['inference']['ollama']
  assert ollama_config['context_window'] == 16384
  assert ollama_config['num_ctx'] == 16384
  assert ollama_config['max_tokens'] == 2048
  assert ollama_config['num_predict'] == 2048


def test_provider_cache_manager_skips_alias_for_providers_without_one():
  """A provider with no native alias (e.g. openai) must not get a spurious
  duplicate key written under its own generic key name."""
  cache_manager = ProviderCacheManager({'inference': {}}, thread_pool=None)
  config_for_provider = {'inference': {}}

  cache_manager._apply_param_overrides(
    config_for_provider, 'openai', {'context_window': 64000, 'max_tokens': 4096}
  )

  openai_config = config_for_provider['inference']['openai']
  assert openai_config == {'context_window': 64000, 'max_tokens': 4096}
