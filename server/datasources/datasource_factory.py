"""
Datasource Factory Module

This module provides functionality for initializing various datasource clients
based on the configured provider. It supports multiple datasource types including
ChromaDB, SQLite, PostgreSQL, and Milvus.
"""

import sqlite3
import os
from pathlib import Path
from typing import Any, Dict, Optional
import chromadb


class DatasourceFactory:
    """
    Factory class for creating datasource clients based on configuration.
    
    This class handles the initialization of different types of datasource clients
    including ChromaDB, SQLite, PostgreSQL, and Milvus. It provides a unified
    interface for creating clients while handling provider-specific configuration.
    """
    
    def __init__(self, config: Dict[str, Any], logger):
        """
        Initialize the DatasourceFactory.
        
        Args:
            config: The application configuration dictionary
            logger: Logger instance for logging operations
        """
        self.config = config
        self.logger = logger
    
    def initialize_datasource_client(self, provider: str) -> Any:
        """
        Initialize a datasource client based on the selected provider.
        
        Args:
            provider: The datasource provider to initialize
            
        Returns:
            An initialized datasource client
            
        Raises:
            Exception: If the datasource client fails to initialize
        """
        if provider == 'sqlite':
            return self._initialize_sqlite_client()
        elif provider == 'postgres':
            return self._initialize_postgres_client()
        elif provider == 'milvus':
            return self._initialize_milvus_client()
        else:
            self.logger.warning(f"Unknown datasource provider: {provider}, falling back to ChromaDB")
            return self._initialize_chroma_client()
    
    def _initialize_sqlite_client(self) -> Optional[sqlite3.Connection]:
        """
        Initialize a SQLite database client.
        
        Returns:
            SQLite connection object or None if initialization fails
        """
        sqlite_config = self.config['datasources']['sqlite']
        db_path = sqlite_config.get('db_path', 'sqlite_db.db')
        self.logger.info(f"Initializing SQLite connection to {db_path}")
        
        try:
            return sqlite3.connect(db_path)
        except Exception as e:
            self.logger.error(f"Failed to connect to SQLite database: {str(e)}")
            return None
    
    def _initialize_postgres_client(self) -> Optional[Any]:
        """
        Initialize a PostgreSQL database client.
        
        Returns:
            PostgreSQL client object or None (not yet implemented)
        """
        postgres_conf = self.config['datasources']['postgres']
        self.logger.info("PostgreSQL datasource not yet implemented")
        return None
    
    def _initialize_milvus_client(self) -> Optional[Any]:
        """
        Initialize a Milvus vector database client.
        
        Returns:
            Milvus client object or None (not yet implemented)
        """
        milvus_conf = self.config['datasources']['milvus']
        self.logger.info("Milvus datasource not yet implemented")
        return None
    
    def _initialize_chroma_client(self) -> chromadb.Client:
        """
        Initialize a ChromaDB client (default fallback).
        
        Returns:
            ChromaDB client object (PersistentClient or HttpClient)
        """
        chroma_conf = self.config['datasources']['chroma']
        use_local = chroma_conf.get('use_local', False)
        
        if use_local:
            return self._initialize_local_chroma_client(chroma_conf)
        else:
            return self._initialize_remote_chroma_client(chroma_conf)
    
    def _initialize_local_chroma_client(self, chroma_conf: Dict[str, Any]) -> chromadb.PersistentClient:
        """
        Initialize a local ChromaDB PersistentClient.
        
        Args:
            chroma_conf: ChromaDB configuration dictionary
            
        Returns:
            ChromaDB PersistentClient for local filesystem access
        """
        db_path = chroma_conf.get('db_path', '../localdb_db')
        db_path = Path(db_path).resolve()
        
        # Ensure the directory exists
        os.makedirs(db_path, exist_ok=True)
        
        self.logger.info(f"Using local ChromaDB at path: {db_path}")
        return chromadb.PersistentClient(path=str(db_path))
    
    def _initialize_remote_chroma_client(self, chroma_conf: Dict[str, Any]) -> chromadb.HttpClient:
        """
        Initialize a remote ChromaDB HttpClient.
        
        Args:
            chroma_conf: ChromaDB configuration dictionary
            
        Returns:
            ChromaDB HttpClient for remote server access
        """
        host = chroma_conf['host']
        port = int(chroma_conf['port'])
        
        self.logger.info(f"Connecting to ChromaDB at {host}:{port}...")
        return chromadb.HttpClient(host=host, port=port) 