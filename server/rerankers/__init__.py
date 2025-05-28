"""
Reranker service factory and provider management.
"""

import logging
from typing import Dict, Any, Optional
from .base import RerankerService
from .ollama import OllamaReranker

logger = logging.getLogger(__name__)

class RerankerFactory:
    """Factory class for creating reranker instances."""
    
    _providers = {
        'ollama': OllamaReranker,
        # Add other providers here as they are implemented
    }
    
    @classmethod
    def create(cls, config: Dict[str, Any]) -> Optional[RerankerService]:
        """
        Create a reranker instance based on configuration.
        
        Args:
            config: Application configuration dictionary
            
        Returns:
            RerankerService instance or None if disabled
        """
        reranker_config = config.get('reranker', {})
        if not reranker_config.get('enabled', False):
            return None
            
        # Get provider name
        provider_name = reranker_config.get('provider', 'ollama')
            
        # Get provider class
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            logger.error(f"Unsupported reranker provider: {provider_name}")
            return None
            
        # Get provider-specific config
        provider_config = config.get('rerankers', {}).get(provider_name, {})
        if not provider_config:
            logger.error(f"No configuration found for reranker provider: {provider_name}")
            return None
            
        # Add global reranker settings
        provider_config.update({
            'temperature': reranker_config.get('temperature', 0.0),
            'batch_size': reranker_config.get('batch_size', 5)
        })
        
        return provider_class(provider_config) 