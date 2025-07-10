#!/usr/bin/env python3
"""
Semantic RAG System using ChromaDB, Ollama embeddings, and Ollama inference
This system stores query templates in ChromaDB and uses semantic search to match user intents.
"""

import yaml
import chromadb
from chromadb.config import Settings
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import json
import re
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv, find_dotenv
import os
from decimal import Decimal

class OllamaEmbeddingClient:
    """Client for Ollama embeddings using nomic-embed-text model"""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = "nomic-embed-text"
    
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
            print(f"❌ Error getting embedding: {e}")
            return []

class OllamaInferenceClient:
    """Client for Ollama inference using gemma3:1b model"""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = "gemma3:1b"
    
    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        """Generate response using Ollama"""
        try:
            payload = {
                "model": self.model,
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
            print(f"❌ Error generating response: {e}")
            return "I'm sorry, I encountered an error processing your request."

class DatabaseClient:
    """Client for PostgreSQL database operations"""
    
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
    
    def execute_query(self, sql: str, params: Dict[str, Any] = None) -> List[Dict]:
        """Execute SQL query and return results"""
        connection = None
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
            
            cursor.close()
            return results
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            return []
        finally:
            if connection:
                connection.close()

class SemanticRAGSystem:
    """Main RAG system that combines ChromaDB, embeddings, and inference"""
    
    def __init__(self, chroma_persist_directory: str = "./chroma_db"):
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.embedding_client = OllamaEmbeddingClient()
        self.inference_client = OllamaInferenceClient()
        self.db_client = DatabaseClient()
        
        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="query_templates",
            metadata={"hnsw:space": "cosine"}
        )
    
    def load_templates_from_yaml(self, yaml_file: str) -> List[Dict]:
        """Load query templates from YAML file"""
        try:
            with open(yaml_file, 'r') as file:
                data = yaml.safe_load(file)
                return data.get('templates', [])
        except Exception as e:
            print(f"❌ Error loading templates: {e}")
            return []
    
    def create_embedding_text(self, template: Dict) -> str:
        """Create text for embedding from template"""
        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(template.get('tags', []))
        ]
        return ' '.join(parts)
    
    def create_metadata(self, template: Dict) -> Dict:
        """Create ChromaDB-compatible metadata from template"""
        # ChromaDB metadata can only contain primitive types
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
    
    def populate_chromadb(self, yaml_file: str):
        """Populate ChromaDB with query templates from YAML"""
        templates = self.load_templates_from_yaml(yaml_file)
        
        if not templates:
            print("❌ No templates found")
            return
        
        print(f"📚 Loading {len(templates)} templates into ChromaDB...")
        
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
            print(f"✅ Successfully loaded {len(ids)} templates")
        else:
            print("❌ No valid embeddings generated")
    
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
            response = self.inference_client.generate_response(extraction_prompt)
            
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
                
                print(f"🔍 Extracted parameters: {parameters}")
                return parameters
                
        except Exception as e:
            print(f"❌ Error extracting parameters: {e}")
        
        return {}
    
    def find_best_template(self, user_query: str, n_results: int = 3) -> List[Dict]:
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
            print(f"❌ Error finding template: {e}")
            return []
    
    def execute_template(self, template: Dict, parameters: Dict[str, Any]) -> List[Dict]:
        """Execute a query template with parameters"""
        try:
            sql_template = template['sql_template']
            results = self.db_client.execute_query(sql_template, parameters)
            return results
        except Exception as e:
            print(f"❌ Error executing template: {e}")
            return []
    
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
            
            return self.inference_client.generate_response(response_prompt)
            
        except Exception as e:
            print(f"❌ Error generating response: {e}")
            return "I'm sorry, I encountered an error processing your request."
    
    def process_query(self, user_query: str) -> Dict[str, Any]:
        """Main method to process a user query end-to-end"""
        print(f"\n🤔 Processing query: {user_query}")
        print("-" * 60)
        
        # Step 1: Find best matching template
        templates = self.find_best_template(user_query)
        
        if not templates:
            return {
                'success': False,
                'error': 'No matching query template found'
            }
        
        best_template = templates[0]
        template = best_template['template']
        similarity = best_template['similarity']
        
        print(f"📋 Best match: {template['id']} (similarity: {similarity:.3f})")
        print(f"📝 Description: {template['description']}")
        
        # Step 2: Extract parameters
        parameters = self.extract_parameters(user_query, template)
        
        # Step 3: Execute query
        results = self.execute_template(template, parameters)
        
        print(f"📊 Query returned {len(results)} results")
        
        # Step 4: Generate response
        response = self.generate_response(user_query, results, template)
        
        return {
            'success': True,
            'template_id': template['id'],
            'similarity': similarity,
            'parameters': parameters,
            'results': results,
            'response': response,
            'result_count': len(results)
        }

def main():
    """Main function to demonstrate the system"""
    # Initialize the RAG system
    rag_system = SemanticRAGSystem()
    
    # Populate ChromaDB with templates (run once)
    print("🚀 Initializing Semantic RAG System...")
    rag_system.populate_chromadb("query_templates.yaml")
    
    # Example queries to test
    test_queries = [
        "What did customer 1 buy last week?",
        "Show me all orders over $500 from last month",
        "Find delivered orders from last week",
        "Give me a summary for customer 5",
        "Show orders from New York customers",
        "What orders were paid with credit card?"
    ]
    
    print("\n🧪 Testing the system with example queries:")
    print("=" * 60)
    
    for query in test_queries:
        result = rag_system.process_query(query)
        
        if result['success']:
            print(f"\n✅ Query: {query}")
            print(f"📋 Template: {result['template_id']}")
            print(f"🎯 Similarity: {result['similarity']:.3f}")
            print(f"🔍 Parameters: {result['parameters']}")
            print(f"📊 Results: {result['result_count']} records")
            print(f"💬 Response: {result['response']}")
        else:
            print(f"\n❌ Query: {query}")
            print(f"❌ Error: {result['error']}")
        
        print("-" * 60)

if __name__ == "__main__":
    main() 