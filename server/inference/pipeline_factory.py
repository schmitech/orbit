"""
Pipeline Factory

This module provides a factory for creating and configuring inference pipelines
with clean, direct provider implementations.
"""

import logging
from typing import Dict, Any, Optional
from .pipeline.pipeline import InferencePipeline, InferencePipelineBuilder
from .pipeline.service_container import ServiceContainer
from .pipeline.providers import ProviderFactory

class PipelineFactory:
    """
    Factory for creating inference pipelines with clean services.
    
    This factory integrates the new pipeline architecture with clean
    provider implementations, avoiding legacy compatibility layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the pipeline factory.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def create_service_container(
        self,
        retriever=None,
        reranker_service=None,
        prompt_service=None,
        llm_guard_service=None,
        moderator_service=None,
        chat_history_service=None,
        logger_service=None
    ) -> ServiceContainer:
        """
        Create a service container with all required services.
        
        Args:
            retriever: Optional retriever service
            reranker_service: Optional reranker service
            prompt_service: Optional prompt service
            llm_guard_service: Optional LLM Guard service
            moderator_service: Optional moderator service
            chat_history_service: Optional chat history service
            logger_service: Optional logger service
            
        Returns:
            Configured service container
        """
        container = ServiceContainer()
        
        # Register configuration
        container.register_singleton('config', self.config)
        
        # Create and register clean LLM provider
        llm_provider = ProviderFactory.create_provider(self.config)
        container.register_singleton('llm_provider', llm_provider)
        
        # Register RAG services if available
        if retriever:
            container.register_singleton('retriever', retriever)
        
        if reranker_service:
            container.register_singleton('reranker_service', reranker_service)
        
        if prompt_service:
            container.register_singleton('prompt_service', prompt_service)
        
        # Register security services if available
        if llm_guard_service:
            container.register_singleton('llm_guard_service', llm_guard_service)
        
        if moderator_service:
            container.register_singleton('moderator_service', moderator_service)
        
        # Register other services if available
        if chat_history_service:
            container.register_singleton('chat_history_service', chat_history_service)
        
        if logger_service:
            container.register_singleton('logger_service', logger_service)
        
        self.logger.info(f"Created service container with {len(container.list_services())} services")
        return container
    
    async def initialize_provider(self, container: ServiceContainer) -> None:
        """
        Initialize the LLM provider in the service container.
        
        Args:
            container: The service container with the provider
        """
        llm_provider = container.get('llm_provider')
        if llm_provider:
            await llm_provider.initialize()
            self.logger.info("LLM provider initialized")
    
    def create_pipeline(
        self,
        container: ServiceContainer,
        pipeline_type: str = "auto"
    ) -> InferencePipeline:
        """
        Create an inference pipeline.
        
        Args:
            container: The service container
            pipeline_type: Type of pipeline to create ("auto", "standard", "inference_only")
            
        Returns:
            Configured inference pipeline
        """
        if pipeline_type == "auto":
            # Determine pipeline type based on configuration
            inference_only = self.config.get('general', {}).get('inference_only', False)
            pipeline_type = "inference_only" if inference_only else "standard"
        
        if pipeline_type == "standard":
            pipeline = InferencePipelineBuilder.build_standard_pipeline(container)
            self.logger.info("Created standard pipeline with RAG support")
        elif pipeline_type == "inference_only":
            pipeline = InferencePipelineBuilder.build_inference_only_pipeline(container)
            self.logger.info("Created inference-only pipeline")
        else:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}")
        
        return pipeline
    
    def create_pipeline_with_services(
        self,
        retriever=None,
        reranker_service=None,
        prompt_service=None,
        llm_guard_service=None,
        moderator_service=None,
        chat_history_service=None,
        logger_service=None,
        pipeline_type: str = "auto"
    ) -> InferencePipeline:
        """
        Create a complete pipeline with services.
        
        This is a convenience method that creates both the service container
        and pipeline in one call.
        
        Args:
            retriever: Optional retriever service
            reranker_service: Optional reranker service
            prompt_service: Optional prompt service
            llm_guard_service: Optional LLM Guard service
            moderator_service: Optional moderator service
            chat_history_service: Optional chat history service
            logger_service: Optional logger service
            pipeline_type: Type of pipeline to create
            
        Returns:
            Configured inference pipeline
        """
        container = self.create_service_container(
            retriever=retriever,
            reranker_service=reranker_service,
            prompt_service=prompt_service,
            llm_guard_service=llm_guard_service,
            moderator_service=moderator_service,
            chat_history_service=chat_history_service,
            logger_service=logger_service
        )
        
        return self.create_pipeline(container, pipeline_type) 