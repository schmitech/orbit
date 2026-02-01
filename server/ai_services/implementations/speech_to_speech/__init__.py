"""
Speech-to-Speech Service Implementations

This package contains implementations of full-duplex speech-to-speech services
that handle conversation dynamics (listening + speaking) simultaneously.

Available Implementations:
    - PersonaPlexService: Main PersonaPlex service (auto-selects embedded/proxy)
    - PersonaPlexProxyService: Connects to remote PersonaPlex server
    - PersonaPlexEmbeddedService: Runs PersonaPlex locally on GPU
"""

# Lazy imports to avoid loading heavy dependencies at startup
_implementations = [
    ('personaplex_service', 'PersonaPlexService'),
    ('personaplex_proxy', 'PersonaPlexProxyService'),
    ('personaplex_embedded', 'PersonaPlexEmbeddedService'),
]


def __getattr__(name):
    """Lazy import implementations."""
    for module_name, class_name in _implementations:
        if name == class_name:
            try:
                module = __import__(
                    f'ai_services.implementations.speech_to_speech.{module_name}',
                    fromlist=[class_name]
                )
                return getattr(module, class_name)
            except ImportError as e:
                raise ImportError(
                    f"Cannot import {class_name}: {e}. "
                    f"Ensure required dependencies are installed."
                )
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    'PersonaPlexService',
    'PersonaPlexProxyService',
    'PersonaPlexEmbeddedService',
]
