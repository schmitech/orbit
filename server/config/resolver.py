"""
Configuration resolver for handling provider configurations and ensuring backward compatibility.

This module handles the resolution of all provider configurations in the system,
including inference, embedding, datasource, and reranker providers.
"""

import logging
from typing import Dict, Any
from config.config_manager import _is_true_value


class ConfigResolver:
    """
    Handles resolution of provider configurations and ensures backward compatibility.
    
    This class is responsible for:
    - Resolving provider configurations for all components
    - Handling provider inheritance and overrides
    - Managing component-specific settings
    - Ensuring backward compatibility
    - Model resolution for components
    """
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger = None):
        """
        Initialize the ConfigResolver.
        
        Args:
            config: The application configuration dictionary
            logger: Logger instance for logging resolution details
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
    
    def resolve_all_providers(self) -> None:
        """
        Resolve all provider configurations and ensure backward compatibility.
        
        This method handles the resolution of all provider configurations in the system,
        including:
        - Inference provider (LLM)
        - Embedding provider
        - Datasource provider
        - Safety provider
        - Reranker provider
        
        The resolution process:
        1. Checks for inference-only mode
        2. Resolves each provider configuration
        3. Updates component-specific settings
        4. Handles backward compatibility
        
        The method supports:
        - Provider inheritance
        - Component-specific overrides
        - Model resolution
        - Backward compatibility mapping
        
        Note:
            In inference-only mode, only the inference provider is resolved.
            Other providers are skipped to minimize resource usage.
        """
        # Check if inference_only is enabled
        inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
        
        # Get selected providers
        inference_provider = self.config['general'].get('inference_provider', 'ollama')
        safety_provider = self._resolve_component_provider('safety')
        safety_model = self._resolve_component_model('safety', safety_provider)
        if 'safety' in self.config:
                self.config['safety']['resolved_provider'] = safety_provider
                self.config['safety']['resolved_model'] = safety_model
        
        # Only resolve embedding and datasource providers if not in inference_only mode
        if not inference_only:
            datasource_provider = self.config['general'].get('datasource_provider', 'chroma')
            embedding_provider = self.config['embedding'].get('provider', 'ollama')
            
            # Resolve providers for reranker component
            reranker_provider = self._resolve_component_provider('reranker')
            
            # Resolve models for reranker
            reranker_model = self._resolve_component_model('reranker', reranker_provider)
            
            # Update reranker configuration with resolved values
            if 'reranker' in self.config:
                self.config['reranker']['resolved_provider'] = reranker_provider
                self.config['reranker']['resolved_model'] = reranker_model
            
            # Handle mongodb settings for backward compatibility
            if 'internal_services' in self.config and 'mongodb' in self.config['internal_services']:
                self.config['mongodb'] = self.config['internal_services']['mongodb']
            
            # Handle elasticsearch settings for backward compatibility
            if 'internal_services' in self.config and 'elasticsearch' in self.config['internal_services']:
                self.config['elasticsearch'] = self.config['internal_services']['elasticsearch']
            
            self.logger.info(f"Using datasource provider: {datasource_provider}")
            self.logger.info(f"Using embedding provider: {embedding_provider}")
            self.logger.info(f"Using safety provider: {safety_provider}")
            self.logger.info(f"Using reranker provider: {reranker_provider}")

        else:
            # In inference_only mode, only log the inference provider
            self.logger.info(f"Using inference provider: {inference_provider}")
    
    def _resolve_component_provider(self, component_name: str) -> str:
        """
        Resolve the provider for a specific component (safety or reranker).
        This implements the inheritance with override capability.
        
        Args:
            component_name: The name of the component ('safety' or 'reranker')
            
        Returns:
            The provider name to use for this component
        """
        # Get the main inference provider from general settings
        main_provider = self.config['general'].get('inference_provider', 'ollama')
        
        # Check if there's a component-specific override
        component_config = self.config.get(component_name, {})
        
        # For safety component, check for 'moderator'
        if component_name == 'safety':
            moderator = component_config.get('moderator')
            if moderator:
                # If a specific moderator is configured, use it
                self.logger.info(f"{component_name.capitalize()} uses configured moderator: {moderator}")
                return moderator
            else:
                # If no moderator specified, fall back to main provider
                self.logger.info(f"{component_name.capitalize()} falls back to main provider: {main_provider}")
                return main_provider

        # For reranker component, check for provider_override
        elif component_name == 'reranker':
            provider_override = component_config.get('provider_override')
            if provider_override and provider_override in self.config.get('inference', {}):
                self.logger.info(f"{component_name.capitalize()} uses custom provider: {provider_override}")
                return provider_override
            else:
                # If no override found, inherit from main provider
                self.logger.info(f"{component_name.capitalize()} inherits provider from general: {main_provider}")
                return main_provider
        
        # For any other component, use the default inheritance logic
        else:
            provider_override = component_config.get('provider_override')
            if provider_override and provider_override in self.config.get('inference', {}):
                self.logger.info(f"{component_name.capitalize()} uses custom provider: {provider_override}")
                return provider_override
            else:
                self.logger.info(f"{component_name.capitalize()} inherits provider from general: {main_provider}")
                return main_provider

    def _resolve_component_model(self, component_name: str, provider: str) -> str:
        """
        Resolve the model for a specific component (reranker).
        Handles model specification and suffix addition.
        
        Args:
            component_name: The name of the component ('reranker')
            provider: The provider name for this component
            
        Returns:
            The model name to use for this component
        """
        component_config = self.config.get(component_name, {})
        
        # Get the base model from the provider configuration
        provider_model = self.config['inference'].get(provider, {}).get('model', '')
        
        # Check if the component has its own model specified
        component_model = component_config.get('model')
        
        # Check if there's a model suffix to add
        model_suffix = component_config.get('model_suffix')
        
        # Determine the final model name
        if component_model:
            # Component has its own model specification
            model = component_model
        else:
            # Inherit from provider's model
            model = provider_model
        
        # Add suffix if specified
        if model_suffix and model:
            model = f"{model}{model_suffix}"
        
        self.logger.info(f"{component_name.capitalize()} using model: {model}")
        return model

    def resolve_datasource_embedding_provider(self, datasource_name: str) -> str:
        """
        Resolve embedding provider for a specific datasource.
        
        This method implements a provider resolution system that supports:
        - Inheritance from main embedding provider
        - Datasource-specific overrides
        - Fallback to default provider
        
        The resolution process:
        1. Gets the main embedding provider from config
        2. Checks for datasource-specific override
        3. Validates the provider exists in config
        4. Returns the appropriate provider name
        
        Args:
            datasource_name: The name of the datasource ('chroma', 'milvus', etc.)
            
        Returns:
            The embedding provider name to use for this datasource
            
        Note:
            If the specified provider override is not found in the config,
            the method falls back to the main provider.
        """
        # Get the main embedding provider from embedding settings
        main_provider = self.config['embedding'].get('provider', 'ollama')
        
        # Check if there's a provider override for this datasource
        datasource_config = self.config.get('datasources', {}).get(datasource_name, {})
        provider_override = datasource_config.get('embedding_provider')
        
        # If there's a valid override, use it; otherwise inherit from main provider
        if provider_override and provider_override in self.config.get('embeddings', {}):
            provider = provider_override
            self.logger.info(f"{datasource_name.capitalize()} uses custom embedding provider: {provider}")
        else:
            provider = main_provider
            self.logger.info(f"{datasource_name.capitalize()} inherits embedding provider from embedding config: {provider}")
        
        return provider