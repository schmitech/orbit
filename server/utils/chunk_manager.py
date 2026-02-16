"""
Chunk storage and retrieval manager for vector stores.

This module provides intelligent chunk storage, retrieval, and ranking using
vector stores and embedding-based similarity search.
"""

import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

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
                 max_embedding_tokens: int = 7500):
        """
        Initialize the chunk manager.

        Args:
            vector_store: Vector store instance (Chroma, Qdrant, etc.)
            embedding_client: Embedding client for generating embeddings
            collection_name: Name of the collection for storing chunks
            cache_ttl_hours: How long to cache chunks (default: 24 hours)
            min_similarity_score: Minimum similarity score for retrieval (default: 0.3)
            max_embedding_tokens: Maximum tokens per embedding (default: 7500 with safety buffer)
        """
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self.cache_ttl_hours = cache_ttl_hours
        self.min_similarity_score = min_similarity_score
        self.max_embedding_tokens = max_embedding_tokens

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
                          chunks: List[Dict[str, Any]],
                          source_url: str,
                          metadata: Dict[str, Any]) -> bool:
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

            # Log chunk statistics (using conservative estimate)
            avg_tokens = sum(len(text) // 3 for text in chunk_texts) // len(chunk_texts)
            max_tokens = max(len(text) // 3 for text in chunk_texts)
            logger.info(f"Embedding {len(chunk_texts)} chunks: avg={avg_tokens} tokens, max={max_tokens} tokens")

            # Generate embeddings with error handling
            try:
                embeddings = await self._embed_chunks_safely(chunk_texts)
                # If successful, all chunks should have embeddings
                if not embeddings or len(embeddings) != len(validated_chunks):
                    logger.error(f"Embedding count mismatch: got {len(embeddings)}, expected {len(validated_chunks)}")
                    return False
            except Exception as e:
                logger.error(f"Failed to generate embeddings: {e}")
                # Try one more time with smaller batches
                logger.info("Retrying with individual chunk embedding...")
                try:
                    embeddings, successful_indices = await self._embed_chunks_individually(chunk_texts)
                    # Filter validated_chunks to match successfully embedded chunks
                    if successful_indices:
                        validated_chunks = [validated_chunks[i] for i in successful_indices]
                        chunk_texts = [chunk_texts[i] for i in successful_indices]
                    
                    if not embeddings or len(embeddings) != len(validated_chunks):
                        logger.error(f"Embedding count mismatch after individual embedding: got {len(embeddings)}, expected {len(validated_chunks)}")
                        return False
                except Exception as e2:
                    logger.error(f"Individual chunk embedding also failed: {e2}")
                    return False

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
                             source_url: Optional[str] = None,
                             top_k: int = 3,
                             min_score: Optional[float] = None) -> List[Dict[str, Any]]:
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

            logger.info(f"Retrieved {len(chunks)} relevant chunks (scores: {[c['similarity_score'] for c in chunks]})")

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
                # Fallback: We'd need to query then delete each chunk individually
                # For now, just remove from cache tracking
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

    def _prepare_chunks_for_embedding(self, chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
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
            # Conservative token estimate: 1 token ≈ 3 chars (accounting for special tokens)
            # This is more accurate than 4 chars and includes safety buffer
            estimated_tokens = len(content) // 3

            # If chunk is within limits, use as-is
            if estimated_tokens <= self.max_embedding_tokens:
                validated_chunks.append(chunk)
                chunk_texts.append(content)
            else:
                # Chunk is too large - split it into smaller pieces
                logger.warning(
                    f"Chunk too large for embedding ({estimated_tokens} tokens). "
                    f"Splitting into smaller pieces (max: {self.max_embedding_tokens} tokens)"
                )

                # Recursively split the chunk
                split_pieces = self._recursive_split_chunk(content, chunk)
                
                for piece_content, piece_chunk_data in split_pieces:
                    # Double-check each piece is within limits
                    piece_tokens = len(piece_content) // 3
                    if piece_tokens > self.max_embedding_tokens:
                        # Still too large - split further by character limit
                        logger.warning(
                            f"Split piece still too large ({piece_tokens} tokens). "
                            f"Applying character-based splitting."
                        )
                        char_limit = self.max_embedding_tokens * 3 - 100  # Safety margin
                        sub_pieces = self._split_by_char_limit(piece_content, char_limit)
                        for sub_content in sub_pieces:
                            sub_chunk = piece_chunk_data.copy()
                            sub_chunk['content'] = sub_content.strip()
                            sub_chunk['token_count'] = len(sub_content) // 3
                            validated_chunks.append(sub_chunk)
                            chunk_texts.append(sub_content.strip())
                    else:
                        validated_chunks.append(piece_chunk_data)
                        chunk_texts.append(piece_content.strip())

                logger.info(f"Split large chunk into {len(split_pieces)} pieces")

        logger.info(f"Prepared {len(validated_chunks)} chunks for embedding (from {len(chunks)} original chunks)")
        return validated_chunks, chunk_texts

    def _recursive_split_chunk(self, content: str, original_chunk: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Recursively split a chunk that's too large for embedding.
        
        Args:
            content: The content to split
            original_chunk: Original chunk metadata
            
        Returns:
            List of tuples (piece_content, piece_chunk_dict)
        """
        pieces = []
        piece_count = 0
        
        # Use a safety margin: allow max_embedding_tokens * 0.95 to account for estimation errors
        safe_max_tokens = int(self.max_embedding_tokens * 0.95)
        safe_max_chars = safe_max_tokens * 3
        
        # Split by paragraphs first
        paragraphs = content.split('\n\n')
        current_piece = ""
        
        for para in paragraphs:
            para_chars = len(para)
            para_tokens = para_chars // 3
            current_chars = len(current_piece)
            current_tokens = current_chars // 3
            
            # If single paragraph exceeds limit, split by sentences
            if para_tokens > safe_max_tokens:
                # Save current piece if it exists
                if current_piece.strip():
                    piece_chunk = original_chunk.copy()
                    piece_chunk['content'] = current_piece.strip()
                    piece_chunk['token_count'] = current_tokens
                    piece_chunk['split_piece'] = piece_count
                    pieces.append((current_piece.strip(), piece_chunk))
                    piece_count += 1
                    current_piece = ""
                
                # Split paragraph by sentences
                sentences = para.split('. ')
                for sentence in sentences:
                    sentence_chars = len(sentence)
                    sentence_tokens = sentence_chars // 3
                    
                    # If single sentence is too large, split by character limit
                    if sentence_tokens > safe_max_tokens:
                        # Save current piece
                        if current_piece.strip():
                            piece_chunk = original_chunk.copy()
                            piece_chunk['content'] = current_piece.strip()
                            piece_chunk['token_count'] = len(current_piece) // 3
                            piece_chunk['split_piece'] = piece_count
                            pieces.append((current_piece.strip(), piece_chunk))
                            piece_count += 1
                            current_piece = ""
                        
                        # Split sentence by character limit
                        sub_pieces = self._split_by_char_limit(sentence + '. ', safe_max_chars)
                        for sub_piece in sub_pieces:
                            sub_chunk = original_chunk.copy()
                            sub_chunk['content'] = sub_piece.strip()
                            sub_chunk['token_count'] = len(sub_piece) // 3
                            sub_chunk['split_piece'] = piece_count
                            pieces.append((sub_piece.strip(), sub_chunk))
                            piece_count += 1
                    elif current_chars + sentence_chars > safe_max_chars:
                        # Adding sentence would exceed limit - save current piece
                        if current_piece.strip():
                            piece_chunk = original_chunk.copy()
                            piece_chunk['content'] = current_piece.strip()
                            piece_chunk['token_count'] = current_tokens
                            piece_chunk['split_piece'] = piece_count
                            pieces.append((current_piece.strip(), piece_chunk))
                            piece_count += 1
                            current_piece = ""
                        current_piece = sentence + '. '
                    else:
                        current_piece += sentence + '. '
                        current_chars += sentence_chars
                        current_tokens = current_chars // 3
            elif current_chars + para_chars > safe_max_chars:
                # Adding paragraph would exceed limit - save current piece
                if current_piece.strip():
                    piece_chunk = original_chunk.copy()
                    piece_chunk['content'] = current_piece.strip()
                    piece_chunk['token_count'] = current_tokens
                    piece_chunk['split_piece'] = piece_count
                    pieces.append((current_piece.strip(), piece_chunk))
                    piece_count += 1
                    current_piece = ""
                current_piece = para + '\n\n'
            else:
                current_piece += para + '\n\n'
                current_chars += para_chars
                current_tokens = current_chars // 3
        
        # Add remaining piece if it exists
        if current_piece.strip():
            piece_tokens = len(current_piece) // 3
            if piece_tokens > safe_max_tokens:
                # Final piece is still too large - split by character limit
                sub_pieces = self._split_by_char_limit(current_piece, safe_max_chars)
                for sub_piece in sub_pieces:
                    sub_chunk = original_chunk.copy()
                    sub_chunk['content'] = sub_piece.strip()
                    sub_chunk['token_count'] = len(sub_piece) // 3
                    sub_chunk['split_piece'] = piece_count
                    pieces.append((sub_piece.strip(), sub_chunk))
                    piece_count += 1
            else:
                piece_chunk = original_chunk.copy()
                piece_chunk['content'] = current_piece.strip()
                piece_chunk['token_count'] = piece_tokens
                piece_chunk['split_piece'] = piece_count
                pieces.append((current_piece.strip(), piece_chunk))
        
        return pieces

    def _split_by_char_limit(self, text: str, char_limit: int) -> List[str]:
        """
        Split text by character limit as last resort.
        
        Args:
            text: Text to split
            char_limit: Maximum characters per piece
            
        Returns:
            List of text pieces
        """
        pieces = []
        remaining = text
        
        while len(remaining) > char_limit:
            # Try to split at word boundary near the limit
            split_pos = char_limit
            # Look backwards for word boundary (space, newline, punctuation)
            for i in range(split_pos, max(0, split_pos - 200), -1):
                if remaining[i] in ' \n\t.,;:!?':
                    split_pos = i + 1
                    break
            
            pieces.append(remaining[:split_pos])
            remaining = remaining[split_pos:].lstrip()
        
        if remaining:
            pieces.append(remaining)
        
        return pieces

    async def _embed_chunks_safely(self, chunk_texts: List[str]) -> List[List[float]]:
        """
        Safely embed chunks with error handling.

        Args:
            chunk_texts: List of chunk texts to embed

        Returns:
            List of embeddings

        Raises:
            Exception if embedding fails
        """
        try:
            embeddings = await self.embedding_client.embed_documents(chunk_texts)
            return embeddings
        except Exception as e:
            # Check if it's a token limit error
            error_msg = str(e).lower()
            if 'maximum context length' in error_msg or 'token' in error_msg:
                logger.error(f"Token limit error during batch embedding: {e}")
                logger.error("Some chunks may still be too large. Consider reducing max_chunk_tokens.")
            raise

    async def _embed_chunks_individually(self, chunk_texts: List[str]) -> Tuple[List[List[float]], List[int]]:
        """
        Embed chunks one at a time as fallback.

        Args:
            chunk_texts: List of chunk texts to embed

        Returns:
            Tuple of (list of embeddings, list of successful chunk indices)
        """
        embeddings = []
        successful_indices = []
        failed_indices = []

        for i, text in enumerate(chunk_texts):
            try:
                # Conservative token estimate with safety margin
                estimated_tokens = len(text) // 3
                safe_max_tokens = int(self.max_embedding_tokens * 0.95)  # Safety margin
                
                if estimated_tokens > safe_max_tokens:
                    logger.warning(f"Skipping chunk {i}: too large ({estimated_tokens} tokens, max: {safe_max_tokens})")
                    failed_indices.append(i)
                    continue

                embedding = await self.embedding_client.embed_query(text)
                embeddings.append(embedding)
                successful_indices.append(i)
            except Exception as e:
                logger.error(f"Failed to embed chunk {i}: {e}")
                failed_indices.append(i)

        if failed_indices:
            logger.warning(f"Failed to embed {len(failed_indices)} chunks: {failed_indices}")

        if not embeddings:
            raise Exception("Failed to embed any chunks individually")

        return embeddings, successful_indices

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
