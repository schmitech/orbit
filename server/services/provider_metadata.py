"""
Provider Metadata
==================

Shared, provider-keyed metadata about native parameter aliases and default
context-window sizes. This is the single source of truth for facts that used
to be duplicated across `ChatHistoryService` (context-window lookups for the
conversation-history token budget) and `ProviderCacheManager` (writing
adapter-level overrides under the key each provider's client actually reads).

Not a provider *service* registry (see `ai_services`/`inference.pipeline.providers`
for which client class to instantiate per provider) -- this module only holds
facts about a provider's native option names and defaults.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderContextWindowInfo:
    """
    Native parameter names and default context-window size for one provider.

    Attributes:
        context_window_param: The config key this provider actually reads for
            its context window. Most cloud providers use the generic
            'context_window'; local inference backends use their own native
            option name (e.g. Ollama's 'num_ctx').
        max_tokens_param: The config key this provider actually reads for its
            output-token limit. Most providers use the generic 'max_tokens';
            the Ollama family uses 'num_predict' instead.
        default_context_window: Conservative default context window size (in
            tokens), used only when neither the native nor the generic
            context-window config key is set for this provider.
    """
    context_window_param: str = "context_window"
    max_tokens_param: str = "max_tokens"
    default_context_window: int = 4096


_DEFAULT_INFO = ProviderContextWindowInfo()

# Populated from the four dicts this module replaces:
# ChatHistoryService._CONTEXT_WINDOW_PARAM_NAMES, the inline
# default_context_windows dict in ChatHistoryService._get_context_window_size,
# and ProviderCacheManager._CONTEXT_WINDOW_ALIASES/_MAX_TOKENS_ALIASES. Values
# are copied as-is (pure consolidation, not a re-tune) -- the two
# context-window-alias dicts already agreed exactly; where a provider only
# appeared in one of the four (e.g. every non-Ollama provider had no
# max-tokens alias), the default 'max_tokens'/'context_window' fields above
# reproduce that provider's prior "no alias" behavior.
_PROVIDER_CONTEXT_WINDOW_INFO: dict[str, ProviderContextWindowInfo] = {
    'ollama': ProviderContextWindowInfo(
        context_window_param='num_ctx', max_tokens_param='num_predict', default_context_window=8192
    ),
    'ollama_cloud': ProviderContextWindowInfo(
        context_window_param='num_ctx', max_tokens_param='num_predict', default_context_window=32768
    ),
    'ollama_remote': ProviderContextWindowInfo(
        context_window_param='num_ctx', max_tokens_param='num_predict', default_context_window=8192
    ),
    'llama_cpp': ProviderContextWindowInfo(context_window_param='n_ctx', default_context_window=4096),
    'bitnet': ProviderContextWindowInfo(context_window_param='n_ctx', default_context_window=2048),
    'vllm': ProviderContextWindowInfo(context_window_param='max_model_len', default_context_window=8192),
    'tensorrt': ProviderContextWindowInfo(context_window_param='max_model_len', default_context_window=4096),
    'huggingface': ProviderContextWindowInfo(context_window_param='max_length', default_context_window=2048),
    'openai': ProviderContextWindowInfo(default_context_window=128000),
    'anthropic': ProviderContextWindowInfo(default_context_window=200000),
    'gemini': ProviderContextWindowInfo(default_context_window=1000000),
    'groq': ProviderContextWindowInfo(default_context_window=131072),
    'deepseek': ProviderContextWindowInfo(default_context_window=65536),
    'together': ProviderContextWindowInfo(default_context_window=32768),
    'xai': ProviderContextWindowInfo(default_context_window=131072),
    'shimmy': ProviderContextWindowInfo(default_context_window=65536),
    'azure': ProviderContextWindowInfo(default_context_window=128000),
    'vertex': ProviderContextWindowInfo(default_context_window=1000000),
    'aws': ProviderContextWindowInfo(default_context_window=200000),
    'mistral': ProviderContextWindowInfo(default_context_window=32768),
    'openrouter': ProviderContextWindowInfo(default_context_window=131072),
    'cohere': ProviderContextWindowInfo(default_context_window=288000),
    'watson': ProviderContextWindowInfo(default_context_window=8192),
    'perplexity': ProviderContextWindowInfo(default_context_window=32768),
    'fireworks': ProviderContextWindowInfo(default_context_window=4096),
    'replicate': ProviderContextWindowInfo(default_context_window=4096),
    'nvidia': ProviderContextWindowInfo(default_context_window=8192),
    'transformers': ProviderContextWindowInfo(default_context_window=4096),
    'zai': ProviderContextWindowInfo(default_context_window=128000),
}


def get_provider_context_window_info(provider: str) -> ProviderContextWindowInfo:
    """
    Look up native parameter names and default context-window size for a
    provider.

    Args:
        provider: Inference provider name

    Returns:
        The provider's ProviderContextWindowInfo, or the generic default
        ('context_window'/'max_tokens' params, 4096-token default) for an
        unknown/unregistered provider -- matching the implicit fallback both
        prior consumers had.
    """
    return _PROVIDER_CONTEXT_WINDOW_INFO.get(provider, _DEFAULT_INFO)
