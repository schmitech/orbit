"""
Intent-based PostgreSQL retriever implementation
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List, Optional
import os

from .base_intent_sql_retriever import BaseIntentSQLRetriever
from ...base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentPostgreSQLRetriever(BaseIntentSQLRetriever):
    """PostgreSQL-specific implementation of intent-based retriever."""
    
    def _create_database_connection(self):
        """Create PostgreSQL connection using datasource configuration."""
        try:
            # Get PostgreSQL configuration
            postgres_conf = self.datasource_config
            
            # Extract connection parameters with environment variable fallback
            def get_config_value(key, default):
                """Get config value with environment variable fallback"""
                value = postgres_conf.get(key, default)
                
                if self.verbose:
                    # Mask sensitive values like passwords
                    if key.lower() in ['password', 'pass', 'pwd']:
                        masked_value = '*' * len(str(value)) if value else ''
                        logger.info(f"Config key '{key}': raw value = '{masked_value}', default = '{default}'")
                    else:
                        logger.info(f"Config key '{key}': raw value = '{value}', default = '{default}'")
                
                # If the value looks like an environment variable placeholder, resolve it
                if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                    env_var_name = value[2:-1]
                    env_value = os.environ.get(env_var_name)
                    if self.verbose:
                        logger.info(f"Resolving env var '{env_var_name}': found = {env_value is not None}")
                    if env_value is not None:
                        return env_value
                    else:
                        logger.warning(f"Environment variable {env_var_name} not found, using default: {default}")
                        return default
                
                return value
            
            # Extract connection parameters with proper environment variable resolution
            host = get_config_value('host', 'localhost')
            port = get_config_value('port', 5432)
            database = get_config_value('database', 'postgres')
            username = get_config_value('username', 'postgres')
            password = get_config_value('password', '')
            sslmode = get_config_value('sslmode', 'prefer')
            
            # Convert port to int if it's a string
            if isinstance(port, str):
                try:
                    port = int(port)
                except ValueError:
                    logger.warning(f"Invalid port value '{port}', using default port 5432")
                    port = 5432
            
            if self.verbose:
                logger.info(f"Connecting to PostgreSQL: {host}:{port}/{database} (user: {username})")
            
            # Create connection
            connection = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                sslmode=sslmode,
                cursor_factory=RealDictCursor  # Use dict cursor for easier result handling
            )
            
            # Test the connection
            cursor = connection.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            
            if version and self.verbose:
                logger.info(f"PostgreSQL connection successful: {version['version']}")
            
            return connection
            
        except ImportError:
            logger.error("psycopg2 not available. Install with: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
    
    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute a SQL query and return a list of dictionaries."""
        if not self.connection:
            raise Exception("PostgreSQL connection is not initialized.")
        
        cursor = None
        try:
            # Use a new cursor for each execution for thread safety
            cursor = self.connection.cursor()
            
            logger.info(f"Executing PostgreSQL query: {query}")
            if params:
                logger.info(f"Parameters: {params}")
            
            cursor.execute(query, params)
            
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                # RealDictCursor returns a list of dict-like objects.
                # We convert them to standard dicts and handle special data types.
                converted_results = [self._convert_row_types(dict(row)) for row in results]
                if self.verbose:
                    # Dump to file instead of logging
                    self._dump_results_to_file(converted_results)
                return converted_results
            else:
                # For non-SELECT queries, commit and return affected row count
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception as e:
            logger.error(f"Error executing PostgreSQL query: {e}")
            logger.error(f"SQL: {query}, Params: {params}")
            if self.connection:
                self.connection.rollback()
            # Re-raise the exception to be handled by the caller
            raise
        finally:
            if cursor:
                cursor.close()
    
    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return "postgres"
    
    async def close(self) -> None:
        """Close PostgreSQL connection and any open services."""
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                if self.verbose:
                    logger.info("PostgreSQL connection closed")
        except Exception as e:
            logger.error(f"Error closing PostgreSQL connection: {e}")
        
        # Call parent close method
        await super().close()
    
    def _convert_row_types(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert PostgreSQL-specific types to standard Python types."""
        from decimal import Decimal
        from datetime import datetime, date
        import uuid
        
        converted = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, (datetime, date)):
                converted[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                converted[key] = str(value)
            elif isinstance(value, memoryview):
                # Handle bytea/binary data
                converted[key] = value.tobytes().decode('utf-8', errors='ignore')
            else:
                converted[key] = value
        return converted
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for better matching."""
        import re
        # Simple tokenization - split on whitespace and punctuation
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    def _calculate_similarity(self, query: str, text: str) -> float:
        """Calculate similarity between query and text using simple word overlap."""
        query_tokens = set(self._tokenize_text(query))
        text_tokens = set(self._tokenize_text(text))
        
        if not query_tokens or not text_tokens:
            return 0.0
        
        intersection = query_tokens & text_tokens
        union = query_tokens | text_tokens
        
        return len(intersection) / len(union) if union else 0.0


# Register the intent retriever with the factory
RetrieverFactory.register_retriever('intent_postgresql', IntentPostgreSQLRetriever)