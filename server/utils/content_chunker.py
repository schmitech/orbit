"""
Content chunking utilities for handling large web content.

This module provides intelligent content chunking for large documents (especially markdown)
to prevent exceeding LLM context limits and improve retrieval performance.

SPECIALIZATION:
This chunker is specialized for markdown web content from Firecrawl/web scraping.
It parses hierarchical markdown structure (headers) and chunks by sections.

For general file chunking (PDF, DOCX, TXT), see:
    server/services/file_processing/chunking/
    - FixedSizeChunker: Character-based chunking
    - SemanticChunker: Sentence-based chunking

KEY DIFFERENCES:
    File Chunking               vs    Web Content Chunking
    --------------                    --------------------
    Character-based                   Token-based
    Flat structure                    Hierarchical (H1-H6)
    Sentence/paragraph aware          Section/heading aware
    Returns Chunk objects             Returns dictionaries
    For uploaded files                For scraped web content

SOURCE SPANS AND OVERLAP:
Each emitted chunk carries `source_span` (start, end) offsets into the original
`content` string covering exactly the chunk's non-overlap text. Concatenating
chunks in order by `source_span` reconstructs the original content, except for
whitespace strictly between two spans (e.g. the blank line separating two
paragraphs that land in different chunks) -- that inter-chunk whitespace is
intentionally not duplicated into either chunk. `overlap_span`, when present,
points at the *previous* chunk's source text that was copied into this chunk's
`content` for context continuity; it is not part of this chunk's own coverage.
"""

import re
import hashlib
import logging
from typing import Any, Optional

from utils.embedding_budget import EmbeddingBudget, resolve_embedding_budget

logger = logging.getLogger(__name__)

_FENCE_MARKER_PATTERN = re.compile(r"```")
_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)$", re.MULTILINE)
_PARAGRAPH_SPLIT_PATTERN = r"\n\s*\n"
_SENTENCE_SPLIT_PATTERN = r"(?<=[.!?])\s+"
_WORD_BOUNDARY_CHARS = " \n\t.,;:!?"


def _fenced_code_spans(content: str) -> list[tuple[int, int]]:
    """Pair up ``` markers into fenced-code spans. An unmatched opening
    fence (truncated/scraped content with no closing ```) extends through
    end-of-document, matching how Markdown renders it."""
    markers = list(_FENCE_MARKER_PATTERN.finditer(content))
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(markers):
        start = markers[i].start()
        if i + 1 < len(markers):
            spans.append((start, markers[i + 1].end()))
            i += 2
        else:
            spans.append((start, len(content)))
            i += 1
    return spans


def _iter_units(text: str, pattern: str) -> list[tuple[str, int, int]]:
    """Split `text` on `pattern`, returning (unit_text, start, end) offsets
    relative to `text` covering the full input contiguously -- separators
    (e.g. blank lines between paragraphs) are emitted as their own unit
    rather than dropped, so spans never lose source coverage."""
    units = []
    last = 0
    for m in re.finditer(pattern, text):
        if m.start() > last:
            units.append((text[last:m.start()], last, m.start()))
        if m.end() > m.start():
            units.append((text[m.start():m.end()], m.start(), m.end()))
        last = m.end()
    if last < len(text):
        units.append((text[last:], last, len(text)))
    return units


def _absorb_whitespace_spans(content: str, spans: list[tuple[int, int]],
                              max_tokens: int, budget: EmbeddingBudget) -> list[tuple[int, int]]:
    """Fold any whitespace-only span (e.g. a lone separator that couldn't be
    packed with either neighbor) into the adjacent span rather than dropping
    it, so no source text is ever skipped. Only merges when the enlarged
    neighbor still fits `max_tokens` -- a whitespace span too large to fit
    with either neighbor (e.g. one already character-split to the packing
    target) is kept as its own standalone unit instead of recreating an
    over-budget chunk."""
    result = list(spans)
    i = 0
    while i < len(result):
        start, end = result[i]
        if content[start:end].strip():
            i += 1
            continue
        if i > 0:
            prev_start, prev_end = result[i - 1]
            merged_text = content[prev_start:end]
            if budget.count(merged_text).count <= max_tokens:
                result[i - 1] = (prev_start, end)
                del result[i]
                continue
        if i + 1 < len(result):
            next_start, next_end = result[i + 1]
            merged_text = content[start:next_end]
            if budget.count(merged_text).count <= max_tokens:
                result[i + 1] = (start, next_end)
                del result[i]
                continue
        # Cannot merge into either neighbor without exceeding the budget;
        # keep it as its own span rather than dropping or over-merging it.
        i += 1
    return result


def _split_span_chars(text: str, base: int, max_tokens: int, budget: EmbeddingBudget) -> list[tuple[int, int]]:
    """Last-resort character-boundary split; always makes progress on nonempty text."""
    pieces: list[tuple[int, int]] = []
    n = len(text)
    pos = 0
    while pos < n:
        remaining = text[pos:]
        if budget.count(remaining).count <= max_tokens:
            pieces.append((base + pos, base + n))
            break

        lo, hi, best = 1, len(remaining), 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if budget.count(remaining[:mid]).count <= max_tokens:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best == 0:
            raise ValueError(
                "Unable to produce a valid nonempty piece within the effective budget: "
                "a single character exceeds the effective token budget"
            )

        cut = best
        for i in range(cut, max(0, cut - 200), -1):
            if remaining[i - 1] in _WORD_BOUNDARY_CHARS:
                cut = i
                break

        pieces.append((base + pos, base + pos + cut))
        pos += cut
    return pieces


def _split_span_sentence(text: str, base: int, max_tokens: int, budget: EmbeddingBudget) -> list[tuple[int, int]]:
    return _split_span_generic(text, base, max_tokens, budget, _SENTENCE_SPLIT_PATTERN, _split_span_chars)


def _split_span_paragraph(text: str, base: int, max_tokens: int, budget: EmbeddingBudget) -> list[tuple[int, int]]:
    return _split_span_generic(text, base, max_tokens, budget, _PARAGRAPH_SPLIT_PATTERN, _split_span_sentence)


def _split_span_generic(text: str, base: int, max_tokens: int, budget: EmbeddingBudget,
                         sep_pattern: str, fallback) -> list[tuple[int, int]]:
    units = _iter_units(text, sep_pattern)
    if len(units) <= 1:
        return fallback(text, base, max_tokens, budget)

    pieces: list[tuple[int, int]] = []
    current_start: Optional[int] = None
    current_end: Optional[int] = None

    for utext, ustart, uend in units:
        candidate_start = ustart if current_start is None else current_start
        candidate_end = uend
        candidate_text = text[candidate_start:candidate_end]

        if budget.count(candidate_text).count <= max_tokens:
            current_start, current_end = candidate_start, candidate_end
            continue

        if current_start is not None:
            pieces.append((base + current_start, base + current_end))
            current_start = current_end = None

        if budget.count(utext).count <= max_tokens:
            current_start, current_end = ustart, uend
        else:
            pieces.extend(fallback(utext, base + ustart, max_tokens, budget))

    if current_start is not None:
        pieces.append((base + current_start, base + current_end))

    return pieces


def _take_overlap_suffix(prev_source_text: str, prev_start: int, max_tokens: int,
                          budget: EmbeddingBudget) -> Optional[tuple[int, int, str]]:
    """Find the largest word-boundary-aligned suffix of `prev_source_text` whose
    token count fits `max_tokens`. Returns (abs_start, abs_end, text) or None."""
    if max_tokens <= 0 or not prev_source_text:
        return None
    if budget.count(prev_source_text).count <= max_tokens:
        overlap_text = prev_source_text.strip()
        if not overlap_text:
            return None
        idx = prev_source_text.rfind(overlap_text)
        return prev_start + idx, prev_start + idx + len(overlap_text), overlap_text

    lo, hi, best = 1, len(prev_source_text), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if budget.count(prev_source_text[-mid:]).count <= max_tokens:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best == 0:
        return None

    cut = len(prev_source_text) - best
    for i in range(cut, min(len(prev_source_text), cut + 200)):
        if prev_source_text[i - 1] in _WORD_BOUNDARY_CHARS:
            cut = i
            break

    overlap_text = prev_source_text[cut:].strip()
    if not overlap_text:
        return None
    idx = prev_source_text.rfind(overlap_text)
    return prev_start + idx, prev_start + idx + len(overlap_text), overlap_text


class ContentChunker:
    """
    Intelligent content chunker for markdown documents.

    Features:
    - Semantic chunking based on markdown structure
    - Preserves preamble content and heading hierarchy (fenced-code headings ignored)
    - Tracks source spans so chunk coverage can be verified independently of
      display whitespace
    - Overlap is reserved within the chunk target/embedding budget and trimmed
      before any new source content is dropped
    - Configurable chunk sizes with overlap
    - Token estimation
    """

    def __init__(self,
                 max_chunk_tokens: int = 4000,
                 chunk_overlap_tokens: int = 200,
                 min_chunk_tokens: int = 500,
                 budget: Optional[EmbeddingBudget] = None,
                 model: Optional[str] = None):
        """
        Initialize the content chunker.

        Args:
            max_chunk_tokens: Maximum tokens per chunk (default: 4000)
            chunk_overlap_tokens: Overlap between chunks (default: 200)
            min_chunk_tokens: Minimum tokens for a chunk (default: 500)
            budget: Shared EmbeddingBudget to validate against (preferred). When
                provided, callers should pass the same instance used by the
                ChunkManager so preparation and submission agree on one cutoff.
            model: Embedding model identifier, used to resolve a budget when
                one isn't supplied directly.
        """
        self.budget = budget or resolve_embedding_budget(
            max_embedding_tokens=max_chunk_tokens,
            model=model,
            chunk_target_tokens=max_chunk_tokens,
            overlap_tokens=chunk_overlap_tokens,
            min_chunk_tokens=min_chunk_tokens,
        )
        self.max_chunk_tokens = self.budget.chunk_target_tokens
        self.chunk_overlap_tokens = self.budget.overlap_tokens
        self.min_chunk_tokens = self.budget.min_chunk_tokens
        # Room reserved for overlap so a chunk's main content plus overlap
        # still fits the chunk target without trimming new source content.
        self._pack_target_tokens = max(1, self.max_chunk_tokens - self.chunk_overlap_tokens)

    def should_chunk(self, content: str) -> bool:
        """Determine if content should be chunked based on size."""
        return self.budget.count(content).count > self.max_chunk_tokens

    def chunk_markdown(self, content: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Chunk markdown content into semantic sections.

        Args:
            content: Markdown content to chunk
            metadata: Metadata about the source document

        Returns:
            List of chunk dictionaries with content, metadata, and source spans
        """
        if not content:
            return []

        source_hash = self._hash_content(content)

        if not self.should_chunk(content):
            token_count = self.budget.count(content)
            return [{
                "chunk_id": 0,
                "total_chunks": 1,
                "content": content,
                "section": metadata.get('title', 'Full Document'),
                "hierarchy": [metadata.get('title', 'Document')],
                "position": 0,
                "token_count": token_count.count,
                "token_count_estimated": token_count.estimated,
                "overlap_with_prev": False,
                "overlap_with_next": False,
                "source_span": (0, len(content)),
                "overlap_span": None,
                "source_url": metadata.get('url', ''),
                "source_hash": source_hash,
            }]

        blocks = self._parse_blocks(content)
        units = self._split_blocks_to_units(content, blocks)
        pieces = self._merge_contiguous_units(content, units)
        chunks = self._add_overlap_and_finalize(content, pieces, metadata, source_hash)

        logger.info(
            f"Chunked content into {len(chunks)} chunks "
            f"(original: {self.budget.count(content).count} tokens, mode={self.budget.counting_mode})"
        )

        return chunks

    def _parse_blocks(self, content: str) -> list[dict[str, Any]]:
        """Parse content into an ordered list of contiguous blocks covering the
        entire document: an optional preamble block, then one block per
        heading. Headings inside fenced code blocks are not treated as
        section boundaries."""
        fenced_spans = _fenced_code_spans(content)

        def in_fence(pos: int) -> bool:
            return any(s <= pos < e for s, e in fenced_spans)

        matches = [m for m in _HEADER_PATTERN.finditer(content) if not in_fence(m.start())]

        blocks: list[dict[str, Any]] = []

        if not matches:
            return [{"start": 0, "end": len(content), "level": 0, "title": None, "hierarchy": ["Document"]}]

        if matches[0].start() > 0:
            blocks.append({
                "start": 0, "end": matches[0].start(),
                "level": 0, "title": None, "hierarchy": ["Document"],
            })

        stack: list[tuple[int, str]] = []
        for i, m in enumerate(matches):
            level = len(m.group(1))
            title = m.group(2).strip()
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

            while stack and stack[-1][0] >= level:
                stack.pop()
            hierarchy = [t for _, t in stack] + [title]
            stack.append((level, title))

            blocks.append({"start": start, "end": end, "level": level, "title": title, "hierarchy": hierarchy})

        return blocks

    def _absorb_whitespace_blocks(self, content: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fold a whitespace-only block (e.g. blank lines before the first
        heading) into an adjacent block's span instead of dropping it, so its
        source coverage is never lost. Keeps the surviving neighbor's
        hierarchy/title."""
        result = [dict(b) for b in blocks]
        i = 0
        while i < len(result):
            block = result[i]
            if content[block["start"]:block["end"]].strip() or len(result) == 1:
                i += 1
                continue
            if i > 0:
                result[i - 1]["end"] = block["end"]
            else:
                result[i + 1]["start"] = block["start"]
            del result[i]
        return result

    def _split_blocks_to_units(self, content: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Split each block into one or more units that individually fit the
        packing target, preserving order and source spans."""
        units: list[dict[str, Any]] = []
        for block in self._absorb_whitespace_blocks(content, blocks):
            block_text = content[block["start"]:block["end"]]
            if not block_text.strip():
                # Only possible when the entire document is whitespace; still
                # cover its span, splitting to the packing target rather than
                # emitting it as one unbounded chunk.
                if self.budget.count(block_text).count <= self._pack_target_tokens:
                    ws_spans = [(block["start"], block["end"])]
                else:
                    ws_spans = _split_span_chars(block_text, block["start"], self._pack_target_tokens, self.budget)
                for start, end in ws_spans:
                    units.append({"start": start, "end": end,
                                   "hierarchy": block["hierarchy"], "title": block["title"]})
                continue

            if self.budget.count(block_text).count <= self._pack_target_tokens:
                spans = [(block["start"], block["end"])]
            else:
                spans = _split_span_paragraph(block_text, block["start"], self._pack_target_tokens, self.budget)

            for start, end in _absorb_whitespace_spans(content, spans, self._pack_target_tokens, self.budget):
                units.append({"start": start, "end": end, "hierarchy": block["hierarchy"], "title": block["title"]})

        return units

    def _merge_contiguous_units(self, content: str, units: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Greedily merge contiguous units into larger pieces while the
        combined text still fits the packing target."""
        if not units:
            return []

        pieces: list[dict[str, Any]] = []
        current = dict(units[0])

        for unit in units[1:]:
            contiguous = unit["start"] == current["end"]
            if contiguous:
                candidate_text = content[current["start"]:unit["end"]]
                if self.budget.count(candidate_text).count <= self._pack_target_tokens:
                    current["end"] = unit["end"]
                    continue

            pieces.append(current)
            current = dict(unit)

        pieces.append(current)
        return pieces

    def _add_overlap_and_finalize(self, content: str, pieces: list[dict[str, Any]],
                                   metadata: dict[str, Any], source_hash: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        overlap_texts: list[Optional[str]] = [None] * len(pieces)
        overlap_spans: list[Optional[tuple[int, int]]] = [None] * len(pieces)

        for i in range(1, len(pieces)):
            prev = pieces[i - 1]
            main_text = content[pieces[i]["start"]:pieces[i]["end"]]
            prev_text = content[prev["start"]:prev["end"]]

            remaining_room = self.budget.chunk_target_tokens - self.budget.count(main_text).count
            overlap_budget = max(0, min(self.chunk_overlap_tokens, remaining_room))

            result = _take_overlap_suffix(prev_text, prev["start"], overlap_budget, self.budget) if overlap_budget else None
            if result is None:
                continue

            abs_start, abs_end, overlap_text = result
            candidate = overlap_text + "\n\n" + main_text

            # Trim overlap further if it still doesn't fit; never sacrifice main content.
            while overlap_text and not self.budget.fits(candidate):
                shrink_target = max(0, self.budget.count(overlap_text).count - 1)
                if shrink_target <= 0:
                    overlap_text = ""
                    break
                result = _take_overlap_suffix(prev_text, prev["start"], shrink_target, self.budget)
                if result is None:
                    overlap_text = ""
                    break
                abs_start, abs_end, overlap_text = result
                candidate = overlap_text + "\n\n" + main_text

            if overlap_text:
                overlap_texts[i] = overlap_text
                overlap_spans[i] = (abs_start, abs_end)

        total = len(pieces)
        for i, piece in enumerate(pieces):
            main_text = content[piece["start"]:piece["end"]]
            overlap_text = overlap_texts[i]
            final_text = f"{overlap_text}\n\n{main_text}" if overlap_text else main_text
            token_count = self.budget.count(final_text)

            chunks.append({
                "chunk_id": i,
                "total_chunks": total,
                "content": final_text,
                "section": piece["title"] or metadata.get("title", "Document"),
                "hierarchy": piece["hierarchy"],
                "position": i,
                "token_count": token_count.count,
                "token_count_estimated": token_count.estimated,
                "overlap_with_prev": overlap_text is not None,
                "overlap_with_next": overlap_texts[i + 1] is not None if i + 1 < total else False,
                "source_span": (piece["start"], piece["end"]),
                "overlap_span": overlap_spans[i],
                "source_url": metadata.get("url", ""),
                "source_hash": source_hash,
            })

        return chunks

    def _hash_content(self, content: str) -> str:
        """Generate a hash for content deduplication."""
        return hashlib.md5(content.encode()).hexdigest()


class ChunkCache:
    """
    Simple in-memory cache for content chunks.

    Used to avoid re-chunking the same content multiple times in a session.
    For production, this could be replaced with Redis or vector store caching.
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.cache: dict[str, list[dict[str, Any]]] = {}
        self.access_order: list[str] = []

    def get(self, content_hash: str) -> Optional[list[dict[str, Any]]]:
        """Get cached chunks by content hash."""
        if content_hash in self.cache:
            # Update access order (LRU)
            self.access_order.remove(content_hash)
            self.access_order.append(content_hash)
            return self.cache[content_hash]
        return None

    def put(self, content_hash: str, chunks: list[dict[str, Any]]):
        """Store chunks in cache."""
        # Evict oldest if cache is full
        if len(self.cache) >= self.max_size and content_hash not in self.cache:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]

        self.cache[content_hash] = chunks
        if content_hash not in self.access_order:
            self.access_order.append(content_hash)

    def clear(self):
        """Clear the cache."""
        self.cache.clear()
        self.access_order.clear()
