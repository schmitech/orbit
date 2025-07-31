#!/usr/bin/env python3
"""
Base Classes for RAG System
====================================

Abstract base classes that define the interfaces for the RAG system components.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class BaseEmbeddingClient(ABC):
    """Abstract base class for embedding clients"""
    
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text"""
        pass


class BaseInferenceClient(ABC):
    """Abstract base class for inference clients"""
    
    @abstractmethod
    def generate_response(self, prompt: str, system_prompt: Optional[str] = None, 
                         max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Generate response using the inference model"""
        pass


class BaseDatabaseClient(ABC):
    """Abstract base class for database clients"""
    
    @abstractmethod
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute SQL query and return results"""
        pass
    
    @abstractmethod
    def get_schema_info(self) -> Dict[str, List[str]]:
        """Get database schema information"""
        pass


class BaseParameterExtractor(ABC):
    """Abstract base class for parameter extraction"""
    
    def __init__(self, inference_client: BaseInferenceClient):
        self.inference_client = inference_client
    
    @abstractmethod
    def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """Extract parameters from user query based on template requirements"""
        pass
    
    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]:
        """Validate extracted parameters against template requirements"""
        pass


class BaseResponseGenerator(ABC):
    """Abstract base class for response generation"""
    
    def __init__(self, inference_client: BaseInferenceClient):
        self.inference_client = inference_client
    
    @abstractmethod
    def generate_response(self, user_query: str, results: List[Dict], template: Dict, 
                         error: Optional[str] = None, conversation_context: Optional[str] = None) -> str:
        """Generate natural language response"""
        pass


class BaseRAGSystem(ABC):
    """Abstract base class for RAG systems"""
    
    @abstractmethod
    def process_query(self, user_query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a user query and return results"""
        pass
    
    @abstractmethod
    def populate_chromadb_from_library(self, clear_first: bool = False) -> None:
        """Populate ChromaDB with templates from the library"""
        pass