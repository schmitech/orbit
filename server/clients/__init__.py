"""
Client modules for external services
"""

from .qa_ollama_client import QAOllamaClient
from .base_ollama_client import BaseOllamaClient

__all__ = ['QAOllamaClient', 'BaseOllamaClient']