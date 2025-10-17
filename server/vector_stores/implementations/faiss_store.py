"""
FAISS store implementation for vector operations.
"""

import logging
import os
import json
from typing import List, Dict, Any, Optional
import uuid

try:
    import faiss
    import numpy as np
except ImportError:
    raise ImportError("faiss-cpu and numpy are required for FaissStore. Please install with 'pip install faiss-cpu numpy'")

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)

class FaissStore(BaseVectorStore):
    """
    FAISS store implementation for vector operations.
    This store is file-based and saves the index and metadata to disk.
    """
    
    def __init__(self, config: StoreConfig):
        super().__init__(config)
        
        self.persist_directory = self.config.connection_params.get('persist_directory', './faiss_db')
        self.embedding_dim = self.config.connection_params.get('dimension', 768) # Should be set by embedding provider
        
        self.index_path = os.path.join(self.persist_directory, 'faiss.index')
        self.metadata_path = os.path.join(self.persist_directory, 'metadata.json')
        
        self._index = None
        self._metadata: Dict[str, Dict[str, Any]] = {} # id -> {metadata, index_pos}
        
        if not os.path.exists(self.persist_directory):
            os.makedirs(self.persist_directory)

    async def connect(self) -> bool:
        if self.status == StoreStatus.CONNECTED:
            return True
        self.status = StoreStatus.CONNECTING
        try:
            self._load_index()
            self._load_metadata()
            self.status = StoreStatus.CONNECTED
            logger.info(f"FaissStore '{self.config.name}' connected and loaded from '{self.persist_directory}'.")
            return True
        except Exception as e:
            logger.error(f"Error connecting to FaissStore: {e}")
            self.status = StoreStatus.ERROR
            return False

    async def disconnect(self) -> None:
        if self.status == StoreStatus.CONNECTED:
            self._save_index()
            self._save_metadata()
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"FaissStore '{self.config.name}' disconnected and saved to '{self.persist_directory}'.")

    async def health_check(self) -> bool:
        return self._index is not None

    def _load_index(self):
        if os.path.exists(self.index_path):
            self._index = faiss.read_index(self.index_path)
            logger.info(f"Loaded FAISS index from {self.index_path}. Index size: {self._index.ntotal}")
        else:
            self._index = faiss.IndexIDMap(faiss.IndexFlatL2(self.embedding_dim))
            logger.info("Created new FAISS index.")

    def _save_index(self):
        if self._index:
            faiss.write_index(self._index, self.index_path)
            logger.info(f"Saved FAISS index to {self.index_path}")

    def _load_metadata(self):
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, 'r') as f:
                self._metadata = json.load(f)
            logger.info(f"Loaded metadata from {self.metadata_path}")
        else:
            self._metadata = {}
            logger.info("Created new metadata store.")

    def _save_metadata(self):
        with open(self.metadata_path, 'w') as f:
            json.dump(self._metadata, f)
        logger.info(f"Saved metadata to {self.metadata_path}")

    async def add_vectors(self, vectors: List[List[float]], ids: List[str], metadata: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None) -> bool:
        if not vectors:
            return True
        
        np_vectors = np.array(vectors, dtype=np.float32)
        
        # FAISS requires integer IDs for IndexIDMap
        int_ids = [abs(hash(id_)) % (2**63 - 1) for id_ in ids]
        
        self._index.add_with_ids(np_vectors, np.array(int_ids))
        
        for i, id_str in enumerate(ids):
            self._metadata[id_str] = {
                "metadata": metadata[i] if metadata and i < len(metadata) else {},
                "int_id": int_ids[i]
            }
        return True

    async def search_vectors(self, query_vector: List[float], limit: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self._index.ntotal == 0:
            return []
            
        np_query = np.array([query_vector], dtype=np.float32)
        distances, int_indices = self._index.search(np_query, limit)
        
        int_id_to_str_id = {v['int_id']: k for k, v in self._metadata.items()}
        
        results = []
        for i, int_id in enumerate(int_indices[0]):
            if int_id in int_id_to_str_id:
                str_id = int_id_to_str_id[int_id]
                meta = self._metadata[str_id]
                results.append({
                    "id": str_id,
                    "score": 1.0 - distances[0][i],
                    "metadata": meta["metadata"]
                })
        return results

    async def get_vector(self, vector_id: str, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if vector_id in self._metadata:
            int_id = self._metadata[vector_id]["int_id"]
            vector = self._index.reconstruct(int_id)
            return {"id": vector_id, "vector": vector.tolist(), "metadata": self._metadata[vector_id]["metadata"]}
        return None

    async def update_vector(self, vector_id: str, vector: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None, collection_name: Optional[str] = None) -> bool:
        logger.warning("FAISS does not support efficient updates. Re-adding the vector.")
        await self.delete_vector(vector_id)
        
        if vector is None:
            logger.error("Updating metadata without providing a vector is not supported in this FAISS implementation.")
            return False

        return await self.add_vectors([vector], [vector_id], [metadata] if metadata else None)

    async def delete_vector(self, vector_id: str, collection_name: Optional[str] = None) -> bool:
        if vector_id in self._metadata:
            int_id = self._metadata[vector_id]["int_id"]
            self._index.remove_ids(np.array([int_id]))
            del self._metadata[vector_id]
            return True
        return False

    async def create_collection(self, collection_name: str, dimension: int, **kwargs) -> bool:
        logger.info("FAISS store uses a single index per instance. Collection creation is not applicable.")
        if dimension != self.embedding_dim:
            logger.warning(f"Dimension mismatch. Expected {self.embedding_dim}, got {dimension}. This may cause issues.")
        return True

    async def delete_collection(self, collection_name: str) -> bool:
        if os.path.exists(self.index_path):
            os.remove(self.index_path)
        if os.path.exists(self.metadata_path):
            os.remove(self.metadata_path)
        self._index = faiss.IndexIDMap(faiss.IndexFlatL2(self.embedding_dim))
        self._metadata = {}
        logger.info("Cleared FAISS index and metadata.")
        return True

    async def list_collections(self) -> List[str]:
        return ["default"]

    async def collection_exists(self, collection_name: str) -> bool:
        return collection_name == "default"

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        return {
            "name": "default",
            "count": self._index.ntotal,
            "dimension": self.embedding_dim,
        }
