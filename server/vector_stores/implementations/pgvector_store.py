import logging
from typing import Dict, Any, Optional, List
import json

try:
    import psycopg2
    from pgvector.psycopg2 import register_vector
except ImportError:
    raise ImportError("pgvector not installed. Please install with 'pip install pgvector psycopg2-binary'")

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)

class PgvectorStore(BaseVectorStore):
    def __init__(self, config: StoreConfig):
        super().__init__(config)
        self.connection_string = self.config.connection_params.get("connection_string")
        self._conn = None
        self._cursor = None

    async def connect(self) -> bool:
        if self.status == StoreStatus.CONNECTED:
            return True
        self.status = StoreStatus.CONNECTING
        try:
            self._conn = psycopg2.connect(self.connection_string)
            register_vector(self._conn)
            self._cursor = self._conn.cursor()
            self.status = StoreStatus.CONNECTED
            logger.info(f"Pgvector store '{self.config.name}' connected successfully.")
            return True
        except Exception as e:
            self.status = StoreStatus.ERROR
            logger.error(f"Error connecting to Pgvector: {e}")
            return False

    async def disconnect(self) -> None:
        if self._conn:
            self._cursor.close()
            self._conn.close()
            self._conn = None
            self._cursor = None
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"Pgvector store '{self.config.name}' disconnected.")

    async def health_check(self) -> bool:
        if not self._conn or self._conn.closed:
            return False
        try:
            self._cursor.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def add_vectors(self, vectors: List[List[float]], ids: List[str], metadata: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        
        try:
            for i, id_ in enumerate(ids):
                meta = metadata[i] if metadata and i < len(metadata) else {}
                self._cursor.execute(
                    f"INSERT INTO {collection_name} (id, embedding, metadata) VALUES (%s, %s, %s)",
                    (id_, vectors[i], json.dumps(meta))
                )
            self._conn.commit()
            return True
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Error adding vectors to Pgvector: {e}")
            return False

    async def search_vectors(self, query_vector: List[float], limit: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection
        
        try:
            self._cursor.execute(
                f"SELECT id, metadata, 1 - (embedding <-> %s) AS score FROM {collection_name} ORDER BY embedding <-> %s LIMIT %s",
                (query_vector, query_vector, limit)
            )
            results = self._cursor.fetchall()
            return [{"id": row[0], "metadata": row[1], "score": row[2]} for row in results]
        except Exception as e:
            logger.error(f"Error searching vectors in Pgvector: {e}")
            return []

    async def create_collection(self, collection_name: str, dimension: int, **kwargs) -> bool:
        try:
            self._cursor.execute(f"CREATE TABLE IF NOT EXISTS {collection_name} (id VARCHAR PRIMARY KEY, embedding vector({dimension}), metadata JSONB)")
            self._conn.commit()
            return True
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Error creating Pgvector collection: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        try:
            self._cursor.execute(f"DROP TABLE IF EXISTS {collection_name}")
            self._conn.commit()
            return True
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Error deleting Pgvector collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        try:
            self._cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            return [row[0] for row in self._cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error listing Pgvector collections: {e}")
            return []

    async def collection_exists(self, collection_name: str) -> bool:
        try:
            self._cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (collection_name,))
            return self._cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error checking if Pgvector collection exists: {e}")
            return False

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        try:
            self._cursor.execute(f"SELECT COUNT(*) FROM {collection_name}")
            count = self._cursor.fetchone()[0]
            return {"name": collection_name, "count": count}
        except Exception as e:
            logger.error(f"Error getting Pgvector collection info: {e}")
            return {}

    async def get_vector(self, vector_id: str, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection
        try:
            self._cursor.execute(f"SELECT embedding, metadata FROM {collection_name} WHERE id = %s", (vector_id,))
            res = self._cursor.fetchone()
            if res:
                return {"id": vector_id, "vector": res[0], "metadata": res[1]}
            return None
        except Exception as e:
            logger.error(f"Error getting vector from Pgvector: {e}")
            return None

    async def update_vector(self, vector_id: str, vector: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        try:
            if vector and metadata:
                self._cursor.execute(f"UPDATE {collection_name} SET embedding = %s, metadata = %s WHERE id = %s", (vector, json.dumps(metadata), vector_id))
            elif vector:
                self._cursor.execute(f"UPDATE {collection_name} SET embedding = %s WHERE id = %s", (vector, vector_id))
            elif metadata:
                self._cursor.execute(f"UPDATE {collection_name} SET metadata = %s WHERE id = %s", (json.dumps(metadata), vector_id))
            self._conn.commit()
            return True
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Error updating vector in Pgvector: {e}")
            return False

    async def delete_vector(self, vector_id: str, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        try:
            self._cursor.execute(f"DELETE FROM {collection_name} WHERE id = %s", (vector_id,))
            self._conn.commit()
            return True
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Error deleting vector from Pgvector: {e}")
            return False
