#!/usr/bin/env python3
"""
Base RAG System - Reusable foundation for domain-specific RAG implementations
This provides the core functionality that can be extended for any domain.
"""

import yaml
import chromadb
from chromadb.config import Settings
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from abc import ABC, abstractmethod
from dotenv import load_dotenv, find_dotenv
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    def generate_response(self, prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
        """Generate response using the inference model"""
        pass


class BaseDatabaseClient(ABC):
    """Abstract base class for database clients"""
    
    @abstractmethod
    def execute_query(self, sql: str, params: Dict[str, Any] = None) -> Tuple[List[Dict], Optional[str]]:
        """Execute SQL query and return results with error message if any"""
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
                         error: Optional[str] = None) -> str:
        """Generate natural language response"""
        pass


class BaseRAGSystem:
    """Base RAG system that can be extended for any domain-specific implementation"""
    
    def __init__(self, 
                 chroma_persist_directory: str = "./chroma_db",
                 embedding_client: BaseEmbeddingClient = None,
                 inference_client: BaseInferenceClient = None,
                 db_client: BaseDatabaseClient = None,
                 parameter_extractor: BaseParameterExtractor = None,
                 response_generator: BaseResponseGenerator = None):
        """
        Initialize the base RAG system
        
        Args:
            chroma_persist_directory: Directory for ChromaDB persistence
            embedding_client: Client for generating embeddings
            inference_client: Client for generating responses
            db_client: Client for database operations
            parameter_extractor: Extractor for query parameters
            response_generator: Generator for natural language responses
        """
        self.chroma_persist_directory = chroma_persist_directory
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize clients
        self.embedding_client = embedding_client
        self.inference_client = inference_client
        self.db_client = db_client
        self.parameter_extractor = parameter_extractor
        self.response_generator = response_generator
        
        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="query_templates",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Track conversation context
        self.conversation_history = []
    
    def load_templates_from_yaml(self, yaml_file: str) -> List[Dict]:
        """Load query templates from YAML file"""
        try:
            with open(yaml_file, 'r') as file:
                data = yaml.safe_load(file)
                return data.get('templates', [])
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
            return []
    
    def create_embedding_text(self, template: Dict) -> str:
        """Create text for embedding from template - can be overridden by subclasses"""
        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(template.get('tags', []))
        ]
        
        # Add parameter names for better matching
        param_names = [p['name'].replace('_', ' ') for p in template.get('parameters', [])]
        parts.extend(param_names)
        
        return ' '.join(parts)
    
    def create_metadata(self, template: Dict) -> Dict:
        """Create ChromaDB-compatible metadata from template - can be overridden by subclasses"""
        return {
            'id': template.get('id', ''),
            'description': template.get('description', ''),
            'result_format': template.get('result_format', ''),
            'approved': str(template.get('approved', False)),
            'tags': ' '.join(template.get('tags', [])),
            'nl_examples': ' | '.join(template.get('nl_examples', [])),
            'sql_template': template.get('sql_template', ''),
            'parameters': json.dumps(template.get('parameters', []), ensure_ascii=False)
        }
    
    def clear_chromadb(self):
        """Clear all templates from ChromaDB"""
        try:
            # Delete the entire collection and recreate it
            collection_name = self.collection.name
            self.chroma_client.delete_collection(name=collection_name)
            logger.info(f"Deleted ChromaDB collection: {collection_name}")
            
            # Recreate the collection
            self.collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Recreated ChromaDB collection: {collection_name}")
        except Exception as e:
            logger.error(f"Error clearing ChromaDB: {e}")
            # Fallback: try to delete individual items
            try:
                results = self.collection.get()
                if results['ids']:
                    self.collection.delete(ids=results['ids'])
                    logger.info("Cleared ChromaDB collection (fallback method)")
            except Exception as e2:
                logger.error(f"Fallback clearing also failed: {e2}")
    
    def populate_chromadb(self, yaml_file: str, clear_first: bool = False):
        """Populate ChromaDB with query templates from YAML"""
        if clear_first:
            self.clear_chromadb()
        
        templates = self.load_templates_from_yaml(yaml_file)
        
        if not templates:
            logger.error("No templates found")
            return
        
        logger.info(f"Loading {len(templates)} templates into ChromaDB...")
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for template in templates:
            template_id = template['id']
            
            # Create embedding text
            embedding_text = self.create_embedding_text(template)
            
            # Get embedding
            embedding = self.embedding_client.get_embedding(embedding_text)
            
            if embedding:
                ids.append(template_id)
                embeddings.append(embedding)
                documents.append(embedding_text)
                metadatas.append(self.create_metadata(template))
        
        if ids:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Successfully loaded {len(ids)} templates")
        else:
            logger.error("No valid embeddings generated")
    
    def find_best_template(self, user_query: str, n_results: int = 5) -> List[Dict]:
        """Find the best matching template using semantic search"""
        try:
            # Get embedding for user query
            query_embedding = self.embedding_client.get_embedding(user_query)
            
            if not query_embedding:
                return []
            
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=['metadatas', 'distances']
            )
            
            templates = []
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                
                # Reconstruct template from metadata
                template = {
                    'id': metadata.get('id', ''),
                    'description': metadata.get('description', ''),
                    'result_format': metadata.get('result_format', ''),
                    'approved': metadata.get('approved', 'false').lower() == 'true',
                    'tags': metadata.get('tags', '').split(),
                    'nl_examples': metadata.get('nl_examples', '').split(' | '),
                    'sql_template': metadata.get('sql_template', ''),
                    'parameters': json.loads(metadata.get('parameters', '[]'))
                }
                
                templates.append({
                    'template': template,
                    'distance': distance,
                    'similarity': 1 - distance  # Convert distance to similarity
                })
            
            return templates
            
        except Exception as e:
            logger.error(f"Error finding template: {e}")
            return []
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]:
        """Rerank templates using additional heuristics - can be overridden by subclasses"""
        query_lower = user_query.lower()
        
        for template_info in templates:
            template = template_info['template']
            boost = 0.0
            
            # Boost for exact keyword matches
            for tag in template['tags']:
                if tag.lower() in query_lower:
                    boost += 0.1
            
            # Apply boost
            template_info['similarity'] = min(1.0, template_info['similarity'] + boost)
        
        # Re-sort by adjusted similarity
        return sorted(templates, key=lambda x: x['similarity'], reverse=True)
    
    def execute_template(self, template: Dict, parameters: Dict[str, Any]) -> Tuple[List[Dict], Optional[str]]:
        """Execute a query template with parameters"""
        try:
            sql_template = template['sql_template']
            results, error = self.db_client.execute_query(sql_template, parameters)
            return results, error
        except Exception as e:
            logger.error(f"Error executing template: {e}")
            return [], str(e)
    
    def suggest_alternatives(self, user_query: str, failed_template: Dict) -> str:
        """Suggest alternative ways to phrase the query"""
        prompt = f"""The user asked: "{user_query}"

This matched a template for "{failed_template['description']}" but couldn't extract all required parameters.

Based on the template examples:
{chr(10).join(failed_template['nl_examples'][:3])}

Suggest 2-3 alternative ways the user could rephrase their question to be clearer. Be brief and helpful.

Important: Give ONLY the suggestions, no meta-commentary."""
        
        return self.inference_client.generate_response(prompt)
    
    def process_query(self, user_query: str, conversation_context: bool = True) -> Dict[str, Any]:
        """Process a user query and return results"""
        logger.info(f"Processing query: {user_query}")
        
        # Add to conversation history if context is enabled
        if conversation_context:
            self.conversation_history.append({"role": "user", "content": user_query})
        
        # Step 1: Find best matching templates
        templates = self.find_best_template(user_query)
        
        if not templates:
            response = "I couldn't find a matching query pattern. Could you rephrase your question?"
            return {
                'success': False,
                'error': 'No matching query template found',
                'response': response
            }
        
        # Step 2: Rerank templates
        templates = self.rerank_templates(templates, user_query)
        
        # Step 3: Try templates in order until one works
        for template_info in templates:
            template = template_info['template']
            similarity = template_info['similarity']
            
            # Skip if similarity is too low
            if similarity < 0.3:
                continue
            
            logger.info(f"Trying template: {template['id']} (similarity: {similarity:.3f})")
            
            # Extract parameters
            parameters = self.parameter_extractor.extract_parameters(user_query, template)
            
            # Validate parameters
            valid, errors = self.parameter_extractor.validate_parameters(parameters, template)
            
            if not valid:
                logger.warning(f"Parameter validation failed: {errors}")
                
                # If this is the best match, provide helpful feedback
                if template_info == templates[0]:
                    suggestions = self.suggest_alternatives(user_query, template)
                    return {
                        'success': False,
                        'error': 'Missing required parameters',
                        'validation_errors': errors,
                        'response': suggestions,
                        'template_id': template['id'],
                        'similarity': similarity
                    }
                continue
            
            # Execute query
            results, error = self.execute_template(template, parameters)
            
            if error:
                logger.error(f"Query execution error: {error}")
                response = self.response_generator.generate_response(
                    user_query, results, template, error
                )
                return {
                    'success': False,
                    'error': error,
                    'response': response,
                    'template_id': template['id'],
                    'similarity': similarity
                }
            
            # Generate response
            response = self.response_generator.generate_response(
                user_query, results, template
            )
            
            # Add to conversation history
            if conversation_context:
                self.conversation_history.append({
                    "role": "assistant", 
                    "content": response,
                    "template_id": template['id'],
                    "result_count": len(results)
                })
            
            return {
                'success': True,
                'template_id': template['id'],
                'similarity': similarity,
                'parameters': parameters,
                'results': results,
                'response': response,
                'result_count': len(results)
            }
        
        # No template worked
        response = "I understood your question but couldn't process it properly. Could you try rephrasing it?"
        return {
            'success': False,
            'error': 'No viable template found',
            'response': response
        }
    
    def get_conversation_context(self, max_turns: int = 5) -> str:
        """Get recent conversation context for better understanding"""
        if not self.conversation_history:
            return ""
        
        recent = self.conversation_history[-max_turns:]
        context_parts = []
        
        for turn in recent:
            role = turn['role']
            content = turn['content']
            if role == 'assistant' and 'template_id' in turn:
                context_parts.append(f"Assistant: [Used {turn['template_id']}] {content}")
            else:
                context_parts.append(f"{role.capitalize()}: {content}")
        
        return "\n".join(context_parts)
    
    def clear_conversation(self):
        """Clear conversation history"""
        self.conversation_history = []
        logger.info("Conversation history cleared")
    
    def print_configuration(self):
        """Print the current configuration being used - can be overridden by subclasses"""
        print("🤖 Base RAG System Configuration:")
        print(f"  ChromaDB Path: {self.chroma_persist_directory}")
        
        # Test embedding dimensions
        if self.embedding_client:
            try:
                test_embedding = self.embedding_client.get_embedding("test")
                if test_embedding:
                    print(f"  Embedding Dimensions: {len(test_embedding)}")
                else:
                    print("  Embedding Dimensions: Failed to get test embedding")
            except Exception as e:
                print(f"  Embedding Dimensions: Error - {e}") 