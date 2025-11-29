"""
Audio service implementations.

Available providers:
    - OpenAIAudioService: OpenAI audio (Whisper STT, TTS-1)
    - GoogleAudioService: Google Cloud audio (Speech-to-Text, Text-to-Speech)
    - GeminiAudioService: Gemini audio (native multimodal STT/TTS)
    - AnthropicAudioService: Anthropic audio (placeholder - not yet supported)
    - OllamaAudioService: Ollama audio (local audio models)
    - CohereAudioService: Cohere audio (placeholder - not yet supported)
    - ElevenLabsAudioService: ElevenLabs audio (high-quality TTS)
    - WhisperAudioService: Direct Whisper integration (local, offline STT)
    - VLLMAudioService: vLLM audio (Orpheus TTS, local serving)
    - CoquiAudioService: Coqui TTS (local, open-source TTS)
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('openai_audio_service', 'OpenAIAudioService'),
    ('google_audio_service', 'GoogleAudioService'),
    ('gemini_audio_service', 'GeminiAudioService'),
    ('anthropic_audio_service', 'AnthropicAudioService'),
    ('ollama_audio_service', 'OllamaAudioService'),
    ('cohere_audio_service', 'CohereAudioService'),
    ('elevenlabs_audio_service', 'ElevenLabsAudioService'),
    ('whisper_audio_service', 'WhisperAudioService'),
    ('vllm_audio_service', 'VLLMAudioService'),
    ('coqui_audio_service', 'CoquiAudioService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.audio.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
