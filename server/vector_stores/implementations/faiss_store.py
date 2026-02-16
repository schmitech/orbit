"""
FAISS store implementation for vector operations.
"""

import logging
import os
import json
from typing import List, Dict, Any, Optional

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
    This store is file-based and supports multiple collections.
    Each collection has its own index and metadata file.
    """

    def __init__(self, config: StoreConfig):
        super().__init__(config)

        self.persist_directory = self.config.connection_params.get('persist_directory', './faiss_db')
        self.embedding_dim = self.config.connection_params.get('dimension', 768) # Should be set by embedding provider

        # Multi-collection support: collection_name -> {index, metadata}
        self._collections: Dict[str, Dict[str, Any]] = {}

        if not os.path.exists(self.persist_directory):
            os.makedirs(self.persist_directory)

    def _get_collection_paths(self, collection_name: str):
        """Get index and metadata paths for a collection."""
        collection_dir = os.path.join(self.persist_directory, collection_name)
        if not os.path.exists(collection_dir):
            os.makedirs(collection_dir)
        return {
            'index': os.path.join(collection_dir, 'faiss.index'),
            'metadata': os.path.join(collection_dir, 'metadata.json')
        }

    async def connect(self) -> bool:
        if self.status == StoreStatus.CONNECTED:
            return True
        self.status = StoreStatus.CONNECTING
        try:
            # Load all existing collections from disk
            self._load_all_collections()
            self.status = StoreStatus.CONNECTED
            logger.info(f"FaissStore '{self.config.name}' connected and loaded from '{self.persist_directory}'.")
            return True
        except Exception as e:
            logger.error(f"Error connecting to FaissStore: {e}")
            self.status = StoreStatus.ERROR
            return False

    async def disconnect(self) -> None:
        if self.status == StoreStatus.CONNECTED:
            # Save all collections
            self._save_all_collections()
            self.status = StoreStatus.DISCONNECTED
            logger.info(f"FaissStore '{self.config.name}' disconnected and saved to '{self.persist_directory}'.")

    async def health_check(self) -> bool:
        return self.status == StoreStatus.CONNECTED

    def _load_all_collections(self):
        """Load all collections from persist directory."""
        if not os.path.exists(self.persist_directory):
            return

        for collection_name in os.listdir(self.persist_directory):
            collection_path = os.path.join(self.persist_directory, collection_name)
            if os.path.isdir(collection_path):
                self._load_collection(collection_name)

    def _load_collection(self, collection_name: str):
        """Load a specific collection's index and metadata."""
        paths = self._get_collection_paths(collection_name)

        index = None
        metadata = {}

        if os.path.exists(paths['index']):
            index = faiss.read_index(paths['index'])
            logger.info(f"Loaded FAISS index for collection '{collection_name}'. Size: {index.ntotal}")
        else:
            index = faiss.IndexIDMap(faiss.IndexFlatL2(self.embedding_dim))
            logger.debug(f"Created new FAISS index for collection '{collection_name}'.")

        if os.path.exists(paths['metadata']):
            with open(paths['metadata'], 'r') as f:
                metadata = json.load(f)
            logger.info(f"Loaded metadata for collection '{collection_name}'")
        else:
            metadata = {}
            logger.debug(f"Created new metadata store for collection '{collection_name}'.")

        self._collections[collection_name] = {
            'index': index,
            'metadata': metadata
        }

    def _save_all_collections(self):
        """Save all loaded collections."""
        for collection_name in self._collections.keys():
            self._save_collection(collection_name)

    def _save_collection(self, collection_name: str):
        """Save a specific collection's index and metadata."""
        if collection_name not in self._collections:
            return

        paths = self._get_collection_paths(collection_name)
        collection = self._collections[collection_name]

        if collection['index']:
            faiss.write_index(collection['index'], paths['index'])
            logger.debug(f"Saved FAISS index for collection '{collection_name}'")

        with open(paths['metadata'], 'w') as f:
            json.dump(collection['metadata'], f)
        logger.debug(f"Saved metadata for collection '{collection_name}'")

    async def add_vectors(self, vectors: List[List[float]], ids: List[str], metadata: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None, documents: Optional[List[str]] = None) -> bool:
        if not vectors:
            return True

        collection_name = collection_name or self._default_collection

        # Ensure collection exists
        if collection_name not in self._collections:
            await self.create_collection(collection_name, len(vectors[0]) if vectors else self.embedding_dim)

        collection = self._collections[collection_name]

        np_vectors = np.array(vectors, dtype=np.float32)

        # FAISS requires integer IDs for IndexIDMap
        int_ids = [abs(hash(id_)) % (2**63 - 1) for id_ in ids]

        collection['index'].add_with_ids(np_vectors, np.array(int_ids))

        for i, id_str in enumerate(ids):
            # Prepare metadata with text support
            vector_metadata = metadata[i].copy() if metadata and i < len(metadata) else {}

            # Add document text if provided
            if documents and i < len(documents):
                vector_metadata["text"] = documents[i]
                vector_metadata["content"] = documents[i]
            elif "text" not in vector_metadata and "content" not in vector_metadata:
                # Try to extract from existing metadata
                text = vector_metadata.get('text') or vector_metadata.get('content') or vector_metadata.get('document')
                if text:
                    vector_metadata["text"] = text
                    vector_metadata["content"] = text

            collection['metadata'][id_str] = {
                "metadata": vector_metadata,
                "int_id": int_ids[i]
            }

        logger.debug(f"Added {len(vectors)} vectors to FAISS collection '{collection_name}'")
        return True

    async def search_vectors(self, query_vector: List[float], limit: int = 10, collection_name: Optional[str] = None, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection

        # Check if collection exists
        if collection_name not in self._collections:
            logger.warning(f"Collection '{collection_name}' not found")
            return []

        collection = self._collections[collection_name]

        if collection['index'].ntotal == 0:
            return []

        np_query = np.array([query_vector], dtype=np.float32)
        distances, int_indices = collection['index'].search(np_query, limit)

        int_id_to_str_id = {v['int_id']: k for k, v in collection['metadata'].items()}

        results = []
        for i, int_id in enumerate(int_indices[0]):
            if int_id in int_id_to_str_id:
                str_id = int_id_to_str_id[int_id]
                meta = collection['metadata'][str_id]
                metadata = meta["metadata"]

                # Extract text for file chunking support
                text = metadata.get('text', metadata.get('content', ''))

                # Client-side metadata filtering (FAISS doesn't support server-side filtering)
                if filter_metadata:
                    matches = all(metadata.get(k) == v for k, v in filter_metadata.items())
                    if not matches:
                        continue

                results.append({
                    "id": str_id,
                    "score": max(0, 1.0 - (distances[0][i] / 2.0)),  # Normalize L2 distance to [0, 1]
                    "metadata": metadata,
                    "text": text,
                    "content": text
                })

        return results

    async def get_vector(self, vector_id: str, collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        collection_name = collection_name or self._default_collection

        if collection_name not in self._collections:
            return None

        collection = self._collections[collection_name]

        if vector_id in collection['metadata']:
            int_id = collection['metadata'][vector_id]["int_id"]
            vector = collection['index'].reconstruct(int_id)
            return {
                "id": vector_id,
                "vector": vector.tolist(),
                "metadata": collection['metadata'][vector_id]["metadata"]
            }
        return None

    async def update_vector(self, vector_id: str, vector: Optional[List[float]] = None, metadata: Optional[Dict[str, Any]] = None, collection_name: Optional[str] = None) -> bool:
        logger.warning("FAISS does not support efficient updates. Re-adding the vector.")
        await self.delete_vector(vector_id, collection_name)

        if vector is None:
            logger.error("Updating metadata without providing a vector is not supported in this FAISS implementation.")
            return False

        return await self.add_vectors([vector], [vector_id], [metadata] if metadata else None, collection_name)

    async def delete_vector(self, vector_id: str, collection_name: Optional[str] = None) -> bool:
        collection_name = collection_name or self._default_collection

        if collection_name not in self._collections:
            return False

        collection = self._collections[collection_name]

        if vector_id in collection['metadata']:
            int_id = collection['metadata'][vector_id]["int_id"]
            collection['index'].remove_ids(np.array([int_id]))
            del collection['metadata'][vector_id]
            return True
        return False

    async def create_collection(self, collection_name: str, dimension: int, **kwargs) -> bool:
        if collection_name in self._collections:
            logger.debug(f"Collection '{collection_name}' already exists")
            return True

        if dimension != self.embedding_dim:
            logger.warning(f"Dimension mismatch. Expected {self.embedding_dim}, got {dimension}. Using {self.embedding_dim}.")

        # Create new collection
        self._collections[collection_name] = {
            'index': faiss.IndexIDMap(faiss.IndexFlatL2(self.embedding_dim)),
            'metadata': {}
        }

        logger.info(f"Created FAISS collection '{collection_name}'")
        return True

    async def delete_collection(self, collection_name: str) -> bool:
        if collection_name not in self._collections:
            logger.warning(f"Collection '{collection_name}' does not exist")
            return False

        # Remove from memory
        del self._collections[collection_name]

        # Delete files from disk
        paths = self._get_collection_paths(collection_name)
        try:
            if os.path.exists(paths['index']):
                os.remove(paths['index'])
            if os.path.exists(paths['metadata']):
                os.remove(paths['metadata'])

            # Remove collection directory if empty
            collection_dir = os.path.dirname(paths['index'])
            if os.path.exists(collection_dir) and not os.listdir(collection_dir):
                os.rmdir(collection_dir)

            logger.info(f"Deleted FAISS collection '{collection_name}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection files: {e}")
            return False

    async def list_collections(self) -> List[str]:
        return list(self._collections.keys())

    async def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self._collections

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        if collection_name not in self._collections:
            return {"error": "Collection not found", "name": collection_name}

        collection = self._collections[collection_name]
        return {
            "name": collection_name,
            "count": collection['index'].ntotal,
            "dimension": self.embedding_dim,
            "metadata": {
                "dimension": self.embedding_dim
            }
        }
