"""
Chunk storage and retrieval manager for vector stores.

This module provides intelligent chunk storage, retrieval, and ranking using
vector stores and embedding-based similarity search.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from utils.embedding_budget import EmbeddingBudget, resolve_embedding_budget, split_text_to_budget
from utils.embedding_recovery import FailureCategory, RecoveryConfig, embed_documents_with_recovery

logger = logging.getLogger(__name__)


class IngestionStatus(str, Enum):
    """Explicit completeness state for a `store_chunks` call -- never inferred
    from truthiness of the original storage boolean."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


VECTOR_STORE_WRITE_FAILED = "vector_store_write_failed"


@dataclass
class IngestionResult:
    """Structured outcome of `ChunkManager.store_chunks`.

    `generation_id` identifies the (content, embedding model, embedding
    budget) combination this result describes -- retrieval is isolated by
    this id so a later, differently-chunked or re-embedded generation for the
    same URL cannot mix pieces with a stale one.
    """

    status: IngestionStatus
    source_url: str
    generation_id: str
    expected_count: int
    stored_count: int
    failed_count: int
    failed_ids: list = field(default_factory=list)
    failure_reasons: dict = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.status == IngestionStatus.COMPLETE

    @property
    def partial(self) -> bool:
        return self.status == IngestionStatus.PARTIAL

    @property
    def failed(self) -> bool:
        return self.status == IngestionStatus.FAILED


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

        # Ingestion state, kept for the current process lifetime only (no
        # durable retry support is implied): completed/partial results keyed
        # by "{url_hash}:{generation_id}", pieces still needing (re-)embedding
        # or storage for a partial generation, and the latest generation seen
        # per URL so retrieval can filter out a stale, previously-ingested
        # generation for the same source.
        self._ingestion_state: dict[str, IngestionResult] = {}
        self._pending_pieces: dict[str, dict[int, dict[str, Any]]] = {}
        self._generation_by_url: dict[str, str] = {}

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
                          usage_sink=None) -> IngestionResult:
        """
        Store chunks in the vector store with embeddings.

        Args:
            chunks: List of chunk dictionaries from ContentChunker
            source_url: The URL these chunks came from
            metadata: Additional metadata about the source

        Returns:
            An `IngestionResult` describing complete/partial/failed status,
            expected/stored/failed piece counts, and per-piece failure
            reasons. Never rely on truthiness -- check `.status` (or the
            `.complete`/`.partial`/`.failed` properties) explicitly.
        """
        url_hash = self._hash_url(source_url)

        if not chunks:
            logger.warning("No chunks to store")
            return IngestionResult(IngestionStatus.FAILED, source_url, "", 0, 0, 0)

        try:
            # Validate and prepare chunks for embedding
            validated_chunks, chunk_texts = self._prepare_chunks_for_embedding(chunks)

            if not chunk_texts:
                logger.error("No valid chunks to embed after validation")
                return IngestionResult(IngestionStatus.FAILED, source_url, "", 0, 0, 0)

            # Ingestion identity: source URL, prepared-content hash, embedding
            # model identity, and budget version. Any change to these makes a
            # new generation, so retries never mix pieces produced under a
            # different model/budget/content into one "complete" result.
            content_hash = self._hash_content(chunk_texts)
            model_identity = str(getattr(self.embedding_client, "model", "") or "")
            budget_version = f"{self.budget.effective_max_tokens}:{self.budget.counting_mode}"
            generation_id = hashlib.sha256(
                f"{content_hash}:{model_identity}:{budget_version}".encode()
            ).hexdigest()[:16]
            state_key = f"{url_hash}:{generation_id}"

            cached = self._ingestion_state.get(state_key)
            if cached is not None and cached.status == IngestionStatus.COMPLETE and self._is_cached(url_hash):
                logger.info(f"Chunks for {source_url} already fully stored at this generation, skipping")
                return cached

            # A prior attempt at this exact generation may have partially
            # succeeded -- retry only the pieces still pending instead of
            # re-embedding/re-storing everything, and keep accumulating
            # toward the same expected total.
            pending = self._pending_pieces.get(state_key)
            if pending is None:
                pending = {i: validated_chunks[i] for i in range(len(validated_chunks))}
            work_indices = sorted(pending.keys())
            texts_to_embed = [pending[i]["content"] for i in work_indices]
            expected_count = len(validated_chunks)
            already_stored = expected_count - len(work_indices)

            counts = [self.budget.count(text).count for text in texts_to_embed]
            avg_tokens = sum(counts) // len(counts)
            max_tokens = max(counts)
            logger.debug(
                f"Embedding {len(texts_to_embed)} chunk(s) ({already_stored} already stored): "
                f"avg={avg_tokens} tokens, max={max_tokens} tokens (mode={self.budget.counting_mode})"
            )

            # Generate embeddings with bounded, policy-driven recovery: one
            # attempt/deadline budget shared across every batch and split
            # retry, document embedding semantics preserved throughout (no
            # embed_query fallback), and input-to-vector provenance kept
            # even when an oversized input must be split and re-embedded.
            recovery = await embed_documents_with_recovery(
                self.embedding_client, texts_to_embed, self.budget,
                usage_sink=usage_sink, config=self.recovery_config,
            )

            failure_reasons: dict[str, str] = {}
            remaining_pending: dict[int, dict[str, Any]] = {}
            stored_ids: list[str] = []
            timestamp = datetime.utcnow().isoformat()

            for embed_idx in recovery.failed_indices:
                orig_idx = work_indices[embed_idx]
                piece_id = f"{state_key}_p{orig_idx}"
                failure_reasons[piece_id] = recovery.failure_reasons.get(embed_idx, FailureCategory.UNKNOWN)
                remaining_pending[orig_idx] = pending[orig_idx]

            pieces_by_orig_idx: dict[int, list] = {}
            for piece in recovery.pieces:
                orig_idx = work_indices[piece.source_index]
                pieces_by_orig_idx.setdefault(orig_idx, []).append(piece)

            for orig_idx, pieces in pieces_by_orig_idx.items():
                stored_pieces_metadata = []
                stored_pieces_ids = []
                stored_pieces_vectors = []
                for sub_idx, piece in enumerate(pieces):
                    source_chunk = validated_chunks[orig_idx]
                    if piece.split_depth:
                        chunk = source_chunk.copy()
                        chunk['content'] = piece.text
                        token_count = self.budget.count(piece.text)
                        chunk['token_count'] = token_count.count
                        chunk['token_count_estimated'] = token_count.estimated
                    else:
                        chunk = source_chunk

                    piece_id = f"{state_key}_p{orig_idx}" if len(pieces) == 1 else f"{state_key}_p{orig_idx}_s{sub_idx}"
                    chunk_metadata = {
                        "source_url": source_url,
                        "generation_id": generation_id,
                        "chunk_id": chunk.get("chunk_id", orig_idx),
                        "total_chunks": chunk.get("total_chunks", expected_count),
                        "section": chunk.get("section", ""),
                        "hierarchy": "|".join(chunk.get("hierarchy", [])),
                        "token_count": chunk.get("token_count", 0),
                        "position": chunk.get("position", orig_idx),
                        "timestamp": timestamp,
                        "content": chunk['content'],  # Store content in metadata for retrieval
                        # Add source metadata
                        **{f"source_{k}": v for k, v in metadata.items()
                           if isinstance(v, (str, int, float, bool))}
                    }
                    stored_pieces_ids.append(piece_id)
                    stored_pieces_vectors.append(piece.vector)
                    stored_pieces_metadata.append(chunk_metadata)

                # Store per original index so a vector-store failure on one
                # piece never masks or blocks another piece's successful
                # write, and so completion can be confirmed piece by piece.
                try:
                    write_ok = await self.vector_store.add_vectors(
                        vectors=stored_pieces_vectors,
                        ids=stored_pieces_ids,
                        metadata=stored_pieces_metadata,
                        collection_name=self.collection_name,
                    )
                except Exception as exc:
                    logger.error(f"Vector store write failed for chunk {orig_idx} of {source_url}: {exc}")
                    write_ok = False

                if not write_ok and hasattr(self.vector_store, "get_vector"):
                    # A rejected write on a deterministic, already-stored id
                    # (e.g. an add-not-upsert adapter refusing a duplicate id
                    # on a retry after restart) is not a real failure --
                    # confirm existence before treating it as one.
                    try:
                        write_ok = True
                        for piece_id in stored_pieces_ids:
                            existing = await self.vector_store.get_vector(
                                piece_id, collection_name=self.collection_name
                            )
                            if existing is None:
                                write_ok = False
                                break
                    except Exception as exc:
                        write_ok = False
                        logger.debug(f"Could not confirm existing vector(s) for chunk {orig_idx}: {exc}")

                if write_ok:
                    stored_ids.extend(stored_pieces_ids)
                else:
                    for piece_id in stored_pieces_ids:
                        failure_reasons[piece_id] = VECTOR_STORE_WRITE_FAILED
                    remaining_pending[orig_idx] = pending[orig_idx]

            newly_stored = sum(1 for orig_idx in pieces_by_orig_idx if orig_idx not in remaining_pending)
            stored_count = already_stored + newly_stored
            failed_count = expected_count - stored_count

            if failed_count == 0:
                status = IngestionStatus.COMPLETE
            elif stored_count > 0:
                status = IngestionStatus.PARTIAL
            else:
                status = IngestionStatus.FAILED

            if remaining_pending:
                self._pending_pieces[state_key] = remaining_pending
            else:
                self._pending_pieces.pop(state_key, None)

            self._generation_by_url[url_hash] = generation_id

            if status == IngestionStatus.COMPLETE:
                self._cached_urls[url_hash] = datetime.utcnow()

            result = IngestionResult(
                status=status,
                source_url=source_url,
                generation_id=generation_id,
                expected_count=expected_count,
                stored_count=stored_count,
                failed_count=failed_count,
                failed_ids=list(failure_reasons.keys()),
                failure_reasons=failure_reasons,
            )
            self._ingestion_state[state_key] = result

            logger.debug(
                f"Ingestion for {source_url}: status={status.value}, prepared={expected_count}, "
                f"embedded_this_attempt={len(texts_to_embed) - len(recovery.failed_indices)}, "
                f"stored={stored_count}, failed={failed_count}"
            )
            if recovery.terminal_error is not None and recovery.terminal_error.category == FailureCategory.AUTH:
                logger.error(f"Authentication/configuration error during embedding: {recovery.terminal_error.reason}")

            return result

        except Exception as e:
            logger.error(f"Error storing chunks: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return IngestionResult(IngestionStatus.FAILED, source_url, "", len(chunks), 0, len(chunks))

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

            # Build metadata filter if source_url provided. Filter by the
            # latest known generation for that URL too, so a superseded
            # generation (changed content, model, or budget) cannot return
            # stale pieces alongside or instead of the current one. Without a
            # known generation (e.g. after a process restart, before any
            # store_chunks call in this process), no generation filter is
            # applied -- this is a documented limitation of the in-memory
            # generation map, not a durable guarantee.
            filter_metadata = None
            if source_url:
                filter_metadata = {"source_url": source_url}
                generation_id = self._generation_by_url.get(self._hash_url(source_url))
                if generation_id:
                    filter_metadata["generation_id"] = generation_id

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

            # Clear state for every generation ever seen for this URL, not
            # just the latest one -- an older partial generation's pending
            # map must not survive to later report false completion after
            # its pieces are deleted below.
            self._generation_by_url.pop(url_hash, None)
            state_prefix = f"{url_hash}:"
            for state_key in [k for k in self._ingestion_state if k.startswith(state_prefix)]:
                del self._ingestion_state[state_key]
            for state_key in [k for k in self._pending_pieces if k.startswith(state_prefix)]:
                del self._pending_pieces[state_key]

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

    def _hash_content(self, texts: list[str]) -> str:
        """Deterministic hash of prepared chunk texts, used as part of the
        ingestion generation identity so changed content is never mistaken
        for the same generation."""
        hasher = hashlib.sha256()
        for text in texts:
            hasher.update(text.encode("utf-8"))
            hasher.update(b"\x1f")
        return hasher.hexdigest()[:16]

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

        logger.debug(f"Prepared {len(validated_chunks)} chunks for embedding (from {len(chunks)} original chunks)")
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
                self._generation_by_url.pop(url_hash, None)
                state_prefix = f"{url_hash}:"
                for state_key in [k for k in self._ingestion_state if k.startswith(state_prefix)]:
                    del self._ingestion_state[state_key]
                for state_key in [k for k in self._pending_pieces if k.startswith(state_prefix)]:
                    del self._pending_pieces[state_key]

            if expired_hashes:
                logger.info(f"Cleaned up {len(expired_hashes)} expired URL caches")

        except Exception as e:
            logger.error(f"Error cleaning up expired chunks: {e}")
