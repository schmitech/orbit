"""
MongoDB Datasource Implementation
"""

from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource


class MongoDBDatasource(BaseDatasource):
    """MongoDB document database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'mongodb'
    
    async def initialize(self) -> None:
        """Initialize the MongoDB client."""
        mongodb_config = self.config.get('datasources', {}).get('mongodb', {})
        
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            self.logger.warning("motor not available. Install with: pip install motor")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = mongodb_config.get('host', 'localhost')
        port = mongodb_config.get('port', 27017)
        database = mongodb_config.get('database', 'orbit')
        username = mongodb_config.get('username')
        password = mongodb_config.get('password')
        
        try:
            # Build connection URI
            if username and password:
                uri = f"mongodb://{username}:{password}@{host}:{port}/{database}"
            else:
                uri = f"mongodb://{host}:{port}/{database}"
            
            self.logger.info(f"Initializing MongoDB connection to {host}:{port}/{database}")
            
            # Create client
            self._client = AsyncIOMotorClient(uri)
            
            # Test the connection
            await self._client.admin.command('ping')
            
            self.logger.info("MongoDB connection successful")
            self._initialized = True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to MongoDB: {str(e)}")
            self.logger.error(f"Connection details: {host}:{port}/{database}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the MongoDB connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            await self._client.admin.command('ping')
            return True
        except Exception as e:
            self.logger.error(f"MongoDB health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            self.logger.info("MongoDB connection closed")
