"""
Inference module for the pipeline architecture.

This module provides the new pipeline-based inference system
with clean provider implementations.
"""

from .pipeline_factory import PipelineFactory
from .pipeline import ProcessingContext, InferencePipeline

__all__ = ["PipelineFactory", "ProcessingContext", "InferencePipeline"]