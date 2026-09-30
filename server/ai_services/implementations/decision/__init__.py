"""
Decision model service implementations ("System One" / Jev-style models).

Available providers:
    - OllamaDecisionService: local decision models via Ollama's /v1/systemone
    - TypeSafeDecisionService: TypeSafe hosted API via the typesafe-sdk
"""

import logging

logger = logging.getLogger(__name__)

__all__ = []

_implementations = [
    ('ollama_decision_service', 'OllamaDecisionService'),
    ('typesafe_decision_service', 'TypeSafeDecisionService'),
]

for module_name, class_name in _implementations:
    try:
        module = __import__(f'ai_services.implementations.decision.{module_name}', fromlist=[class_name])
        globals()[class_name] = getattr(module, class_name)
        __all__.append(class_name)
    except (ImportError, AttributeError) as e:
        logger.debug(f"Skipping {class_name} - missing dependencies: {e}")
