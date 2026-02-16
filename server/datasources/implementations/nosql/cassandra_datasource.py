"""
Apache Cassandra Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class CassandraDatasource(BaseDatasource):
    """Apache Cassandra database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'cassandra'
    
    async def initialize(self) -> None:
        """Initialize the Cassandra client."""
        cassandra_config = self.config.get('datasources', {}).get('cassandra', {})
        
        try:
            from cassandra.cluster import Cluster
            from cassandra.auth import PlainTextAuthProvider
        except ImportError:
            logger.warning("cassandra-driver not available. Install with: pip install cassandra-driver")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        contact_points = cassandra_config.get('contact_points', 'localhost')
        if isinstance(contact_points, str):
            contact_points = [cp.strip() for cp in contact_points.split(',')]
        
        port = cassandra_config.get('port', 9042)
        keyspace = cassandra_config.get('keyspace', 'orbit')
        username = cassandra_config.get('username')
        password = cassandra_config.get('password')
        
        try:
            logger.info(f"Initializing Cassandra connection to {contact_points}:{port}/{keyspace}")
            
            # Create authentication provider if credentials provided
            auth_provider = None
            if username and password:
                auth_provider = PlainTextAuthProvider(username=username, password=password)
            
            # Create cluster
            cluster = Cluster(
                contact_points=contact_points,
                port=port,
                auth_provider=auth_provider
            )
            
            # Create session
            self._client = cluster.connect(keyspace)
            
            # Test the connection
            result = self._client.execute("SELECT now() FROM system.local")
            result.one()
            
            logger.info("Cassandra connection successful")
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to connect to Cassandra: {str(e)}")
            logger.error(f"Connection details: {contact_points}:{port}/{keyspace}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the Cassandra connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            result = self._client.execute("SELECT now() FROM system.local")
            result.one()
            return True
        except Exception as e:
            logger.error(f"Cassandra health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the Cassandra connection."""
        if self._client:
            self._client.shutdown()
            self._client = None
            self._initialized = False
            logger.info("Cassandra connection closed")
