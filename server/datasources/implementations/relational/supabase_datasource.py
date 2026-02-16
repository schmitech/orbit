"""
Supabase Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class SupabaseDatasource(BaseDatasource):
    """Supabase database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'supabase'
    
    async def initialize(self) -> None:
        """Initialize the Supabase database connection."""
        supabase_config = self.config.get('datasources', {}).get('supabase', {})
        
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError:
            logger.warning("psycopg2 not available. Install with: pip install psycopg2-binary")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = supabase_config.get('host', 'localhost')
        port = supabase_config.get('port', 5432)
        database = supabase_config.get('database', 'postgres')
        username = supabase_config.get('username', 'postgres')
        password = supabase_config.get('password', '')
        sslmode = supabase_config.get('sslmode', 'require')  # Supabase requires SSL
        
        try:
            logger.info(f"Initializing Supabase connection to {host}:{port}/{database}")
            
            # Create connection
            self._client = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                sslmode=sslmode,
                cursor_factory=RealDictCursor  # Use dict cursor by default
            )
            
            # Test the connection
            cursor = self._client.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            
            if version:
                logger.info(f"Supabase connection successful: {version['version']}")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to connect to Supabase database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the Supabase connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Supabase health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the Supabase connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            logger.info("Supabase connection closed")
