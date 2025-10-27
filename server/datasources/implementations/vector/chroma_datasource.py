"""
ChromaDB Datasource Implementation
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource


class ChromaDBDatasource(BaseDatasource):
    """ChromaDB vector database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'chroma'
    
    async def initialize(self) -> None:
        """Initialize the ChromaDB client."""
        try:
            import chromadb
        except ImportError:
            self.logger.error("chromadb not available. Install with: pip install chromadb")
            raise
            
        chroma_config = self.config.get('datasources', {}).get('chroma', {})
        use_local = chroma_config.get('use_local', False)
        
        if use_local:
            self._client = self._initialize_local_client(chroma_config)
        else:
            self._client = self._initialize_remote_client(chroma_config)
            
        self._initialized = True
        self.logger.info("ChromaDB client initialized successfully")
    
    def _initialize_local_client(self, chroma_config: Dict[str, Any]):
        """Initialize a local ChromaDB PersistentClient."""
        import chromadb
        
        db_path = chroma_config.get('db_path', '../localdb_db')
        db_path = Path(db_path).resolve()
        
        # Ensure the directory exists
        os.makedirs(db_path, exist_ok=True)
        
        self.logger.info(f"Using local ChromaDB at path: {db_path}")
        return chromadb.PersistentClient(path=str(db_path))
    
    def _initialize_remote_client(self, chroma_config: Dict[str, Any]):
        """Initialize a remote ChromaDB HttpClient."""
        import chromadb
        
        host = chroma_config['host']
        port = int(chroma_config['port'])
        
        self.logger.info(f"Connecting to ChromaDB at {host}:{port}...")
        return chromadb.HttpClient(host=host, port=port)
    
    async def health_check(self) -> bool:
        """Perform a health check on the ChromaDB connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            # Try to get version info
            version = self._client.get_version()
            return version is not None
        except Exception as e:
            self.logger.error(f"ChromaDB health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the ChromaDB connection."""
        if self._client:
            # ChromaDB clients don't have explicit close methods
            self._client = None
            self._initialized = False
            self.logger.info("ChromaDB client closed")
