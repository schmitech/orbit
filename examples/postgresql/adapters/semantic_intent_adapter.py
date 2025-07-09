"""
Semantic Intent Adapter for ORBIT
=================================

This adapter integrates the semantic RAG intent system with the existing ORBIT retriever architecture.
It uses ChromaDB for template storage, Ollama for embeddings and inference, and provides natural
language query understanding for SQL databases.
"""

import json
import logging
import re
import yaml
from typing import Dict, Any, List, Optional
from decimal import Decimal

import chromadb
from chromadb.config import Settings
import requests

from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

logger = logging.getLogger(__name__)

class OllamaClient:
    """Client for Ollama API interactions"""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        
    def get_embedding(self, text: str, model: str = "nomic-embed-text") -> List[float]:
        """Get embedding for text using Ollama"""
        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return []
    
    def generate_response(self, prompt: str, model: str = "gemma3:1b", system_prompt: str = "") -> str:
        """Generate response using Ollama"""
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm sorry, I encountered an error processing your request."

class SemanticIntentAdapter(DocumentAdapter):
    """
    Adapter that uses semantic search to map user queries to pre-approved SQL templates
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        """Initialize the semantic intent adapter"""
        super().__init__(**kwargs)
        
        self.config = config
        self.verbose = config.get('verbose', False)
        
        # Initialize clients
        self.ollama_client = OllamaClient(config.get('inference_url', 'http://localhost:11434'))
        self.embedding_model = config.get('embedding_model', 'nomic-embed-text')
        self.inference_model = config.get('inference_model', 'gemma3:1b')
        
        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=config.get('chroma_persist_directory', './chroma_db'),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create templates collection
        self.templates_collection = self.chroma_client.get_or_create_collection(
            name=config.get('templates_collection', 'query_templates'),
            metadata={"hnsw:space": "cosine"}
        )
        
        # Configuration
        self.confidence_threshold = config.get('confidence_threshold', 0.7)
        self.templates_loaded = False
        
        logger.info("SemanticIntentAdapter initialized")
    
    def populate_templates(self, templates_file: str):
        """Load query templates from YAML file into ChromaDB"""
        try:
            with open(templates_file, 'r') as file:
                data = yaml.safe_load(file)
                templates = data.get('templates', [])
            
            if not templates:
                logger.warning("No templates found in file")
                return
            
            logger.info(f"Loading {len(templates)} templates into ChromaDB...")
            
            ids = []
            embeddings = []
            documents = []
            metadatas = []
            
            for template in templates:
                template_id = template['id']
                
                # Create embedding text from template
                embedding_text = self._create_embedding_text(template)
                
                # Get embedding
                embedding = self.ollama_client.get_embedding(embedding_text, self.embedding_model)
                
                if embedding:
                    ids.append(template_id)
                    embeddings.append(embedding)
                    documents.append(embedding_text)
                    metadatas.append(self._create_metadata(template))
            
            if ids:
                self.templates_collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"Successfully loaded {len(ids)} templates")
                self.templates_loaded = True
            else:
                logger.error("No valid embeddings generated")
                
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
    
    def _create_embedding_text(self, template: Dict) -> str:
        """Create text for embedding from template"""
        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(template.get('tags', []))
        ]
        return ' '.join(parts)
    
    def _create_metadata(self, template: Dict) -> Dict:
        """Create ChromaDB-compatible metadata from template"""
        return {
            'id': template.get('id', ''),
            'description': template.get('description', ''),
            'result_format': template.get('result_format', ''),
            'approved': str(template.get('approved', False)),
            'tags': ' '.join(template.get('tags', [])),
            'nl_examples': ' | '.join(template.get('nl_examples', [])),
            'sql_template': template.get('sql_template', ''),
            'parameters': json.dumps(template.get('parameters', []))
        }
    
    def find_best_template(self, user_query: str, n_results: int = 3) -> Optional[Dict]:
        """Find the best matching template using semantic search"""
        try:
            # Get embedding for user query
            query_embedding = self.ollama_client.get_embedding(user_query, self.embedding_model)
            
            if not query_embedding:
                return None
            
            # Search in ChromaDB
            results = self.templates_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=['metadatas', 'distances']
            )
            
            if not results['ids'][0]:
                return None
            
            # Get best match
            metadata = results['metadatas'][0][0]
            distance = results['distances'][0][0]
            similarity = 1 - distance
            
            # Check confidence threshold
            if similarity < self.confidence_threshold:
                logger.warning(f"Best template similarity {similarity:.3f} below threshold {self.confidence_threshold}")
                return None
            
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
            
            return {
                'template': template,
                'similarity': similarity,
                'distance': distance
            }
            
        except Exception as e:
            logger.error(f"Error finding template: {e}")
            return None
    
    def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """Extract parameters from user query using LLM"""
        parameters = {}
        
        # Create parameter extraction prompt
        param_descriptions = []
        for param in template.get('parameters', []):
            desc = f"- {param['name']} ({param['type']}): {param['description']}"
            if 'allowed_values' in param:
                desc += f" - Allowed values: {', '.join(param['allowed_values'])}"
            if 'default' in param:
                desc += f" - Default: {param['default']}"
            param_descriptions.append(desc)
        
        extraction_prompt = f"""
Extract parameters from this user query based on the template requirements.

Template: {template['description']}
Parameters needed:
{chr(10).join(param_descriptions)}

User query: "{user_query}"

Extract the parameters as a JSON object. Use null for missing optional parameters.
Only include parameters that are clearly mentioned or can be reasonably inferred.
For numeric values, extract only the number (e.g., "customer 123" -> "customer_id": 123).
For amounts, extract the number (e.g., "over $500" -> "min_amount": 500).

Return only the JSON object, no other text:
"""
        
        try:
            response = self.ollama_client.generate_response(extraction_prompt, self.inference_model)
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                extracted_params = json.loads(json_match.group())
                
                # Validate and set defaults
                for param in template.get('parameters', []):
                    param_name = param['name']
                    
                    if param_name in extracted_params:
                        # Type conversion
                        if param['type'] == 'integer':
                            try:
                                parameters[param_name] = int(extracted_params[param_name])
                            except (ValueError, TypeError):
                                pass
                        elif param['type'] == 'decimal':
                            try:
                                parameters[param_name] = float(extracted_params[param_name])
                            except (ValueError, TypeError):
                                pass
                        else:
                            parameters[param_name] = extracted_params[param_name]
                    
                    # Set default if required and missing
                    elif param.get('required', False) and 'default' in param:
                        if param['type'] == 'integer':
                            parameters[param_name] = int(param['default'])
                        elif param['type'] == 'decimal':
                            parameters[param_name] = float(param['default'])
                        else:
                            parameters[param_name] = param['default']
                
                logger.info(f"Extracted parameters: {parameters}")
                return parameters
                
        except Exception as e:
            logger.error(f"Error extracting parameters: {e}")
        
        return {}
    
    def get_search_conditions(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Override to use semantic search instead of text matching
        """
        if not self.templates_loaded:
            raise ValueError("Templates not loaded. Call populate_templates() first.")
        
        # Find best matching template
        best_match = self.find_best_template(query)
        
        if not best_match:
            raise ValueError("No matching query template found")
        
        template = best_match['template']
        
        # Extract parameters using LLM
        parameters = self.extract_parameters(query, template)
        
        # Return formatted SQL with parameters
        return {
            "sql": template['sql_template'],
            "params": parameters,
            "template_id": template['id'],
            "confidence": best_match['similarity'],
            "template": template
        }
    
    def generate_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Generate natural language response using LLM"""
        try:
            # Format results for LLM
            if results:
                results_text = json.dumps(results, indent=2, default=str)
            else:
                results_text = "No results found."
            
            response_prompt = f"""
You are a helpful data assistant. Based on the user's question and the query results, provide a clear and concise response.

User question: "{user_query}"
Query type: {template['description']}
Results: {results_text}

Provide a helpful response that answers the user's question using the data. Be conversational and informative.
"""
            
            return self.ollama_client.generate_response(response_prompt, self.inference_model)
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm sorry, I encountered an error processing your request."
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format results using LLM to generate natural language responses
        """
        template = metadata.get('template', {})
        user_query = metadata.get('user_query', '')
        
        # Parse raw document (should be JSON from SQL results)
        try:
            if isinstance(raw_doc, str):
                results = json.loads(raw_doc)
            else:
                results = raw_doc
                
            # Generate contextual response using LLM
            response = self.generate_response(user_query, results, template)
            
            return {
                "content": response,
                "metadata": metadata,
                "template_used": template.get('id', ''),
                "confidence": metadata.get('confidence', 0.0),
                "raw_results": results
            }
        except Exception as e:
            logger.error(f"Error formatting document: {e}")
            return {
                "content": "Error processing results",
                "metadata": metadata,
                "error": str(e)
            }
    
    def apply_domain_specific_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Apply semantic intent specific filtering"""
        # Filter by confidence threshold
        filtered = [
            item for item in context_items 
            if item.get('confidence', 0.0) >= self.confidence_threshold
        ]
        
        # Sort by confidence
        filtered.sort(key=lambda x: x.get('confidence', 0.0), reverse=True)
        
        return filtered

# Register with the factory
DocumentAdapterFactory.register_adapter(
    "semantic_intent", 
    lambda **kwargs: SemanticIntentAdapter(**kwargs)
)

logger.info("SemanticIntentAdapter registered with DocumentAdapterFactory") 