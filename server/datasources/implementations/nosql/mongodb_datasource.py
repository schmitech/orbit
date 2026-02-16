"""
MongoDB Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


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
            logger.warning("motor not available. Install with: pip install motor")
            self._client = None
            self._initialized = True
            return

        # Extract connection parameters
        database = mongodb_config.get('database', 'orbit')
        timeout = mongodb_config.get('timeout', 30)

        try:
            # Option 1: Use connection_string if provided (preferred for MongoDB Atlas)
            connection_string = mongodb_config.get('connection_string')

            if connection_string:
                logger.info(f"Initializing MongoDB using connection string to database: {database}")
                uri = connection_string
            else:
                # Option 2: Build connection string from individual parameters
                host = mongodb_config.get('host', 'localhost')
                port = mongodb_config.get('port', 27017)
                username = mongodb_config.get('username')
                password = mongodb_config.get('password')
                auth_source = mongodb_config.get('auth_source', 'admin')
                tls = mongodb_config.get('tls', False)
                retry_writes = mongodb_config.get('retry_writes', True)
                w = mongodb_config.get('w', 'majority')

                logger.info(f"Initializing MongoDB connection to {host}:{port}/{database}")

                # Build connection URI based on host format and authentication
                if "mongodb.net" in host and username and password:
                    # MongoDB Atlas with authentication
                    uri = f"mongodb+srv://{username}:{password}@{host}/{database}?retryWrites={str(retry_writes).lower()}&w={w}"
                    logger.debug("Using MongoDB Atlas connection string format")
                elif username and password:
                    # Local or remote MongoDB with authentication
                    auth_params = f"?authSource={auth_source}"
                    if tls:
                        auth_params += "&tls=true"
                    if retry_writes:
                        auth_params += f"&retryWrites=true&w={w}"
                    uri = f"mongodb://{username}:{password}@{host}:{port}/{database}{auth_params}"
                    logger.debug("Using MongoDB connection string with authentication")
                else:
                    # Local MongoDB without authentication
                    uri = f"mongodb://{host}:{port}/{database}"
                    logger.debug("Using MongoDB connection string without authentication")

            # Create client with timeout
            self._client = AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=timeout * 1000
            )

            # Test the connection
            await self._client.admin.command('ping')

            logger.info("MongoDB connection successful")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            if 'host' in locals():
                logger.error(f"Connection details: {host}:{port}/{database}")
            else:
                logger.error(f"Database: {database}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the MongoDB connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            await self._client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            logger.info("MongoDB connection closed")
