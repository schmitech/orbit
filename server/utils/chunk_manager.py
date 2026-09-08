"""
Chunk storage and retrieval manager for vector stores.

This module provides intelligent chunk storage, retrieval, and ranking using
vector stores and embedding-based similarity search.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from utils.embedding_budget import EmbeddingBudget, resolve_embedding_budget, split_text_to_budget
from utils.embedding_recovery import FailureCategory, RecoveryConfig, embed_documents_with_recovery

logger = logging.getLogger(__name__)


class ChunkManager:
    """
    Manages storage and retrieval of content chunks in a vector store.

    Features:
    - Stores chunks with embeddings in vector store
    - Retrieves relevant chunks based on query similarity
    - Supports caching and TTL for chunks
    - Prevents duplicate chunk storage
    """

    def __init__(self,
                 vector_store: Any,
                 embedding_client: Any,
                 collection_name: str = "firecrawl_chunks",
                 cache_ttl_hours: int = 24,
                 min_similarity_score: float = 0.3,
                 max_embedding_tokens: int = 7500,
                 budget: EmbeddingBudget | None = None,
                 recovery_config: RecoveryConfig | None = None):
        """
        Initialize the chunk manager.

        Args:
            vector_store: Vector store instance (Chroma, Qdrant, etc.)
            embedding_client: Embedding client for generating embeddings
            collection_name: Name of the collection for storing chunks
            cache_ttl_hours: How long to cache chunks (default: 24 hours)
            min_similarity_score: Minimum similarity score for retrieval (default: 0.3)
            max_embedding_tokens: Maximum tokens per embedding (default: 7500 with safety buffer)
            budget: Shared EmbeddingBudget to validate against (preferred). When
                provided, callers should pass the same instance used by the
                ContentChunker so preparation and submission agree on one cutoff.
            recovery_config: Bounds (attempts, deadline, concurrency, split depth)
                for embedding recovery. Defaults to RecoveryConfig()'s values.
        """
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self.cache_ttl_hours = cache_ttl_hours
        self.min_similarity_score = min_similarity_score
        self.budget = budget or resolve_embedding_budget(
            max_embedding_tokens=max_embedding_tokens,
            model=getattr(embedding_client, "model", None),
        )
        self.max_embedding_tokens = self.budget.effective_max_tokens
        self.recovery_config = recovery_config or RecoveryConfig()

        # Track which URLs have been cached
        self._cached_urls = {}

    async def initialize(self):
        """Initialize the chunk manager and create collection if needed."""
        try:
            # Check if collection exists first
            collection_exists = False
            if hasattr(self.vector_store, 'collection_exists'):
                collection_exists = await self.vector_store.collection_exists(self.collection_name)

            if collection_exists:
                logger.info(f"Collection '{self.collection_name}' already exists")
            else:
                # Create collection if it doesn't exist
                if hasattr(self.vector_store, 'create_collection'):
                    # Get embedding dimension from a test embedding
                    test_embedding = await self.embedding_client.embed_query("test")
                    dimension = len(test_embedding) if test_embedding else 384

                    await self.vector_store.create_collection(
                        collection_name=self.collection_name,
                        dimension=dimension
                    )
                    logger.info(f"Created collection '{self.collection_name}' for chunks (dimension: {dimension})")
        except Exception as e:
            # Collection might already exist - that's fine
            logger.debug(f"Collection initialization: {e}")

    async def store_chunks(self,
                          chunks: list[dict[str, Any]],
                          source_url: str,
                          metadata: dict[str, Any],
                          usage_sink=None) -> bool:
        """
        Store chunks in the vector store with embeddings.

        Args:
            chunks: List of chunk dictionaries from ContentChunker
            source_url: The URL these chunks came from
            metadata: Additional metadata about the source

        Returns:
            True if successful, False otherwise
        """
        try:
            if not chunks:
                logger.warning("No chunks to store")
                return False

            # Check if we've already cached this URL recently
            url_hash = self._hash_url(source_url)
            if self._is_cached(url_hash):
                logger.info(f"Chunks for {source_url} already cached, skipping storage")
                return True

            # Validate and prepare chunks for embedding
            validated_chunks, chunk_texts = self._prepare_chunks_for_embedding(chunks)

            if not chunk_texts:
                logger.error("No valid chunks to embed after validation")
                return False

            # Log chunk statistics
            counts = [self.budget.count(text).count for text in chunk_texts]
            avg_tokens = sum(counts) // len(counts)
            max_tokens = max(counts)
            logger.debug(
                f"Embedding {len(chunk_texts)} chunks: avg={avg_tokens} tokens, max={max_tokens} tokens "
                f"(mode={self.budget.counting_mode})"
            )

            # Generate embeddings with bounded, policy-driven recovery: one
            # attempt/deadline budget shared across every batch and split
            # retry, document embedding semantics preserved throughout (no
            # embed_query fallback), and input-to-vector provenance kept
            # even when an oversized input must be split and re-embedded.
            recovery = await embed_documents_with_recovery(
                self.embedding_client, chunk_texts, self.budget,
                usage_sink=usage_sink, config=self.recovery_config,
            )

            if recovery.terminal_error is not None and recovery.terminal_error.category == FailureCategory.AUTH:
                logger.error(f"Authentication/configuration error during embedding: {recovery.terminal_error.reason}")
                return False

            if recovery.failed_indices:
                logger.warning(
                    f"Failed to embed {len(recovery.failed_indices)} chunk(s): {recovery.failure_reasons}"
                )

            if not recovery.pieces:
                logger.error("No chunks were successfully embedded")
                return False

            expanded_chunks = []
            embeddings = []
            for piece in recovery.pieces:
                source_chunk = validated_chunks[piece.source_index]
                if piece.split_depth:
                    sub_chunk = source_chunk.copy()
                    sub_chunk['content'] = piece.text
                    token_count = self.budget.count(piece.text)
                    sub_chunk['token_count'] = token_count.count
                    sub_chunk['token_count_estimated'] = token_count.estimated
                    expanded_chunks.append(sub_chunk)
                else:
                    expanded_chunks.append(source_chunk)
                embeddings.append(piece.vector)

            validated_chunks = expanded_chunks

            # Prepare vectors and metadata for storage
            vectors = []
            ids = []
            metadatas = []
            timestamp = datetime.utcnow().isoformat()

            for i, (chunk, embedding) in enumerate(zip(validated_chunks, embeddings)):
                chunk_id = f"{url_hash}_chunk_{i}"

                chunk_metadata = {
                    "source_url": source_url,
                    "chunk_id": chunk.get("chunk_id", i),
                    "total_chunks": chunk.get("total_chunks", len(validated_chunks)),
                    "section": chunk.get("section", ""),
                    "hierarchy": "|".join(chunk.get("hierarchy", [])),
                    "token_count": chunk.get("token_count", 0),
                    "position": chunk.get("position", i),
                    "timestamp": timestamp,
                    "content": chunk['content'],  # Store content in metadata for retrieval
                    # Add source metadata
                    **{f"source_{k}": v for k, v in metadata.items()
                       if isinstance(v, (str, int, float, bool))}
                }

                vectors.append(embedding)
                ids.append(chunk_id)
                metadatas.append(chunk_metadata)

            # Store in vector store
            success = await self.vector_store.add_vectors(
                vectors=vectors,
                ids=ids,
                metadata=metadatas,
                collection_name=self.collection_name
            )

            if success:
                # Mark URL as cached
                self._cached_urls[url_hash] = datetime.utcnow()
                logger.info(f"Successfully stored {len(chunks)} chunks for {source_url}")
            else:
                logger.error("Failed to store chunks in vector store")

            return success

        except Exception as e:
            logger.error(f"Error storing chunks: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def retrieve_chunks(self,
                             query: str,
                             source_url: str | None = None,
                             top_k: int = 3,
                             min_score: float | None = None,
                             usage_sink=None) -> list[dict[str, Any]]:
        """
        Retrieve relevant chunks based on query similarity.

        Args:
            query: The user's query
            source_url: Optional URL to filter chunks by source
            top_k: Number of top chunks to retrieve (default: 3)
            min_score: Minimum similarity score (default: use configured min_similarity_score)

        Returns:
            List of relevant chunks with content and metadata
        """
        try:
            # Generate query embedding
            if hasattr(self.embedding_client, "embed_query_tracked"):
                local_usage = {}
                query_embedding = await self.embedding_client.embed_query_tracked(
                    query, usage_sink=local_usage
                )
                if usage_sink is not None:
                    from ai_services.providers.usage_reporting import accumulate_usage_sink
                    accumulate_usage_sink(usage_sink, local_usage)
            else:
                query_embedding = await self.embedding_client.embed_query(query)
            if not query_embedding:
                logger.error("Failed to generate query embedding")
                return []

            query_vector = query_embedding

            # Build metadata filter if source_url provided
            filter_metadata = None
            if source_url:
                filter_metadata = {"source_url": source_url}

            # Search vector store
            results = await self.vector_store.search_vectors(
                query_vector=query_vector,
                limit=top_k * 2,  # Get more results to filter
                collection_name=self.collection_name,
                filter_metadata=filter_metadata
            )

            if not results:
                logger.info("No chunks found in vector store")
                return []

            # Filter by minimum score and sort
            min_score = min_score or self.min_similarity_score
            filtered_results = [
                r for r in results
                if r.get('score', 0) >= min_score
            ]

            # Take top K
            top_results = filtered_results[:top_k]

            # Format results
            chunks = []
            for result in top_results:
                metadata = result.get('metadata', {})

                # Reconstruct hierarchy from string
                hierarchy_str = metadata.get('hierarchy', '')
                hierarchy = hierarchy_str.split('|') if hierarchy_str else []

                chunk = {
                    "content": metadata.get('content', ''),
                    "chunk_id": metadata.get('chunk_id', 0),
                    "total_chunks": metadata.get('total_chunks', 1),
                    "section": metadata.get('section', ''),
                    "hierarchy": hierarchy,
                    "token_count": metadata.get('token_count', 0),
                    "position": metadata.get('position', 0),
                    "similarity_score": result.get('score', 0.0),
                    "source_url": metadata.get('source_url', ''),
                    "timestamp": metadata.get('timestamp', '')
                }
                chunks.append(chunk)

            logger.debug(f"Retrieved {len(chunks)} relevant chunks (scores: {[c['similarity_score'] for c in chunks]})")

            return chunks

        except Exception as e:
            logger.error(f"Error retrieving chunks: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def has_cached_chunks(self, source_url: str) -> bool:
        """
        Check if chunks for a URL are already cached.

        Args:
            source_url: The URL to check

        Returns:
            True if chunks exist and are not expired
        """
        url_hash = self._hash_url(source_url)
        return self._is_cached(url_hash)

    async def invalidate_cache(self, source_url: str) -> bool:
        """
        Invalidate cached chunks for a URL.

        Args:
            source_url: The URL to invalidate

        Returns:
            True if successful
        """
        try:
            url_hash = self._hash_url(source_url)

            # Remove from cache tracking
            if url_hash in self._cached_urls:
                del self._cached_urls[url_hash]

            # Delete chunks from vector store
            # This requires getting all chunk IDs first
            # Most vector stores support metadata-based deletion
            if hasattr(self.vector_store, 'delete_by_metadata'):
                await self.vector_store.delete_by_metadata(
                    metadata_filter={"source_url": source_url},
                    collection_name=self.collection_name
                )
            else:
                # The vector store cannot remove chunks by metadata; remove only local cache tracking.
                logger.warning("Vector store doesn't support metadata-based deletion")

            logger.info(f"Invalidated cache for {source_url}")
            return True

        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            return False

    def _hash_url(self, url: str) -> str:
        """Generate a consistent hash for a URL."""
        return hashlib.md5(url.encode()).hexdigest()

    def _is_cached(self, url_hash: str) -> bool:
        """Check if a URL hash is in cache and not expired."""
        if url_hash not in self._cached_urls:
            return False

        cached_time = self._cached_urls[url_hash]
        expiry_time = cached_time + timedelta(hours=self.cache_ttl_hours)

        if datetime.utcnow() > expiry_time:
            # Expired - remove from cache
            del self._cached_urls[url_hash]
            return False

        return True

    def _prepare_chunks_for_embedding(self, chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Validate and prepare chunks for embedding.

        Splits chunks that are too large for the embedding model.

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Tuple of (validated_chunks, chunk_texts)
        """
        validated_chunks = []
        chunk_texts = []

        for chunk in chunks:
            content = chunk['content']

            # If chunk already satisfies the effective budget, use as-is
            if self.budget.fits(content):
                validated_chunks.append(chunk)
                chunk_texts.append(content)
                continue

            # Chunk is too large - split it against the same effective budget
            # used during preparation, so no path applies a different cutoff.
            token_count = self.budget.count(content)
            logger.warning(
                f"Chunk too large for embedding ({token_count.count} tokens, "
                f"mode={'estimated' if token_count.estimated else 'exact'}). "
                f"Splitting into smaller pieces (effective budget: {self.budget.effective_max_tokens} tokens)"
            )

            pieces = split_text_to_budget(content, self.budget)
            for piece_content in pieces:
                piece_token_count = self.budget.count(piece_content)
                sub_chunk = chunk.copy()
                sub_chunk['content'] = piece_content
                sub_chunk['token_count'] = piece_token_count.count
                sub_chunk['token_count_estimated'] = piece_token_count.estimated
                validated_chunks.append(sub_chunk)
                chunk_texts.append(piece_content)

            logger.info(f"Split large chunk into {len(pieces)} pieces")

        logger.info(f"Prepared {len(validated_chunks)} chunks for embedding (from {len(chunks)} original chunks)")
        return validated_chunks, chunk_texts

    async def cleanup_expired_chunks(self):
        """
        Clean up expired chunks from the vector store.

        This should be called periodically to remove old chunks.
        """
        try:
            # Remove expired URLs from cache tracking
            expired_hashes = [
                url_hash for url_hash, cached_time in self._cached_urls.items()
                if datetime.utcnow() > cached_time + timedelta(hours=self.cache_ttl_hours)
            ]

            for url_hash in expired_hashes:
                del self._cached_urls[url_hash]

            if expired_hashes:
                logger.info(f"Cleaned up {len(expired_hashes)} expired URL caches")

        except Exception as e:
            logger.error(f"Error cleaning up expired chunks: {e}")
