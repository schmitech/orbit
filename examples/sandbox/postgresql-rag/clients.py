#!/usr/bin/env python3
"""
RAG System Client Implementations
==================================

Concrete implementations of embedding, inference, and database clients
for the domain-agnostic RAG system.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import json
import os
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime, date
import logging
from dotenv import load_dotenv, find_dotenv

from base_classes import (
    BaseEmbeddingClient, 
    BaseInferenceClient, 
    BaseDatabaseClient
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
def reload_env_variables():
    """Reload environment variables from .env file"""
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
        logger.info(f"Loaded environment variables from: {env_file}")
    else:
        logger.info("No .env file found, using defaults")

# Load env on module import
reload_env_variables()


class OllamaEmbeddingClient(BaseEmbeddingClient):
    """Ollama-based embedding client"""
    
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = model or os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')
        
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding vector for text"""
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
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to Ollama at {self.base_url}")
            logger.error("Ensure Ollama is running and accessible")
            raise
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            raise


class OllamaInferenceClient(BaseInferenceClient):
    """Ollama-based inference client"""
    
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = model or os.getenv('OLLAMA_INFERENCE_MODEL', 'llama3.2:3b')
        
    def generate_response(self, prompt: str, system_prompt: Optional[str] = None, 
                         max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Generate a response using the inference model"""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
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
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Failed to connect to Ollama at {self.base_url}")
            logger.error("Ensure Ollama is running and accessible")
            raise
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise


class PostgreSQLDatabaseClient(BaseDatabaseClient):
    """PostgreSQL database client"""
    
    def __init__(self, conn_params: Optional[Dict[str, str]] = None):
        if conn_params:
            self.conn_params = conn_params
        else:
            # Load from environment variables
            self.conn_params = {
                'dbname': os.getenv('DATASOURCE_POSTGRES_DATABASE', 'customer_orders'),
                'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'db_user'),
                'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'db_password'),
                'host': os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost'),
                'port': os.getenv('DATASOURCE_POSTGRES_PORT', '5432')
            }
            
            # Add SSL mode if specified
            ssl_mode = os.getenv('DATASOURCE_POSTGRES_SSL_MODE')
            if ssl_mode:
                self.conn_params['sslmode'] = ssl_mode
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self):
        """Test database connection"""
        try:
            conn = psycopg2.connect(**self.conn_params)
            conn.close()
            logger.info("Successfully connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            logger.error("Check your database connection parameters")
            raise
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results"""
        conn = None
        cursor = None
        
        try:
            conn = psycopg2.connect(**self.conn_params)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            logger.debug(f"Executing query: {query}")
            logger.debug(f"With parameters: {params}")
            
            cursor.execute(query, params)
            
            # Check if this is a SELECT query
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                # Convert to standard Python types
                return [self._convert_types(dict(row)) for row in results]
            else:
                # For non-SELECT queries, return affected row count
                conn.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except psycopg2.Error as e:
            logger.error(f"Database error: {e}")
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def _convert_types(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert PostgreSQL types to Python types"""
        converted = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, (datetime, date)):
                converted[key] = value.isoformat()
            else:
                converted[key] = value
        return converted
    
    def get_schema_info(self) -> Dict[str, List[str]]:
        """Get database schema information"""
        query = """
        SELECT 
            table_name,
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
        
        results = self.execute_query(query)
        
        schema_info = {}
        for row in results:
            table_name = row['table_name']
            if table_name not in schema_info:
                schema_info[table_name] = []
            
            schema_info[table_name].append({
                'column': row['column_name'],
                'type': row['data_type'],
                'nullable': row['is_nullable'] == 'YES'
            })
        
        return schema_info