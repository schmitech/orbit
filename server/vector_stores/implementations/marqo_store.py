import logging
import warnings
from typing import Dict, Any, Optional, List

# Suppress Pydantic deprecation warnings from Marqo
warnings.filterwarnings("ignore", category=DeprecationWarning, module="marqo.*")

try:
    import marqo
except ImportError:
    raise ImportError("Marqo not installed. Please install with 'pip install marqo'")

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)

class MarqoStore(BaseVectorStore):
    def __init__(self, config: StoreConfig):
        super().__init__(config)
        self.url = self.config.connection_params.get("url", "http://localhost:8882")
        self.model = self.config.connection_params.get("model", "hf/all_datasets_v4_MiniLM-L6")
        self._client = None

    async def connect(self) -> bool:
        if self.status == StoreStatus.CONNECTED:
            return True
        self.status = StoreStatus.CONNECTING
        try:
            self._client = marqo.Client(url=self.url)
            self.status = StoreStatus.CONNECTED
            logger.info(f"Marqo store '{self.config.name}' connected successfully.")
            return True
        except Exception as e:
            self.status = StoreStatus.ERROR
            logger.error(f"Error connecting to Marqo: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            self._client = None
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"Marqo store '{self.config.name}' disconnected.")

    async def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            return self._client.health()
        except Exception:
            return False

    async def add_vectors(self, vectors: List[List[float]], ids: List[str], metadata: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        
        documents = []
        for i, id_ in enumerate(ids):
            doc = {"_id": id_}
            if metadata and i < len(metadata):
                doc.update(metadata[i])
            documents.append(doc)

        tensor_fields = list(metadata[0].keys()) if metadata else []

        try:
            self._client.index(collection_name).add_documents(documents, tensor_fields=tensor_fields)
            return True
        except Exception as e:
            logger.error(f"Error adding documents to Marqo: {e}")
            return False

    async def search_vectors(self, query_vector: List[float], limit: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError("MarqoStore does not support search by vector directly.")

    async def create_collection(self, collection_name: str, dimension: int, **kwargs) -> bool:
        try:
            self._client.create_index(collection_name, model=self.model)
            return True
        except Exception as e:
            logger.info(f"Marqo index {collection_name} may already exist or error: {e}")
            return True

    async def get_vector(self, vector_id: str, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection
        try:
            doc = self._client.index(collection_name).get_document(vector_id)
            return {"id": vector_id, "metadata": doc}
        except Exception:
            return None

    async def update_vector(self, vector_id: str, vector: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        doc = {"_id": vector_id}
        if metadata:
            doc.update(metadata)
        
        tensor_fields = list(metadata.keys()) if metadata else []

        try:
            self._client.index(collection_name).add_documents([doc], tensor_fields=tensor_fields)
            return True
        except Exception as e:
            logger.error(f"Error updating document in Marqo: {e}")
            return False

    async def delete_vector(self, vector_id: str, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection
        try:
            self._client.index(collection_name).delete_documents([vector_id])
            return True
        except Exception as e:
            logger.error(f"Error deleting document from Marqo: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        try:
            self._client.delete_index(collection_name)
            return True
        except Exception as e:
            logger.error(f"Error deleting Marqo index: {e}")
            return False

    async def list_collections(self) -> List[str]:
        return [index.index_name for index in self._client.get_indexes()]

    async def collection_exists(self, collection_name: str) -> bool:
        try:
            self._client.index(collection_name).get_stats()
            return True
        except Exception:
            return False

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        try:
            stats = self._client.index(collection_name).get_stats()
            return {"name": collection_name, "count": stats['numberOfDocuments']}
        except Exception as e:
            logger.error(f"Error getting collection info from Marqo: {e}")
            return {}
