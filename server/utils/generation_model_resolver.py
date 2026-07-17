"""
Resolve the provider/model actually responsible for producing a response on
image/video/audio generation adapters.

These adapters (type: image_generation/video_generation/audio_generation) don't
run a text LLM inference call — the response comes from an image, video, or TTS
provider configured via image_provider/video_provider/tts_provider (falling back
to the global default in config/image.yaml, config/video.yaml, or config/tts.yaml
when the adapter doesn't override it). Adapter-info and model-discovery endpoints
must resolve the provider/model from there instead of the adapter's (usually
absent) 'model'/'inference_provider' fields.
"""

import os
from typing import Any, Dict, Optional, Tuple

# Reported for the 'supertonic' TTS provider when it has no local model_dir configured
# (auto-download mode) — mirrors SupertonicAudioService's own default.
_SUPERTONIC_DEFAULT_MODEL_NAME = "supertonic"

_PROVIDER_FIELD_BY_TYPE = {
    'image_generation': 'image_provider',
    'video_generation': 'video_provider',
    'audio_generation': 'tts_provider',
}


def resolve_generation_provider_and_model(
    adapter_config: Dict[str, Any], config: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str]]:
    """Return (provider, model) for image/video/audio adapters, or (None, None) if not applicable."""
    adapter_type = adapter_config.get('type')
    if adapter_type not in _PROVIDER_FIELD_BY_TYPE:
        return None, None

    provider_field = _PROVIDER_FIELD_BY_TYPE[adapter_type]

    if adapter_type == 'image_generation':
        provider = adapter_config.get(provider_field) or config.get('image', {}).get('provider')
        model = (config.get('image_generation', {}) or {}).get(provider, {}).get('model')
        return provider, model

    if adapter_type == 'video_generation':
        provider = adapter_config.get(provider_field) or config.get('video', {}).get('provider')
        model = (config.get('video_generation', {}) or {}).get(provider, {}).get('model')
        return provider, model

    # audio_generation (TTS)
    provider = adapter_config.get(provider_field) or config.get('tts', {}).get('provider')
    provider_cfg = (config.get('tts_providers', {}) or {}).get(provider, {}) or {}
    model = provider_cfg.get('tts_model') or provider_cfg.get('model')

    if not model and provider == 'supertonic':
        # Supertonic has no model-name setting — it identifies the model by the local
        # directory it was downloaded to (mirrors SupertonicAudioService.__init__).
        model_dir = provider_cfg.get('model_dir')
        model = (
            os.path.basename(str(model_dir).rstrip('/\\')) if model_dir else _SUPERTONIC_DEFAULT_MODEL_NAME
        ) or _SUPERTONIC_DEFAULT_MODEL_NAME

    return provider, model


def resolve_generation_model(adapter_config: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
    """Return the real generation model for image/video/audio adapters, or None if not applicable."""
    _, model = resolve_generation_provider_and_model(adapter_config, config)
    return model
