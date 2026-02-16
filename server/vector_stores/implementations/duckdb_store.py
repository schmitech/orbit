"""
DuckDB store implementation for analytical and relational data operations.
"""

import logging
import os
from typing import Dict, Any, List
import duckdb

from ..base.base_store import BaseStore, StoreConfig, StoreStatus

logger = logging.getLogger(__name__)


class DuckDBStore(BaseStore):
    """
    DuckDB store implementation providing analytical and relational data operations.
    
    This store provides:
    - SQL-based data management
    - CSV/Parquet import and export
    - Table creation and management
    - Query execution
    - No vector search capabilities (analytical focus)
    """
    
    def __init__(self, config: StoreConfig):
        """
        Initialize DuckDB store.
        
        Args:
            config: Store configuration
        """
        super().__init__(config)
        
        # DuckDB-specific configuration
        self.database_path = config.connection_params.get('database_path', ':memory:')
        self.read_only = config.connection_params.get('read_only', False)
        self.threads = config.connection_params.get('threads', None)
        
        # Connection state
        self._client = None
    
    async def connect(self) -> bool:
        """
        Establish connection to DuckDB.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self.status == StoreStatus.CONNECTED:
            return True
        
        self.status = StoreStatus.CONNECTING
        
        try:
            # Configure connection parameters
            config_params = {}
            if self.threads is not None:
                config_params['threads'] = self.threads
            
            # Create connection
            if config_params:
                self._client = duckdb.connect(self.database_path, read_only=self.read_only, config=config_params)
            else:
                self._client = duckdb.connect(self.database_path, read_only=self.read_only)
            
            self.status = StoreStatus.CONNECTED
            logger.info(f"DuckDB store '{self.config.name}' connected successfully.")
            return True
            
        except Exception as e:
            self.status = StoreStatus.ERROR
            logger.error(f"Error connecting to DuckDB: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection to DuckDB."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing DuckDB connection: {e}")
            
            self._client = None
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"DuckDB store '{self.config.name}' disconnected.")
    
    async def health_check(self) -> bool:
        """
        Check if the store is healthy and operational.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self._client:
            return False
        
        try:
            self._client.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    async def query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results.
        
        Args:
            sql: SQL query to execute
            
        Returns:
            List of result dictionaries
        """
        await self.ensure_connected()
        self.update_access_time()
        
        try:
            result = self._client.execute(sql).fetchall()
            columns = self._client.description
            
            if columns:
                column_names = [desc[0] for desc in columns]
                return [dict(zip(column_names, row)) for row in result]
            return []
            
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise
    
    async def execute(self, sql: str) -> None:
        """
        Execute a SQL statement (no results expected).
        
        Args:
            sql: SQL statement to execute
        """
        await self.ensure_connected()
        self.update_access_time()
        
        try:
            self._client.execute(sql)
        except Exception as e:
            logger.error(f"Error executing statement: {e}")
            raise
    
    async def create_table(self, table_name: str, schema: str) -> bool:
        """
        Create a table with the specified schema.
        
        Args:
            table_name: Name of the table
            schema: SQL schema definition (e.g., "id INTEGER, name VARCHAR(50)")
            
        Returns:
            True if successful, False otherwise
        """
        try:
            sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"
            await self.execute(sql)
            logger.info(f"Created table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {e}")
            return False
    
    async def drop_table(self, table_name: str) -> bool:
        """
        Drop a table from the database.
        
        Args:
            table_name: Name of the table to drop
            
        Returns:
            True if successful, False otherwise
        """
        try:
            sql = f"DROP TABLE IF EXISTS {table_name}"
            await self.execute(sql)
            logger.info(f"Dropped table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error dropping table {table_name}: {e}")
            return False
    
    async def list_tables(self) -> List[str]:
        """
        List all tables in the database.
        
        Returns:
            List of table names
        """
        try:
            result = await self.query("SHOW TABLES")
            return [row.get('name', row.get(list(row.keys())[0])) for row in result]
        except Exception as e:
            logger.error(f"Error listing tables: {e}")
            return []
    
    async def import_from_csv(self, file_path: str, table_name: str, 
                               create_table: bool = True) -> bool:
        """
        Import data from a CSV file into a table.
        
        Args:
            file_path: Path to CSV file
            table_name: Target table name
            create_table: Whether to create the table automatically
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if create_table:
                # Let DuckDB infer the schema
                sql = f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path}')"
            else:
                sql = f"INSERT INTO {table_name} SELECT * FROM read_csv_auto('{file_path}')"
            
            await self.execute(sql)
            logger.info(f"Imported data from {file_path} to {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error importing CSV: {e}")
            return False
    
    async def import_from_parquet(self, file_path: str, table_name: str,
                                   create_table: bool = True) -> bool:
        """
        Import data from a Parquet file into a table.
        
        Args:
            file_path: Path to Parquet file
            table_name: Target table name
            create_table: Whether to create the table automatically
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if create_table:
                sql = f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{file_path}')"
            else:
                sql = f"INSERT INTO {table_name} SELECT * FROM read_parquet('{file_path}')"
            
            await self.execute(sql)
            logger.info(f"Imported data from {file_path} to {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error importing Parquet: {e}")
            return False
    
    async def export_to_csv(self, table_name: str, file_path: str) -> bool:
        """
        Export a table to a CSV file.
        
        Args:
            table_name: Source table name
            file_path: Destination CSV file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            
            sql = f"COPY (SELECT * FROM {table_name}) TO '{file_path}' (HEADER, DELIMITER ',')"
            await self.execute(sql)
            logger.info(f"Exported table {table_name} to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False
    
    async def export_to_parquet(self, table_name: str, file_path: str) -> bool:
        """
        Export a table to a Parquet file.
        
        Args:
            table_name: Source table name
            file_path: Destination Parquet file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            
            sql = f"COPY (SELECT * FROM {table_name}) TO '{file_path}' (FORMAT PARQUET)"
            await self.execute(sql)
            logger.info(f"Exported table {table_name} to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting to Parquet: {e}")
            return False
    
    async def insert_data(self, table_name: str, data: List[Dict[str, Any]]) -> bool:
        """
        Insert data into a table.
        
        Args:
            table_name: Target table name
            data: List of dictionaries containing data to insert
            
        Returns:
            True if successful, False otherwise
        """
        if not data:
            return True
        
        try:
            # Extract column names from first row
            columns = list(data[0].keys())
            
            # Build INSERT statements
            for row in data:
                values = ', '.join([self._format_value(value) for value in row.values()])
                sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({values})"
                await self.execute(sql)
            
            logger.info(f"Inserted {len(data)} rows into {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error inserting data: {e}")
            return False
    
    def _format_value(self, value: Any) -> str:
        """
        Format a value for SQL insertion.
        
        Args:
            value: Value to format
            
        Returns:
            Formatted value as string
        """
        if value is None:
            return 'NULL'
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"  # Escape single quotes
        if isinstance(value, bool):
            return 'TRUE' if value else 'FALSE'
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)
    
    async def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get information about a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table information
        """
        try:
            # Get table schema
            schema_result = await self.query(f"DESCRIBE {table_name}")
            
            # Get row count
            count_result = await self.query(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = count_result[0]['count'] if count_result else 0
            
            return {
                'table_name': table_name,
                'schema': schema_result,
                'row_count': row_count
            }
        except Exception as e:
            logger.error(f"Error getting table info: {e}")
            return {}
