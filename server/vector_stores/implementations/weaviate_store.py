import logging
from typing import Dict, Any, Optional, List
import uuid

try:
    import weaviate
    import weaviate.classes as wvc
except ImportError:
    raise ImportError("Weaviate not installed. Please install with 'pip install weaviate-client'")

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)

class WeaviateStore(BaseVectorStore):
    def __init__(self, config: StoreConfig):
        super().__init__(config)
        self.weaviate_url = self.config.connection_params.get("url")
        self.weaviate_api_key = self.config.connection_params.get("api_key")
        self.weaviate_port = self.config.connection_params.get("port")
        self.weaviate_grpc_port = self.config.connection_params.get("grpc_port", 50051)
        self._client = None

    async def connect(self) -> bool:
        if self.status == StoreStatus.CONNECTED:
            return True
        self.status = StoreStatus.CONNECTING
        try:
            if self.weaviate_api_key:
                self._client = weaviate.connect_to_wcs(
                    cluster_url=self.weaviate_url,
                    auth_credentials=weaviate.auth.AuthApiKey(self.weaviate_api_key),
                )
            else:
                self._client = weaviate.connect_to_local(
                    port=self.weaviate_port,
                    grpc_port=self.weaviate_grpc_port,
                )
            self.status = StoreStatus.CONNECTED
            logger.info(f"Weaviate store '{self.config.name}' connected successfully.")
            return True
        except Exception as e:
            self.status = StoreStatus.ERROR
            logger.error(f"Error connecting to Weaviate: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"Weaviate store '{self.config.name}' disconnected.")

    async def health_check(self) -> bool:
        if not self._client:
            return False
        return self._client.is_ready()

    async def add_vectors(self, vectors: List[List[float]], ids: List[str], metadata: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        collection = self._client.collections.get(collection_name)
        
        data_objects = []
        for i, id_ in enumerate(ids):
            props = metadata[i] if metadata and i < len(metadata) else {}
            data_objects.append(wvc.data.DataObject(properties=props, vector=vectors[i], uuid=uuid.UUID(id_)))
        
        try:
            collection.data.insert_many(data_objects)
            return True
        except Exception as e:
            logger.error(f"Error adding vectors to Weaviate: {e}")
            return False

    async def search_vectors(self, query_vector: List[float], limit: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection
        collection = self._client.collections.get(collection_name)
        
        query_results = collection.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )
        
        results = []
        for item in query_results.objects:
            results.append({
                "id": str(item.uuid),
                "score": 1 - item.metadata.distance,
                "metadata": item.properties
            })
        return results

    async def get_vector(self, vector_id: str, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection
        collection = self._client.collections.get(collection_name)
        
        try:
            item = collection.query.fetch_object_by_id(uuid.UUID(vector_id), include_vector=True)
            return {"id": str(item.uuid), "vector": item.vector, "metadata": item.properties}
        except Exception:
            return None

    async def update_vector(self, vector_id: str, vector: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        collection = self._client.collections.get(collection_name)
        
        try:
            if vector and metadata:
                collection.data.update(uuid.UUID(vector_id), properties=metadata, vector=vector)
            elif vector:
                collection.data.update(uuid.UUID(vector_id), vector=vector)
            elif metadata:
                collection.data.update(uuid.UUID(vector_id), properties=metadata)
            return True
        except Exception as e:
            logger.error(f"Error updating vector in Weaviate: {e}")
            return False

    async def delete_vector(self, vector_id: str, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        collection = self._client.collections.get(collection_name)
        try:
            collection.data.delete_by_id(uuid.UUID(vector_id))
            return True
        except Exception as e:
            logger.error(f"Error deleting vector from Weaviate: {e}")
            return False

    async def create_collection(self, collection_name: str, dimension: int, **kwargs) -> bool:
        if self._client.collections.exists(collection_name):
            return True
        try:
            self._client.collections.create(name=collection_name)
            return True
        except Exception as e:
            logger.error(f"Error creating Weaviate collection: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        try:
            self._client.collections.delete(collection_name)
            return True
        except Exception as e:
            logger.error(f"Error deleting Weaviate collection: {e}")
            return False

    async def list_collections(self) -> List[str]:
        return [col.name for col in self._client.collections.list_all()]

    async def collection_exists(self, collection_name: str) -> bool:
        return self._client.collections.exists(collection_name)

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        return {"name": collection_name}
