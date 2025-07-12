#!/usr/bin/env python3
"""
Enhanced Semantic RAG System using ChromaDB, Ollama embeddings, and Ollama inference
This system stores query templates in ChromaDB and uses semantic search to match user intents.
Enhanced with better parameter extraction, error handling, and conversation capabilities.
"""

import yaml
import chromadb
from chromadb.config import Settings
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv, find_dotenv
import os
from decimal import Decimal
from datetime import datetime, date, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class OllamaEmbeddingClient:
    """Client for Ollama embeddings using nomic-embed-text model"""
    
    def __init__(self, base_url: str = None):
        # Load environment variables first
        env_file = find_dotenv()
        if env_file:
            load_dotenv(env_file, override=True)
        
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text using Ollama"""
        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return []


class OllamaInferenceClient:
    """Enhanced Client for Ollama inference with better prompting"""
    
    def __init__(self, base_url: str = None, model: str = None):
        # Load environment variables first
        env_file = find_dotenv()
        if env_file:
            load_dotenv(env_file, override=True)
        
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = model or os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')
        self.system_prompt = """You are a helpful database assistant. When presenting query results, always:
1. Include specific details from the data (names, amounts, dates, etc.)
2. Format currency with $ and proper comma separators
3. Present dates in a readable format
4. Be conversational but informative
5. Never just state counts - always include relevant details from the results"""
    
    def generate_response(self, prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str:
        """Generate response using Ollama with temperature control"""
        try:
            # Use custom system prompt if provided, otherwise use default
            actual_system_prompt = system_prompt if system_prompt else self.system_prompt
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "system": actual_system_prompt,
                "options": {
                    "temperature": temperature
                }
            }
            
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


class DatabaseClient:
    """Enhanced Client for PostgreSQL database operations with better error handling"""
    
    def __init__(self):
        self.reload_env_variables()
        self.config = self.get_db_config()
    
    def reload_env_variables(self):
        """Reload environment variables from .env file"""
        env_file = find_dotenv()
        if env_file:
            load_dotenv(env_file, override=True)
    
    def get_db_config(self):
        """Get database configuration from environment variables"""
        return {
            'host': os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('DATASOURCE_POSTGRES_PORT', '5432')),
            'database': os.getenv('DATASOURCE_POSTGRES_DATABASE', 'orbit'),
            'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres'),
            'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres'),
            'sslmode': os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
        }
    
    def execute_query(self, sql: str, params: Dict[str, Any] = None) -> Tuple[List[Dict], Optional[str]]:
        """Execute SQL query and return results with error message if any"""
        connection = None
        error_message = None
        try:
            connection = psycopg2.connect(**self.config)
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            
            # Format SQL with parameters
            if params:
                formatted_sql = sql.format(**params)
            else:
                formatted_sql = sql
            
            cursor.execute(formatted_sql)
            results = cursor.fetchall()
            
            # Convert Decimal to float for JSON serialization
            for result in results:
                for key, value in result.items():
                    if isinstance(value, Decimal):
                        result[key] = float(value)
                    elif isinstance(value, (date, datetime)):
                        result[key] = str(value)
            
            cursor.close()
            return results, None
            
        except psycopg2.ProgrammingError as e:
            error_message = f"SQL syntax error: {str(e)}"
            logger.error(error_message)
            return [], error_message
        except psycopg2.IntegrityError as e:
            error_message = f"Data integrity error: {str(e)}"
            logger.error(error_message)
            return [], error_message
        except Exception as e:
            error_message = f"Database error: {str(e)}"
            logger.error(error_message)
            return [], error_message
        finally:
            if connection:
                connection.close()


class ParameterExtractor:
    """Enhanced parameter extraction with better NLP understanding"""
    
    def __init__(self, inference_client: OllamaInferenceClient):
        self.inference_client = inference_client
        
        # Common patterns for parameter extraction
        self.patterns = {
            'customer_id': re.compile(r'customer\s*(?:id\s*)?(?:#|number|id)?\s*(\d+)', re.IGNORECASE),
            'amount': re.compile(r'\$?\s*(\d+(?:\.\d{2})?)', re.IGNORECASE),
            'days': re.compile(r'(?:last|past|previous)\s*(\d+)\s*days?', re.IGNORECASE),
            'email': re.compile(r'[\w\.-]+@[\w\.-]+\.\w+', re.IGNORECASE),
            'date': re.compile(r'\d{4}-\d{2}-\d{2}'),
        }
        
        # Time period mappings
        self.time_mappings = {
            'today': 0,
            'yesterday': 1,
            'this week': 7,
            'last week': 14,
            'this month': 30,
            'last month': 60,
            'this year': 365,
        }
    
    def extract_time_period(self, text: str) -> Optional[int]:
        """Extract time period from natural language"""
        text_lower = text.lower()
        
        # Check for specific time mappings
        for phrase, days in self.time_mappings.items():
            if phrase in text_lower:
                return days
        
        # Check for pattern-based extraction
        days_match = self.patterns['days'].search(text)
        if days_match:
            return int(days_match.group(1))
        
        # Check for week/month references
        if 'week' in text_lower:
            weeks_match = re.search(r'(\d+)\s*weeks?', text_lower)
            if weeks_match:
                return int(weeks_match.group(1)) * 7
            return 7  # Default to 1 week
        
        if 'month' in text_lower:
            months_match = re.search(r'(\d+)\s*months?', text_lower)
            if months_match:
                return int(months_match.group(1)) * 30
            return 30  # Default to 1 month
        
        return None
    
    def extract_amount_range(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract amount range from text (e.g., 'between $100 and $500')"""
        # Pattern for range
        range_pattern = re.compile(
            r'(?:between|from)?\s*\$?\s*(\d+(?:\.\d{2})?)\s*(?:to|and|-)\s*\$?\s*(\d+(?:\.\d{2})?)',
            re.IGNORECASE
        )
        
        range_match = range_pattern.search(text)
        if range_match:
            min_amount = float(range_match.group(1))
            max_amount = float(range_match.group(2))
            return min_amount, max_amount
        
        # Pattern for single threshold
        if 'over' in text.lower() or 'above' in text.lower() or 'more than' in text.lower():
            amount_match = self.patterns['amount'].search(text)
            if amount_match:
                return float(amount_match.group(1)), None
        
        if 'under' in text.lower() or 'below' in text.lower() or 'less than' in text.lower():
            amount_match = self.patterns['amount'].search(text)
            if amount_match:
                return None, float(amount_match.group(1))
        
        return None, None
    
    def extract_status(self, text: str) -> Optional[str]:
        """Extract order status from text"""
        statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
        text_lower = text.lower()
        
        for status in statuses:
            if status in text_lower:
                return status
        
        # Handle variations
        if 'cancel' in text_lower:
            return 'cancelled'
        if 'deliver' in text_lower:
            return 'delivered'
        if 'ship' in text_lower:
            return 'shipped'
        if 'process' in text_lower:
            return 'processing'
        
        return None
    
    def extract_payment_method(self, text: str) -> Optional[str]:
        """Extract payment method from text"""
        payment_methods = {
            'credit_card': ['credit card', 'credit'],
            'debit_card': ['debit card', 'debit'],
            'paypal': ['paypal', 'pay pal'],
            'bank_transfer': ['bank transfer', 'bank', 'transfer'],
            'cash': ['cash']
        }
        
        text_lower = text.lower()
        for method, keywords in payment_methods.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return method
        
        return None
    
    def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """Enhanced parameter extraction using multiple strategies"""
        parameters = {}
        
        # Try pattern-based extraction first
        for param in template.get('parameters', []):
            param_name = param['name']
            param_type = param['type']
            
            if param_name == 'customer_id' and param_type == 'integer':
                match = self.patterns['customer_id'].search(user_query)
                if match:
                    parameters[param_name] = int(match.group(1))
            
            elif param_name == 'customer_name' and param_type == 'string':
                # Use LLM for name extraction
                name = self._extract_name_with_llm(user_query)
                if name:
                    parameters[param_name] = name
            
            elif param_name == 'days_back' and param_type == 'integer':
                days = self.extract_time_period(user_query)
                if days is not None:
                    parameters[param_name] = days
            
            elif param_name in ['min_amount', 'max_amount'] and param_type == 'decimal':
                min_amt, max_amt = self.extract_amount_range(user_query)
                if param_name == 'min_amount' and min_amt is not None:
                    parameters[param_name] = min_amt
                elif param_name == 'max_amount' and max_amt is not None:
                    parameters[param_name] = max_amt
            
            elif param_name == 'status' and param_type == 'string':
                status = self.extract_status(user_query)
                if status:
                    parameters[param_name] = status
            
            elif param_name == 'payment_method' and param_type == 'string':
                method = self.extract_payment_method(user_query)
                if method:
                    parameters[param_name] = method
            
            elif param_name == 'email' and param_type == 'string':
                match = self.patterns['email'].search(user_query)
                if match:
                    parameters[param_name] = match.group(0)
            
            elif param_name in ['city', 'country'] and param_type == 'string':
                # Use LLM for location extraction
                location = self._extract_location_with_llm(user_query, param_name)
                if location:
                    parameters[param_name] = location
        
        # Fall back to LLM extraction for missing required parameters
        missing_params = []
        for param in template.get('parameters', []):
            if param.get('required', False) and param['name'] not in parameters:
                missing_params.append(param)
        
        if missing_params:
            llm_params = self._extract_with_llm(user_query, template, missing_params)
            parameters.update(llm_params)
        
        # Apply defaults for missing optional parameters
        for param in template.get('parameters', []):
            if param['name'] not in parameters and 'default' in param:
                if param['type'] == 'integer':
                    parameters[param['name']] = int(param['default'])
                elif param['type'] == 'decimal':
                    parameters[param['name']] = float(param['default'])
                else:
                    parameters[param['name']] = param['default']
        
        return parameters
    
    def _extract_name_with_llm(self, text: str) -> Optional[str]:
        """Extract person name using LLM"""
        prompt = f"""Extract the person's name from this text. Return ONLY the name, nothing else.
If no name is found, return "None".

Text: "{text}"

Name:"""
        
        response = self.inference_client.generate_response(prompt, temperature=0.1)
        response = response.strip()
        
        if response and response.lower() != 'none' and len(response) < 100:
            return response
        return None
    
    def _extract_location_with_llm(self, text: str, location_type: str) -> Optional[str]:
        """Extract location (city or country) using LLM"""
        prompt = f"""Extract the {location_type} name from this text. Return ONLY the {location_type} name, nothing else.
If no {location_type} is found, return "None".

Text: "{text}"

{location_type.capitalize()}:"""
        
        response = self.inference_client.generate_response(prompt, temperature=0.1)
        response = response.strip()
        
        if response and response.lower() != 'none' and len(response) < 100:
            return response
        return None
    
    def _extract_with_llm(self, user_query: str, template: Dict, missing_params: List[Dict]) -> Dict[str, Any]:
        """Extract missing parameters using LLM"""
        param_descriptions = []
        for param in missing_params:
            desc = f"- {param['name']} ({param['type']}): {param['description']}"
            if 'allowed_values' in param:
                desc += f" - Allowed values: {', '.join(param['allowed_values'])}"
            param_descriptions.append(desc)
        
        extraction_prompt = f"""Extract the following parameters from the user query.
Return ONLY a valid JSON object with the extracted values.
Use null for parameters that cannot be found.

Parameters needed:
{chr(10).join(param_descriptions)}

User query: "{user_query}"

JSON:"""
        
        try:
            response = self.inference_client.generate_response(extraction_prompt, temperature=0.1)
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group())
                
                # Type conversion and validation
                result = {}
                for param in missing_params:
                    param_name = param['name']
                    if param_name in extracted and extracted[param_name] is not None:
                        try:
                            if param['type'] == 'integer':
                                result[param_name] = int(extracted[param_name])
                            elif param['type'] == 'decimal':
                                result[param_name] = float(extracted[param_name])
                            else:
                                result[param_name] = str(extracted[param_name])
                        except (ValueError, TypeError):
                            pass
                
                return result
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
        
        return {}


class ResponseGenerator:
    """Enhanced response generation with better formatting and insights"""
    
    def __init__(self, inference_client: OllamaInferenceClient):
        self.inference_client = inference_client
    
    def generate_response(self, user_query: str, results: List[Dict], template: Dict, 
                         error: Optional[str] = None) -> str:
        """Generate enhanced natural language response"""
        
        if error:
            return self._generate_error_response(error, user_query)
        
        if not results:
            return self._generate_no_results_response(user_query, template)
        
        # Choose response strategy based on result format
        if template.get('result_format') == 'summary':
            return self._generate_summary_response(user_query, results, template)
        else:
            return self._generate_table_response(user_query, results, template)
    
    def _generate_error_response(self, error: str, user_query: str) -> str:
        """Generate helpful error response"""
        prompt = f"""The user asked: "{user_query}"

However, there was an error: {error}

Provide a helpful, conversational response that acknowledges the issue and suggests what might have gone wrong or alternative ways to ask. Be brief and friendly.

Important: Give ONLY the direct response."""
        
        return self.inference_client.generate_response(prompt)
    
    def _generate_no_results_response(self, user_query: str, template: Dict) -> str:
        """Generate response when no results found"""
        prompt = f"""The user asked: "{user_query}"

The query returned no results. This was a {template['description']} query.

Provide a helpful response explaining no results were found and suggest why this might be (e.g., no matching records, time period too restrictive). Offer suggestions for modifying the query. Be conversational and helpful.

Important: Give ONLY the direct response."""
        
        return self.inference_client.generate_response(prompt)
    
    def _generate_summary_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Generate response for summary queries"""
        # Format results for better readability
        if len(results) == 1:
            result = results[0]
            formatted_result = json.dumps(result, indent=2, default=str)
        else:
            formatted_result = json.dumps(results[:5], indent=2, default=str)  # Limit to 5 for prompt
        
        prompt = f"""The user asked: "{user_query}"

This is a {template['description']} query that returned summary data:

{formatted_result}

Provide a natural, conversational response that directly answers the question. Include specific numbers and details from the data. Format currency with $ and commas. Be specific and informative, not just stating counts.

Important: Give ONLY the direct response. No explanations about why the response works or what makes it good."""
        
        response = self.inference_client.generate_response(prompt, temperature=0.3)
        return response
    
    def _generate_table_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Generate response for table/list queries"""
        result_count = len(results)
        
        # Show sample of results for context
        sample_size = min(5, result_count)
        sample_results = results[:sample_size]
        formatted_sample = json.dumps(sample_results, indent=2, default=str)
        
        # Create a more detailed prompt with examples
        prompt = f"""The user asked: "{user_query}"

This query returned {result_count} results. Here's a sample of the data:

{formatted_sample}

Provide a natural, conversational response that:
- States how many results were found
- Mentions specific details from the results (customer names, order amounts, dates, etc.)
- Highlights interesting patterns or notable items
- Formats currency with $ and commas, dates in readable format

For example, instead of "There are 2 orders", say something like "I found 2 orders from Maria Smith. The first was on June 30th for $646.17 (shipped), and the second on June 28th for $194.52 (also shipped)."

Important: Give ONLY the direct response. Use the actual data details, don't just state counts."""
        
        response = self.inference_client.generate_response(prompt, temperature=0.3)
        return response


class SemanticRAGSystem:
    """Enhanced RAG system with better matching and response generation"""
    
    def __init__(self, chroma_persist_directory: str = "./chroma_db"):
        self.chroma_persist_directory = chroma_persist_directory
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.embedding_client = OllamaEmbeddingClient()
        self.inference_client = OllamaInferenceClient()
        self.db_client = DatabaseClient()
        self.parameter_extractor = ParameterExtractor(self.inference_client)
        self.response_generator = ResponseGenerator(self.inference_client)
        
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
        """Create enhanced text for embedding from template"""
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
    
    def validate_parameters(self, parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]:
        """Validate extracted parameters against template requirements"""
        errors = []
        
        for param in template.get('parameters', []):
            param_name = param['name']
            param_type = param['type']
            required = param.get('required', False)
            
            if required and param_name not in parameters:
                errors.append(f"Missing required parameter: {param_name}")
                continue
            
            if param_name in parameters:
                value = parameters[param_name]
                
                # Type validation
                if param_type == 'integer' and not isinstance(value, int):
                    errors.append(f"Parameter {param_name} must be an integer")
                elif param_type == 'decimal' and not isinstance(value, (int, float)):
                    errors.append(f"Parameter {param_name} must be a number")
                elif param_type == 'string' and not isinstance(value, str):
                    errors.append(f"Parameter {param_name} must be a string")
                
                # Allowed values validation
                if 'allowed_values' in param and value not in param['allowed_values']:
                    errors.append(f"Parameter {param_name} must be one of: {', '.join(param['allowed_values'])}")
        
        return len(errors) == 0, errors
    
    def execute_template(self, template: Dict, parameters: Dict[str, Any]) -> Tuple[List[Dict], Optional[str]]:
        """Execute a query template with parameters"""
        try:
            sql_template = template['sql_template']
            results, error = self.db_client.execute_query(sql_template, parameters)
            return results, error
        except Exception as e:
            logger.error(f"Error executing template: {e}")
            return [], str(e)
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]:
        """Rerank templates using additional heuristics"""
        query_lower = user_query.lower()
        
        for template_info in templates:
            template = template_info['template']
            boost = 0.0
            
            # Boost for exact keyword matches
            for tag in template['tags']:
                if tag.lower() in query_lower:
                    boost += 0.1
            
            # Boost for parameter type matches
            if 'customer' in query_lower and any(p['name'] == 'customer_id' for p in template['parameters']):
                boost += 0.05
            if 'amount' in user_query or 'dollar' in query_lower:
                if any(p['name'] in ['min_amount', 'max_amount'] for p in template['parameters']):
                    boost += 0.05
            
            # Apply boost
            template_info['similarity'] = min(1.0, template_info['similarity'] + boost)
        
        # Re-sort by adjusted similarity
        return sorted(templates, key=lambda x: x['similarity'], reverse=True)
    
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
        """Enhanced query processing with better error handling and context"""
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
            valid, errors = self.validate_parameters(parameters, template)
            
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
        """Print the current configuration being used"""
        print("🤖 Current Configuration:")
        print(f"  Ollama Server: {self.embedding_client.base_url}")
        print(f"  Embedding Model: {self.embedding_client.model}")
        print(f"  Inference Model: {self.inference_client.model}")
        print(f"  ChromaDB Path: {self.chroma_persist_directory}")
        print(f"  PostgreSQL: {self.db_client.config['host']}:{self.db_client.config['port']}/{self.db_client.config['database']}")
        
        # Test embedding dimensions
        try:
            test_embedding = self.embedding_client.get_embedding("test")
            if test_embedding:
                print(f"  Embedding Dimensions: {len(test_embedding)}")
            else:
                print("  Embedding Dimensions: Failed to get test embedding")
        except Exception as e:
            print(f"  Embedding Dimensions: Error - {e}")


def main():
    """Main function to demonstrate the enhanced system"""
    # Load environment variables first
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
        print(f"🔄 Loaded environment from: {env_file}")
    
    # Display configuration
    print("🚀 Initializing Enhanced Semantic RAG System...")
    print("=" * 60)
    print("🤖 Ollama Configuration:")
    print(f"  Server: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
    print(f"  Embedding Model: {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}")
    print(f"  Inference Model: {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}")
    print("=" * 60)
    
    # Initialize the RAG system
    rag_system = SemanticRAGSystem()
    
    # Display actual configuration being used
    rag_system.print_configuration()
    print()
    
    # Populate ChromaDB with templates
    rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
    
    # Test queries demonstrating various capabilities
    test_queries = [
        # Customer queries
        "What did customer 1 buy last week?",
        "Show me orders from Maria Smith",
        "What's the lifetime value of customer 123?",
        
        # Amount queries
        "Show me all orders over $500 from last month",
        "Find orders between $100 and $500",
        "What are the smallest orders recently?",
        
        # Status queries
        "Show me all pending orders",
        "Which orders need attention?",
        
        # Location queries
        "Show orders from New York customers",
        "Orders from customers in France",
        
        # Payment queries
        "How are customers paying?",
        "Show me credit card orders",
        
        # Analytics queries
        "Who are our top 10 customers?",
        "Show me new customers from this week",
        "How are sales trending?",
        
        # Search queries
        "Find customer with email john@example.com",
        "Show inactive customers",
        
        # Time-based queries
        "What were yesterday's sales?",
        "Show me today's revenue",
        
        # Complex queries
        "Find all expensive orders over $1000 from VIP customers in New York paid with credit card"
    ]
    
    print("\n🧪 Testing the enhanced system with example queries:")
    print("=" * 80)
    
    for query in test_queries[:5]:  # Test first 5 queries
        result = rag_system.process_query(query)
        
        print(f"\n📝 Query: {query}")
        print(f"✅ Success: {result['success']}")
        
        if result['success']:
            print(f"📋 Template: {result['template_id']}")
            print(f"🎯 Similarity: {result['similarity']:.3f}")
            print(f"🔍 Parameters: {result['parameters']}")
            print(f"📊 Results: {result['result_count']} records")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
            if 'validation_errors' in result:
                print(f"⚠️  Validation errors: {result['validation_errors']}")
        
        print(f"\n💬 Response:\n{result['response']}")
        print("-" * 80)


if __name__ == "__main__":
    main()