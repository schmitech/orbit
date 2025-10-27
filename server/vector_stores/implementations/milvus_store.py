import logging
from typing import Dict, Any, Optional, List

try:
    from pymilvus import MilvusClient, DataType
except ImportError:
    raise ImportError("Milvus not installed. Please install with 'pip install pymilvus'")

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)

class MilvusStore(BaseVectorStore):
    def __init__(self, config: StoreConfig):
        super().__init__(config)
        self.uri = self.config.connection_params.get("uri", "./milvus.db")
        self.embedding_dim = self.config.connection_params.get("dimension", 768)
        self._client = None

    async def connect(self) -> bool:
        if self.status == StoreStatus.CONNECTED:
            return True
        self.status = StoreStatus.CONNECTING
        try:
            self._client = MilvusClient(uri=self.uri)
            self.status = StoreStatus.CONNECTED
            logger.info(f"Milvus store '{self.config.name}' connected successfully.")
            return True
        except Exception as e:
            self.status = StoreStatus.ERROR
            logger.error(f"Error connecting to Milvus: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            self._client = None
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"Milvus store '{self.config.name}' disconnected.")

    async def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.list_collections()
            return True
        except Exception:
            return False

    async def add_vectors(self, vectors: List[List[float]], ids: List[str], metadata: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        
        data = []
        for i, id_ in enumerate(ids):
            entry = {"id": id_, "vector": vectors[i]}
            if metadata and i < len(metadata):
                entry.update(metadata[i])
            data.append(entry)
            
        try:
            self._client.insert(collection_name=collection_name, data=data)
            return True
        except Exception as e:
            logger.error(f"Error adding vectors to Milvus: {e}")
            return False

    async def search_vectors(self, query_vector: List[float], limit: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection
        
        filter_expr = ""
        if filter_metadata:
            filter_expr = " and ".join([f'{k} == "{v}"' for k, v in filter_metadata.items()])

        try:
            res = self._client.search(
                collection_name=collection_name,
                data=[query_vector],
                limit=limit,
                filter=filter_expr,
                output_fields=["*"]
            )
            
            results = []
            for hit in res[0]:
                payload = {k: v for k, v in hit['entity'].items() if k not in ['id', 'vector']}
                results.append({
                    "id": hit['entity']['id'],
                    "score": hit['distance'],
                    "metadata": payload
                })
            return results
        except Exception as e:
            logger.error(f"Error searching vectors in Milvus: {e}")
            return []

    async def create_collection(self, collection_name: str, dimension: int, **kwargs) -> bool:
        if self._client.has_collection(collection_name):
            return True
        
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=65535)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dimension)
        
        index_params = self._client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="L2")
        
        try:
            self._client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params
            )
            return True
        except Exception as e:
            logger.error(f"Error creating Milvus collection: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        try:
            self._client.drop_collection(collection_name)
            return True
        except Exception as e:
            logger.error(f"Error deleting Milvus collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        return self._client.list_collections()

    async def collection_exists(self, collection_name: str) -> bool:
        return self._client.has_collection(collection_name)

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        try:
            stats = self._client.get_collection_stats(collection_name)
            return {"name": collection_name, "count": stats['row_count']}
        except Exception as e:
            logger.error(f"Error getting collection info from Milvus: {e}")
            return {}

    async def get_vector(self, vector_id: str, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        logger.warning("get_vector is not efficiently implemented for MilvusStore.")
        return None

    async def update_vector(self, vector_id: str, vector: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None, collection_name: Optional[str] = None) -> bool:
        logger.warning("update_vector is not efficiently implemented for MilvusStore.")
        return False

    async def delete_vector(self, vector_id: str, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        try:
            self._client.delete(collection_name=collection_name, ids=[vector_id])
            return True
        except Exception as e:
            logger.error(f"Error deleting vector from Milvus: {e}")
            return False