"""
Base SQL Database Retriever with common functionality for all SQL databases.
This module provides unified database operations to reduce code duplication.
"""

import logging
import os
import json
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, date
import uuid
from abc import abstractmethod
from pathlib import Path

from retrievers.base.sql_retriever import AbstractSQLRetriever

logger = logging.getLogger(__name__)


class SQLConnectionMixin:
    """Mixin for handling database connections with environment variable support."""
    
    def get_config_value(self, config: Dict[str, Any], key: str, default: Any = None) -> Any:
        """
        Get configuration value with environment variable resolution.
        
        Args:
            config: Configuration dictionary
            key: Configuration key
            default: Default value if not found
            
        Returns:
            Resolved configuration value
        """
        value = config.get(key, default)

        # Mask sensitive values
        if key.lower() in ['password', 'pass', 'pwd', 'secret', 'token']:
            masked_value = '*' * len(str(value)) if value else ''
            logger.debug(f"Config key '{key}': [MASKED]")
        else:
            logger.debug(f"Config key '{key}': {value}")

        # Resolve environment variables
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var_name = value[2:-1]
            env_value = os.environ.get(env_var_name)
            if env_value is not None:
                logger.debug(f"Resolved env var '{env_var_name}'")
                return env_value
            else:
                logger.warning(f"Environment variable {env_var_name} not found, using default: {default}")
                return default
        
        return value
    
    def extract_connection_params(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract common database connection parameters.
        
        Args:
            config: Database configuration
            
        Returns:
            Dictionary of connection parameters
        """
        params = {
            'host': self.get_config_value(config, 'host', 'localhost'),
            'port': self.get_config_value(config, 'port', self.get_default_port()),
            'database': self.get_config_value(config, 'database', self.get_default_database()),
            'username': self.get_config_value(config, 'username', self.get_default_username()),
            'password': self.get_config_value(config, 'password', ''),
        }
        
        # Convert port to int if needed
        if isinstance(params['port'], str):
            try:
                params['port'] = int(params['port'])
            except ValueError:
                default_port = self.get_default_port()
                logger.warning(f"Invalid port '{params['port']}', using default {default_port}")
                params['port'] = default_port
        
        return params
    
    @abstractmethod
    def get_default_port(self) -> int:
        """Get default port for the database type."""
        pass
    
    @abstractmethod
    def get_default_database(self) -> str:
        """Get default database name."""
        pass
    
    @abstractmethod
    def get_default_username(self) -> str:
        """Get default username."""
        pass


class SQLTypeConversionMixin:
    """Mixin for handling database type conversions."""
    
    def convert_row_types(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert database-specific types to standard Python types.
        
        Args:
            row: Database row as dictionary
            
        Returns:
            Row with converted types
        """
        converted = {}
        for key, value in row.items():
            converted[key] = self.convert_value(value)
        return converted
    
    def convert_value(self, value: Any) -> Any:
        """
        Convert a single value to standard Python type.
        
        Args:
            value: Value to convert
            
        Returns:
            Converted value
        """
        if isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, uuid.UUID):
            return str(value)
        elif isinstance(value, memoryview):
            # Handle binary data
            return value.tobytes().decode('utf-8', errors='ignore')
        elif hasattr(value, '__class__') and value.__class__.__name__ == 'RealDictRow':
            # Handle psycopg2 RealDictRow
            return dict(value)
        else:
            return value


class SQLQueryExecutionMixin:
    """Mixin for handling query execution and result processing."""
    
    def dump_results_to_file(self, results: List[Dict[str, Any]], prefix: str = "query_results"):
        """
        Dump query results to a timestamped JSON file for debugging.
        Only executes when log level is DEBUG.
        
        Args:
            results: Query results
            prefix: File prefix
        """
        # Only dump to file if DEBUG logging is enabled
        if not logger.isEnabledFor(logging.DEBUG):
            return
        
        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = log_dir / f"{prefix}_{timestamp}.json"
            
            with open(file_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            logger.debug(f"Query results saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to dump query results: {e}")
    
    async def execute_query_with_retry(self, query: str, params: Any = None, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Execute query with retry logic for transient failures.
        
        Args:
            query: SQL query
            params: Query parameters
            max_retries: Maximum retry attempts
            
        Returns:
            Query results
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                return await self.execute_query(query, params)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(f"Query attempt {attempt + 1} failed: {e}, retrying...")
                    # Wait before retry with exponential backoff
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise last_error


class BaseSQLDatabaseRetriever(AbstractSQLRetriever, SQLConnectionMixin, SQLTypeConversionMixin, SQLQueryExecutionMixin):
    """
    Unified base class for all SQL database retrievers.
    Combines common functionality to reduce code duplication.

    Uses the datasource registry pattern - connection is obtained from the datasource instance.
    """

    def __init__(self, config: Dict[str, Any], datasource: Any = None, **kwargs):
        """
        Initialize base SQL database retriever.

        Args:
            config: Configuration dictionary
            datasource: Datasource instance from the registry
            **kwargs: Additional arguments
        """
        super().__init__(config=config, datasource=datasource, **kwargs)

        # Extract connection parameters using mixin (may still be needed for legacy code)
        self.connection_params = self.extract_connection_params(self.datasource_config)

        # Database-specific settings
        self.use_connection_pool = self.datasource_config.get('use_connection_pool', False)
        self.pool_size = self.datasource_config.get('pool_size', 5)
        self.connection_timeout = self.datasource_config.get('connection_timeout', 30)
    
    async def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful
        """
        try:
            # Ensure datasource is initialized
            await self._ensure_datasource_initialized()

            if not self.connection:
                logger.error("Connection not available from datasource")
                return False

            # Execute a simple test query
            test_query = self.get_test_query()
            result = await self.execute_query(test_query)

            logger.debug(f"Database connection test successful: {self._get_datasource_name()}")

            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    @abstractmethod
    def get_test_query(self) -> str:
        """
        Get database-specific test query.
        Must be implemented by specific database types.
        """
        pass
    
    async def execute_query(self, query: str, params: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute query with common error handling and type conversion.
        Can be overridden by specific implementations if needed.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            List of result dictionaries
        """
        # Ensure datasource is initialized
        await self._ensure_datasource_initialized()

        if not self.connection:
            raise ValueError(f"{self._get_datasource_name()} connection not initialized")

        try:
            logger.debug(f"Executing {self._get_datasource_name()} query: {query}")
            if params:
                logger.debug(f"Parameters: {params}")

            # Execute query (implementation specific)
            raw_results = await self._execute_raw_query(query, params)

            # Convert types using mixin
            results = [self.convert_row_types(row) for row in raw_results]

            logger.debug(f"Query returned {len(results)} rows")
            if len(results) > 0:
                self.dump_results_to_file(results)

            return results

        except Exception as e:
            error_msg = str(e).lower()
            # Check if this is a connection closed error
            if 'connection' in error_msg and ('closed' in error_msg or 'lost' in error_msg or 'broken' in error_msg):
                logger.warning(f"Connection appears to be closed, attempting to reinitialize datasource...")
                try:
                    # Reinitialize the datasource
                    if self._datasource:
                        await self._datasource.close()
                        await self._datasource.initialize()
                        self._connection = self._datasource.get_client()

                    logger.info(f"Reconnected to {self._get_datasource_name()} successfully")

                    # Retry the query with the new connection
                    raw_results = await self._execute_raw_query(query, params)
                    results = [self.convert_row_types(row) for row in raw_results]

                    logger.debug(f"Query retry successful, returned {len(results)} rows")

                    return results

                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect to {self._get_datasource_name()}: {reconnect_error}")
                    raise

            logger.error(f"Error executing {self._get_datasource_name()} query: {e}")
            logger.error(f"SQL: {query}, Params: {params}")
            raise
    
    @abstractmethod
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """
        Execute raw query and return database-specific results.
        Must be implemented by specific database types.
        """
        pass