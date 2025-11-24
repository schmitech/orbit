"""
Pipeline Implementation

This module contains the core pipeline implementation for processing AI inference requests.
"""

import asyncio
import json
import logging
from typing import List, AsyncGenerator
from .base import ProcessingContext, PipelineStep
from .service_container import ServiceContainer
from .monitoring import PipelineMonitor
from .steps import SafetyFilterStep, LanguageDetectionStep, ContextRetrievalStep, DocumentRerankingStep, LLMInferenceStep, ResponseValidationStep

logger = logging.getLogger(__name__)

class InferencePipeline:
    """
    Pipeline for processing AI inference requests.
    
    This pipeline orchestrates a series of steps to process requests
    from input validation through response generation and validation.
    """
    
    def __init__(self, steps: List[PipelineStep], container: ServiceContainer):
        """
        Initialize the inference pipeline.
        
        Args:
            steps: List of pipeline steps to execute
            container: Service container for dependency injection
        """
        self.steps = steps
        self.container = container
        self.monitor = PipelineMonitor()
        self.logger = logging.getLogger(__name__)
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process a request through the pipeline.
        
        Args:
            context: The processing context containing request data
            
        Returns:
            Updated processing context with results
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.debug(f"Starting pipeline processing for message: {context.message[:50]}...")
            
            # Process through each step
            for step in self.steps:
                if not step.should_execute(context):
                    logger.debug(f"Skipping step {step.get_name()} - conditions not met")
                    continue
                
                step_start_time = asyncio.get_event_loop().time()
                
                try:
                    # Pre-process step
                    await step.pre_process(context)
                    
                    # Execute step
                    context = await step.process(context)
                    
                    # Post-process step
                    await step.post_process(context)
                    
                    # Record metrics
                    step_time = asyncio.get_event_loop().time() - step_start_time
                    self.monitor.record_step_metrics(step.get_name(), step_time, True)
                    
                    logger.debug(f"Completed step {step.get_name()} in {step_time:.3f}s")
                    
                    # Check for early termination
                    if context.is_blocked or context.has_error():
                        logger.warning(f"Pipeline stopped at step {step.get_name()}: {'blocked' if context.is_blocked else 'error'}")
                        break
                        
                except Exception as e:
                    step_time = asyncio.get_event_loop().time() - step_start_time
                    self.monitor.record_step_metrics(step.get_name(), step_time, False)
                    
                    logger.error(f"Error in step {step.get_name()}: {str(e)}")
                    context.error = str(e)
                    break
            
            # Record overall pipeline metrics
            total_time = asyncio.get_event_loop().time() - start_time
            self.monitor.record_pipeline_metrics(total_time, not context.has_error())
            
            logger.info(f"Pipeline processing completed in {total_time:.3f}s")
            return context
            
        except Exception as e:
            total_time = asyncio.get_event_loop().time() - start_time
            self.monitor.record_pipeline_metrics(total_time, False)
            
            logger.error(f"Pipeline processing failed: {str(e)}")
            context.error = str(e)
            return context
    
    async def process_stream(self, context: ProcessingContext) -> AsyncGenerator[str, None]:
        """
        Process a request through the pipeline with streaming response.
        
        Args:
            context: The processing context containing request data
            
        Yields:
            Streaming response chunks
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.debug(f"Starting streaming pipeline processing for message: {context.message[:50]}...")
            
            # Process through each step except the last one (LLM step)
            for step in self.steps[:-1]:
                if not step.should_execute(context):
                    logger.debug(f"Skipping step {step.get_name()} - conditions not met")
                    continue
                
                step_start_time = asyncio.get_event_loop().time()
                
                try:
                    # Pre-process step
                    await step.pre_process(context)
                    
                    # Execute step
                    context = await step.process(context)
                    
                    # Post-process step
                    await step.post_process(context)
                    
                    # Record metrics
                    step_time = asyncio.get_event_loop().time() - step_start_time
                    self.monitor.record_step_metrics(step.get_name(), step_time, True)
                    
                    logger.debug(f"Completed step {step.get_name()} in {step_time:.3f}s")
                    
                    # Check for early termination
                    if context.is_blocked or context.has_error():
                        logger.warning(f"Pipeline stopped at step {step.get_name()}: {'blocked' if context.is_blocked else 'error'}")
                        error_json = json.dumps({"error": context.error or "Pipeline blocked", "done": True})
                        yield error_json
                        return
                        
                except Exception as e:
                    step_time = asyncio.get_event_loop().time() - step_start_time
                    self.monitor.record_step_metrics(step.get_name(), step_time, False)
                    
                    logger.error(f"Error in step {step.get_name()}: {str(e)}")
                    error_json = json.dumps({"error": str(e), "done": True})
                    yield error_json
                    return
            
            # Find the LLM step for streaming
            llm_step = None
            for step in self.steps:
                if step.get_name() == 'LLMInferenceStep':
                    llm_step = step
                    break
            
            if llm_step is None:
                logger.error("No LLM step found in pipeline!")
                error_json = json.dumps({"error": "No LLM step configured", "done": True})
                yield error_json
                return
            
            logger.debug(f"DEBUG: LLM step found: {llm_step.get_name()}, should_execute={llm_step.should_execute(context)}, supports_streaming={llm_step.supports_streaming()}")
            
            if llm_step.should_execute(context) and llm_step.supports_streaming():
                # If response is already generated, just stream it
                if context.response:
                    yield json.dumps({"response": context.response, "done": False})
                    yield json.dumps({"done": True})
                    return
                step_start_time = asyncio.get_event_loop().time()
                
                try:
                    # Pre-process step
                    await llm_step.pre_process(context)

                    # Execute step with streaming
                    async for chunk in llm_step.process_stream(context):
                        # Format as JSON for consistency
                        chunk_json = json.dumps({"response": chunk, "done": False})
                        yield chunk_json
                        # Yield control to event loop to prevent buffering
                        await asyncio.sleep(0)

                    # Post-process step
                    await llm_step.post_process(context)
                    
                    # Send final done message
                    done_json = json.dumps({"done": True})
                    yield done_json
                    
                    # Record metrics
                    step_time = asyncio.get_event_loop().time() - step_start_time
                    self.monitor.record_step_metrics(llm_step.get_name(), step_time, True)
                    
                except Exception as e:
                    step_time = asyncio.get_event_loop().time() - step_start_time
                    self.monitor.record_step_metrics(llm_step.get_name(), step_time, False)
                    
                    logger.error(f"Error in streaming LLM step: {str(e)}")
                    error_json = json.dumps({"error": str(e), "done": True})
                    yield error_json
            else:
                # Fallback to non-streaming if LLM step doesn't support streaming
                try:
                    context = await llm_step.process(context)
                    response_json = json.dumps({"response": context.response, "done": True})
                    yield response_json
                except Exception as e:
                    logger.error(f"Error in non-streaming LLM step: {str(e)}")
                    error_json = json.dumps({"error": str(e), "done": True})
                    yield error_json
            
            # Record overall pipeline metrics
            total_time = asyncio.get_event_loop().time() - start_time
            self.monitor.record_pipeline_metrics(total_time, True)
            
            logger.info(f"Streaming pipeline processing completed in {total_time:.3f}s")
            
        except Exception as e:
            total_time = asyncio.get_event_loop().time() - start_time
            self.monitor.record_pipeline_metrics(total_time, False)
            
            logger.error(f"Streaming pipeline processing failed: {str(e)}")
            error_json = json.dumps({"error": str(e), "done": True})
            yield error_json
    
    def get_monitor(self) -> PipelineMonitor:
        """Get the pipeline monitor for metrics and health checks."""
        return self.monitor


class InferencePipelineBuilder:
    """Builder for creating inference pipelines."""
    
    @staticmethod
    def build_standard_pipeline(container: ServiceContainer) -> InferencePipeline:
        """
        Build a standard pipeline with all steps.
        
        Args:
            container: Service container with registered services
            
        Returns:
            Configured inference pipeline
        """
        config = container.get('config')
        
        steps = []
        
        # Add all steps by default (pipeline config section removed)
        # Safety filter only if safety/llm_guard services are available
        steps.append(SafetyFilterStep(container))

        # Language detection (if enabled)
        steps.append(LanguageDetectionStep(container))

        # Context retrieval (adapters will handle routing)
        steps.append(ContextRetrievalStep(container))

        # Document reranking (if enabled and documents retrieved)
        steps.append(DocumentRerankingStep(container))

        # LLM inference is always needed
        steps.append(LLMInferenceStep(container))
        
        # Response validation only if safety/llm_guard services are available
        steps.append(ResponseValidationStep(container))
        
        return InferencePipeline(steps, container)

    @staticmethod
    def build_custom_pipeline(container: ServiceContainer, step_classes: List[type]) -> InferencePipeline:
        """
        Build a custom pipeline with specified steps.
        
        Args:
            container: Service container with registered services
            step_classes: List of step classes to instantiate
            
        Returns:
            Configured custom pipeline
        """
        steps = [step_class(container) for step_class in step_classes]
        return InferencePipeline(steps, container) 