"""
Shared token counting and embedding budget resolution.

Chunk preparation (ContentChunker) and embedding submission (ChunkManager) must
agree on exactly one effective token budget. Before this module existed, they
diverged: preparation accepted 100% of the configured budget while fallback
splitting accepted only 95%, which let content pass preparation and then get
rejected (or silently re-split) at submission time. `resolve_embedding_budget`
computes that single effective value once; both call sites should hold the
same `EmbeddingBudget` instance and use `count_tokens`/`EmbeddingBudget.fits`
instead of ad-hoc `len(text) // 3` arithmetic.

Counting prefers the model's real tokenizer (via tiktoken) and falls back to
an explicitly labeled character-ratio estimate when exact counting isn't
available. Estimated counts are NOT a guarantee of provider acceptance.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

logger = logging.getLogger(__name__)

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    tiktoken = None
    _TIKTOKEN_AVAILABLE = False

# Known provider input-token limits for embedding models, used to clamp a
# configured budget to what the provider will actually accept. This table
# must be re-verified against official provider documentation before being
# trusted for new models or during Phase 6 documentation validation; do not
# infer a limit from a provider/model name alone.
KNOWN_MODEL_INPUT_LIMITS: dict[str, int] = {
    "text-embedding-3-small": 8191,
    "text-embedding-3-large": 8191,
    "text-embedding-ada-002": 8191,
    "embed-english-v3.0": 512,
    "embed-multilingual-v3.0": 512,
    "embed-v4.0": 128000,
    "jina-embeddings-v3": 8192,
    "voyage-3": 32000,
    "voyage-3-large": 32000,
}
MODEL_LIMIT_PROVENANCE = (
    "server/utils/embedding_budget.py:KNOWN_MODEL_INPUT_LIMITS "
    "(manually curated; verify against provider docs before relying on it)"
)

# tiktoken has no native encodings for most of these models; map to the
# closest known encoding rather than claiming exact counts we can't produce.
_TIKTOKEN_MODEL_ALIASES = {
    "text-embedding-3-small": "cl100k_base",
    "text-embedding-3-large": "cl100k_base",
    "text-embedding-ada-002": "cl100k_base",
}

DEFAULT_SAFETY_MARGIN = 0.95

# Encoding objects are cached by encoding name so an offline/network-restricted
# install fails the tiktoken.get_encoding() lookup (which downloads BPE data)
# at most once per encoding, rather than retrying -- and silently re-estimating
# -- on every single count_tokens() call. Provision `TIKTOKEN_CACHE_DIR` with
# the pinned encoding files for a clean offline install to get exact counts.
_ENCODING_CACHE: dict[str, Any] = {}


def _canonical_model_id(model: Optional[str]) -> Optional[str]:
    """Strip a provider-qualified prefix (e.g. "openai/text-embedding-3-small",
    "cohere/embed-english-v3.0") down to the bare model id used by both the
    known-limit table and tiktoken's model registry.
    """
    if not model:
        return None
    return model.rsplit("/", 1)[-1]


def _resolve_encoding_name(model: Optional[str]) -> Optional[str]:
    """Resolve a tiktoken encoding name for `model` without triggering a
    network fetch: this only consults local name tables, never loads BPE data.
    """
    if not model:
        return None
    if model in _TIKTOKEN_MODEL_ALIASES:
        return _TIKTOKEN_MODEL_ALIASES[model]
    try:
        return tiktoken.model.MODEL_TO_ENCODING.get(model)
    except Exception:
        return None


def _get_encoding(encoding_name: str):
    """Load (and cache) a tiktoken encoding by name, degrading to None on failure."""
    if encoding_name in _ENCODING_CACHE:
        return _ENCODING_CACHE[encoding_name]

    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        logger.warning(
            f"tiktoken encoding '{encoding_name}' unavailable ({e}); falling back to estimated "
            f"token counts for this process. For exact offline counting, provision the pinned "
            f"encoding files (see tiktoken's TIKTOKEN_CACHE_DIR) ahead of time."
        )
        encoding = None

    _ENCODING_CACHE[encoding_name] = encoding
    return encoding


class TokenCount(NamedTuple):
    """A token count paired with whether it is an exact or estimated value."""
    count: int
    estimated: bool


def count_tokens(text: str, model: Optional[str] = None) -> TokenCount:
    """Count tokens in `text`, preferring the model's tokenizer when available.

    Falls back to a conservative character-ratio estimate (1 token ~= 3 chars)
    when tiktoken is unavailable or the model has no known encoding. The
    estimate is explicitly labeled via `TokenCount.estimated` -- it is not a
    guarantee that a provider will accept the same count.
    """
    canonical_model = _canonical_model_id(model)

    if not text:
        estimated = not (_TIKTOKEN_AVAILABLE and _resolve_encoding_name(canonical_model))
        return TokenCount(count=0, estimated=estimated)

    if _TIKTOKEN_AVAILABLE:
        encoding_name = _resolve_encoding_name(canonical_model)
        encoding = _get_encoding(encoding_name) if encoding_name else None

        if encoding is not None:
            try:
                return TokenCount(count=len(encoding.encode(text)), estimated=False)
            except Exception:
                pass

    return TokenCount(count=len(text) // 3, estimated=True)


@dataclass(frozen=True)
class EmbeddingBudget:
    """One resolved token budget shared by chunk preparation and embedding submission."""

    model: Optional[str]
    configured_max_tokens: int
    effective_max_tokens: int
    counting_mode: str  # "exact" or "estimated"
    chunk_target_tokens: int
    overlap_tokens: int
    min_chunk_tokens: int
    model_limit: Optional[int]
    model_limit_provenance: Optional[str]

    def count(self, text: str) -> TokenCount:
        return count_tokens(text, self.model)

    def fits(self, text: str) -> bool:
        """Whether `text` satisfies the effective budget for final submission."""
        return self.count(text).count <= self.effective_max_tokens


def resolve_embedding_budget(
    max_embedding_tokens: int,
    *,
    model: Optional[str] = None,
    chunk_target_tokens: Optional[int] = None,
    overlap_tokens: int = 0,
    min_chunk_tokens: Optional[int] = None,
    safety_margin: float = DEFAULT_SAFETY_MARGIN,
) -> EmbeddingBudget:
    """Resolve the single effective embedding token budget.

    Clamps `max_embedding_tokens` to the known model input limit (if any) and
    applies one safety margin, so every caller (chunk preparation and
    fallback/embedding submission) validates against the same cutoff.

    Raises:
        ValueError: for non-positive limits, invalid margins, negative
            overlap, or overlap that isn't smaller than the chunk target.
    """
    if not isinstance(max_embedding_tokens, int) or max_embedding_tokens <= 0:
        raise ValueError(f"max_embedding_tokens must be a positive integer, got {max_embedding_tokens!r}")
    if not (0 < safety_margin <= 1):
        raise ValueError(f"safety_margin must be in (0, 1], got {safety_margin!r}")
    if overlap_tokens < 0:
        raise ValueError(f"overlap_tokens must be nonnegative, got {overlap_tokens!r}")

    chunk_target_tokens = max_embedding_tokens if chunk_target_tokens is None else chunk_target_tokens
    if not isinstance(chunk_target_tokens, int) or chunk_target_tokens <= 0:
        raise ValueError(f"chunk_target_tokens must be a positive integer, got {chunk_target_tokens!r}")

    canonical_model = _canonical_model_id(model)
    model_limit = KNOWN_MODEL_INPUT_LIMITS.get(canonical_model) if canonical_model else None
    capped_max_tokens = min(max_embedding_tokens, model_limit) if model_limit else max_embedding_tokens
    effective_max_tokens = max(1, int(capped_max_tokens * safety_margin))

    # Clamp the chunk target to the effective budget *before* validating overlap
    # against it -- a model limit or safety margin can push the effective budget
    # below the configured target, and overlap must be smaller than what the
    # target actually resolves to, not the pre-clamp configured value.
    effective_chunk_target_tokens = min(chunk_target_tokens, effective_max_tokens)

    if overlap_tokens >= effective_chunk_target_tokens:
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be smaller than the effective chunk target "
            f"({effective_chunk_target_tokens}, clamped from {chunk_target_tokens})"
        )

    if min_chunk_tokens is None:
        min_chunk_tokens = 0
    elif min_chunk_tokens < 0:
        raise ValueError(f"min_chunk_tokens must be nonnegative, got {min_chunk_tokens!r}")
    # min_chunk_tokens is a soft target: it must never exceed the hard limit,
    # and it must never be used elsewhere to justify dropping short content.
    min_chunk_tokens = min(min_chunk_tokens, effective_max_tokens)

    counting_mode = "estimated" if count_tokens("probe", model).estimated else "exact"

    return EmbeddingBudget(
        model=model,
        configured_max_tokens=max_embedding_tokens,
        effective_max_tokens=effective_max_tokens,
        counting_mode=counting_mode,
        chunk_target_tokens=effective_chunk_target_tokens,
        overlap_tokens=overlap_tokens,
        min_chunk_tokens=min_chunk_tokens,
        model_limit=model_limit,
        model_limit_provenance=MODEL_LIMIT_PROVENANCE if model_limit else None,
    )


def split_text_to_budget(text: str, budget: EmbeddingBudget) -> list[str]:
    """Hard-split `text` into pieces that each satisfy `budget`.

    Splits by paragraph, then sentence, then a character-boundary fallback.
    Guarantees progress (terminates) even for tiny budgets or unsplittable
    characters.

    Raises:
        ValueError: if no valid nonempty piece can be produced at all (e.g.
            `text` is empty/whitespace-only).
    """
    text = text.strip()
    if not text:
        raise ValueError("Cannot split empty or whitespace-only text")

    if budget.fits(text):
        return [text]

    return _split_by_paragraph(text, budget)


def _split_by_paragraph(text: str, budget: EmbeddingBudget) -> list[str]:
    parts = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) <= 1:
        return _split_by_sentence(text, budget)
    return _pack_parts(parts, "\n\n", budget, _split_by_sentence)


def _split_by_sentence(text: str, budget: EmbeddingBudget) -> list[str]:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    if len(parts) <= 1:
        return _split_by_chars(text, budget)
    return _pack_parts(parts, " ", budget, _split_by_chars)


def _pack_parts(parts: list[str], joiner: str, budget: EmbeddingBudget, overflow_splitter) -> list[str]:
    pieces: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}{joiner}{part}" if current else part
        if budget.fits(candidate):
            current = candidate
            continue

        if current:
            pieces.extend(_finalize_piece(current, budget, overflow_splitter))
            current = ""

        if budget.fits(part):
            current = part
        else:
            pieces.extend(overflow_splitter(part, budget))

    if current:
        pieces.extend(_finalize_piece(current, budget, overflow_splitter))
    return pieces


def _finalize_piece(piece: str, budget: EmbeddingBudget, overflow_splitter) -> list[str]:
    piece = piece.strip()
    if not piece:
        return []
    if budget.fits(piece):
        return [piece]
    return overflow_splitter(piece, budget)


def _split_by_chars(text: str, budget: EmbeddingBudget) -> list[str]:
    """Last-resort character-boundary split; always makes progress on nonempty text."""
    text = text.strip()
    if not text:
        return []

    pieces: list[str] = []
    remaining = text
    while remaining:
        if budget.fits(remaining):
            pieces.append(remaining)
            break

        # Binary search the largest prefix that fits the effective budget.
        # best stays 0 if not even a single character fits.
        lo, hi, best = 1, len(remaining), 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if budget.fits(remaining[:mid]):
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
            if remaining[i - 1] in " \n\t.,;:!?":
                cut = i
                break

        piece = remaining[:cut].strip()
        if not piece:
            piece = remaining[:best].strip()
        if not piece:
            raise ValueError("Unable to produce a valid nonempty piece within the effective budget")

        pieces.append(piece)
        remaining = remaining[cut:].lstrip()

    if not pieces:
        raise ValueError("Unable to produce a valid nonempty piece within the effective budget")

    return pieces
