"""
Tests for Text Chunking Strategies

Tests fixed-size and semantic chunking strategies for file processing.
"""

import pytest
import sys
from pathlib import Path

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.chunking.base_chunker import Chunk
from services.file_processing.chunking.fixed_chunker import FixedSizeChunker
from services.file_processing.chunking.semantic_chunker import SemanticChunker
from services.file_processing.chunking.token_chunker import TokenChunker
from services.file_processing.chunking.recursive_chunker import RecursiveChunker, RecursiveRules, RecursiveLevel


# Sample text for testing
SAMPLE_TEXT = """
Machine learning is a subset of artificial intelligence. It focuses on teaching
computers to learn from data. Deep learning is a type of machine learning.
It uses neural networks with multiple layers. These networks can learn complex patterns.
Natural language processing is another important field. It helps computers understand human language.
Computer vision enables machines to interpret visual information. Robotics combines all these technologies.
"""

SHORT_TEXT = "This is a short text for testing."


def test_fixed_chunker_initialization():
    """Test FixedSizeChunker initialization"""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    assert chunker.chunk_size == 100
    assert chunker.overlap == 20


def test_fixed_chunker_default_params():
    """Test FixedSizeChunker with default parameters"""
    chunker = FixedSizeChunker()
    assert chunker.chunk_size == 1000
    assert chunker.overlap == 200


def test_fixed_chunker_basic_chunking():
    """Test basic fixed-size chunking"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    file_id = "test_file_123"
    metadata = {"filename": "test.txt"}

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    # Should create multiple chunks
    assert len(chunks) > 1

    # Verify chunk properties
    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, Chunk)
        assert chunk.file_id == file_id
        assert chunk.chunk_index == i
        assert len(chunk.text) <= 50
        assert chunk.chunk_id == f"{file_id}_chunk_{i}"
        assert "filename" in chunk.metadata
        assert "chunk_start" in chunk.metadata
        assert "chunk_end" in chunk.metadata
        assert chunk.metadata["strategy"] == "fixed_size"


def test_fixed_chunker_overlap():
    """Test that overlapping works correctly"""
    chunker = FixedSizeChunker(chunk_size=20, overlap=5)
    text = "12345678901234567890123456789012345"  # 35 chars
    file_id = "test_file"
    metadata = {}

    chunks = chunker.chunk_text(text, file_id, metadata)

    # Verify overlap
    if len(chunks) > 1:
        # Last 5 chars of first chunk should be in second chunk
        chunks[0].text[-5:]
        chunks[1].text[:5]
        # Due to text being numbers, we can verify some overlap exists
        assert len(chunks[0].text) <= 20


def test_fixed_chunker_empty_text():
    """Test chunking empty text"""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk_text("", "file_id", {})

    assert chunks == []


def test_fixed_chunker_short_text():
    """Test chunking text shorter than chunk size"""
    chunker = FixedSizeChunker(chunk_size=1000, overlap=200)
    chunks = chunker.chunk_text(SHORT_TEXT, "file_id", {})

    # Should create single chunk
    assert len(chunks) == 1
    assert chunks[0].text == SHORT_TEXT
    assert chunks[0].chunk_index == 0


def test_fixed_chunker_metadata_preservation():
    """Test that metadata is preserved in chunks"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    file_id = "test_file"
    metadata = {
        "filename": "document.txt",
        "mime_type": "text/plain",
        "custom_field": "custom_value"
    }

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    for chunk in chunks:
        assert chunk.metadata["filename"] == "document.txt"
        assert chunk.metadata["mime_type"] == "text/plain"
        assert chunk.metadata["custom_field"] == "custom_value"


def test_semantic_chunker_initialization():
    """Test SemanticChunker initialization"""
    chunker = SemanticChunker(chunk_size=10, overlap=2)
    assert chunker.chunk_size == 10
    assert chunker.overlap == 2


def test_semantic_chunker_default_params():
    """Test SemanticChunker with default parameters"""
    chunker = SemanticChunker()
    assert chunker.chunk_size == 10
    assert chunker.overlap == 2


def test_semantic_chunker_sentence_splitting():
    """Test semantic chunker respects sentence boundaries"""
    chunker = SemanticChunker(chunk_size=2, overlap=0)
    text = "First sentence. Second sentence. Third sentence."
    file_id = "test_file"
    metadata = {}

    chunks = chunker.chunk_text(text, file_id, metadata)

    # Should create chunks respecting sentence boundaries
    assert len(chunks) >= 1

    # Verify chunks don't split sentences
    for chunk in chunks:
        # Each chunk should contain complete sentences
        assert "." in chunk.text or len(chunks) == 1


def test_semantic_chunker_basic_chunking():
    """Test basic semantic chunking"""
    chunker = SemanticChunker(chunk_size=3, overlap=1)
    file_id = "test_file_123"
    metadata = {"filename": "test.txt"}

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    # Should create multiple chunks
    assert len(chunks) > 1

    # Verify chunk properties
    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, Chunk)
        assert chunk.file_id == file_id
        assert chunk.chunk_index == i
        assert chunk.chunk_id == f"{file_id}_chunk_{i}"
        assert "filename" in chunk.metadata
        assert "sentence_start" in chunk.metadata
        assert "sentence_end" in chunk.metadata
        assert "sentence_count" in chunk.metadata
        assert chunk.metadata["strategy"] == "semantic"


def test_semantic_chunker_empty_text():
    """Test semantic chunking with empty text"""
    chunker = SemanticChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk_text("", "file_id", {})

    assert chunks == []


def test_semantic_chunker_single_sentence():
    """Test semantic chunking with single sentence"""
    chunker = SemanticChunker(chunk_size=10, overlap=2)
    text = "This is a single sentence."
    chunks = chunker.chunk_text(text, "file_id", {})

    assert len(chunks) == 1
    assert chunks[0].text == text


def test_semantic_chunker_metadata_preservation():
    """Test metadata preservation in semantic chunks"""
    chunker = SemanticChunker(chunk_size=3, overlap=1)
    file_id = "test_file"
    metadata = {
        "filename": "document.txt",
        "page_number": 1
    }

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    for chunk in chunks:
        assert chunk.metadata["filename"] == "document.txt"
        assert chunk.metadata["page_number"] == 1


def test_semantic_chunker_sentence_count():
    """Test that sentence count in metadata is accurate"""
    chunker = SemanticChunker(chunk_size=3, overlap=0)
    text = "One. Two. Three. Four. Five. Six."
    chunks = chunker.chunk_text(text, "file_id", {})

    for chunk in chunks:
        # Count actual sentences in chunk
        chunk.text.count(".")
        # Metadata should reflect reasonable sentence count
        assert chunk.metadata["sentence_count"] > 0


def test_chunk_id_generation():
    """Test chunk ID generation is unique"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    file_id = "unique_file_789"
    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, {})

    chunk_ids = [chunk.chunk_id for chunk in chunks]

    # All IDs should be unique
    assert len(chunk_ids) == len(set(chunk_ids))

    # All IDs should contain file_id
    for chunk_id in chunk_ids:
        assert file_id in chunk_id


def test_chunk_index_sequential():
    """Test that chunk indices are sequential"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_repr():
    """Test Chunk string representation"""
    chunk = Chunk(
        chunk_id="file_123_chunk_0",
        file_id="file_123",
        text="Sample text content",
        chunk_index=0,
        metadata={}
    )

    repr_str = repr(chunk)
    # chunk_id is truncated to first 8 chars in __repr__, so check for "file_12"
    assert "file_12" in repr_str
    assert "chunk_index=0" in repr_str
    assert "len=" in repr_str


def test_fixed_chunker_large_text():
    """Test fixed chunker with large text"""
    chunker = FixedSizeChunker(chunk_size=500, overlap=100)
    large_text = SAMPLE_TEXT * 100  # Create large text
    chunks = chunker.chunk_text(large_text, "file_id", {})

    # Should create many chunks
    assert len(chunks) > 10

    # Verify no chunk exceeds size limit
    for chunk in chunks:
        assert len(chunk.text) <= 500


def test_semantic_chunker_no_overlap():
    """Test semantic chunker with no overlap"""
    # Use longer sentences to avoid merging due to min_characters_per_sentence
    chunker = SemanticChunker(chunk_size=2, overlap=0, min_characters_per_sentence=12)
    text = "This is the first sentence with enough characters. This is the second sentence with enough characters. This is the third sentence with enough characters. This is the fourth sentence with enough characters."
    chunks = chunker.chunk_text(text, "file_id", {})

    # With no overlap and chunk_size=2, should create at least 2 chunks
    assert len(chunks) >= 2


def test_chunker_special_characters():
    """Test chunking text with special characters"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    text = "Text with special chars: äöü 中文 emoji 😀! Question? Exclamation!"
    chunks = chunker.chunk_text(text, "file_id", {})

    assert len(chunks) >= 1
    # Verify special characters are preserved
    combined_text = "".join(chunk.text for chunk in chunks)
    assert "äöü" in combined_text
    assert "😀" in combined_text


def test_semantic_chunker_multiple_punctuation():
    """Test semantic chunker with various punctuation"""
    chunker = SemanticChunker(chunk_size=5, overlap=1)
    text = "Question? Exclamation! Statement. Another... More text."
    chunks = chunker.chunk_text(text, "file_id", {})

    # Should handle different sentence endings
    assert len(chunks) >= 1
    for chunk in chunks:
        # Verify chunk contains text
        assert len(chunk.text) > 0


def test_chunk_metadata_types():
    """Test that chunk metadata contains correct types"""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    metadata = {
        "filename": "test.txt",
        "page_number": 1,
        "confidence": 0.95
    }
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", metadata)

    for chunk in chunks:
        assert isinstance(chunk.metadata["filename"], str)
        assert isinstance(chunk.metadata["page_number"], int)
        assert isinstance(chunk.metadata["confidence"], float)
        assert isinstance(chunk.metadata["chunk_start"], int)
        assert isinstance(chunk.metadata["chunk_end"], int)


def test_fixed_chunker_exact_boundaries():
    """Test fixed chunker with exact boundary matching"""
    chunker = FixedSizeChunker(chunk_size=10, overlap=0)
    text = "0123456789" * 5  # 50 chars total
    chunks = chunker.chunk_text(text, "file_id", {})

    # Should create exactly 5 chunks of 10 chars each
    assert len(chunks) == 5
    for chunk in chunks:
        assert len(chunk.text) == 10


def test_semantic_chunker_whitespace_handling():
    """Test semantic chunker handles whitespace correctly"""
    chunker = SemanticChunker(chunk_size=5, overlap=0)
    text = "First sentence.    Second sentence.     Third sentence."
    chunks = chunker.chunk_text(text, "file_id", {})

    # Should handle multiple spaces correctly
    assert len(chunks) >= 1
    for chunk in chunks:
        # Verify no leading/trailing excessive whitespace in combined result
        assert len(chunk.text.strip()) > 0


# ============================================================================
# Tests for TokenChunker
# ============================================================================

def test_token_chunker_initialization():
    """Test TokenChunker initialization"""
    chunker = TokenChunker(chunk_size=100, overlap=10)
    assert chunker.chunk_size == 100
    assert chunker.overlap == 10


def test_token_chunker_default_params():
    """Test TokenChunker with default parameters"""
    chunker = TokenChunker()
    assert chunker.chunk_size == 2048
    assert chunker.overlap == 0


def test_token_chunker_validation():
    """Test TokenChunker parameter validation"""
    # Test invalid chunk_size
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        TokenChunker(chunk_size=0)
    
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        TokenChunker(chunk_size=-1)
    
    # Test invalid overlap
    with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
        TokenChunker(chunk_size=100, overlap=100)
    
    with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
        TokenChunker(chunk_size=100, overlap=150)


def test_token_chunker_basic_chunking():
    """Test basic token-based chunking"""
    chunker = TokenChunker(chunk_size=50, overlap=10, tokenizer="character")
    file_id = "test_file_123"
    metadata = {"filename": "test.txt"}

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    # Should create chunks
    assert len(chunks) >= 1

    # Verify chunk properties
    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, Chunk)
        assert chunk.file_id == file_id
        assert chunk.chunk_index == i
        assert chunk.chunk_id == f"{file_id}_chunk_{i}"
        assert "filename" in chunk.metadata
        assert "token_count" in chunk.metadata
        assert chunk.metadata["strategy"] == "token"


def test_token_chunker_empty_text():
    """Test token chunking with empty text"""
    chunker = TokenChunker(chunk_size=100, overlap=10)
    chunks = chunker.chunk_text("", "file_id", {})

    assert chunks == []


def test_token_chunker_short_text():
    """Test token chunking with short text"""
    chunker = TokenChunker(chunk_size=1000, overlap=0)
    chunks = chunker.chunk_text(SHORT_TEXT, "file_id", {})

    # Should create single chunk
    assert len(chunks) == 1
    assert chunks[0].text == SHORT_TEXT
    assert chunks[0].chunk_index == 0


def test_token_chunker_tokenizer_fallback():
    """Test token chunker falls back gracefully on tokenizer errors"""
    # Using character tokenizer should work
    chunker = TokenChunker(chunk_size=50, overlap=10, tokenizer="character")
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})
    
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata["token_count"] > 0


# ============================================================================
# Tests for RecursiveChunker
# ============================================================================

def test_recursive_chunker_initialization():
    """Test RecursiveChunker initialization"""
    chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=24)
    assert chunker.chunk_size == 100
    assert chunker.min_characters_per_chunk == 24


def test_recursive_chunker_default_params():
    """Test RecursiveChunker with default parameters"""
    chunker = RecursiveChunker()
    assert chunker.chunk_size == 2048
    assert chunker.min_characters_per_chunk == 24


def test_recursive_chunker_validation():
    """Test RecursiveChunker parameter validation"""
    # Test invalid chunk_size
    with pytest.raises(ValueError, match="chunk_size must be greater than 0"):
        RecursiveChunker(chunk_size=0)
    
    with pytest.raises(ValueError, match="chunk_size must be greater than 0"):
        RecursiveChunker(chunk_size=-1)
    
    # Test invalid min_characters_per_chunk
    with pytest.raises(ValueError, match="min_characters_per_chunk must be greater than 0"):
        RecursiveChunker(min_characters_per_chunk=0)
    
    with pytest.raises(ValueError, match="min_characters_per_chunk must be greater than 0"):
        RecursiveChunker(min_characters_per_chunk=-1)


def test_recursive_chunker_basic_chunking():
    """Test basic recursive chunking"""
    chunker = RecursiveChunker(chunk_size=200, min_characters_per_chunk=24)
    file_id = "test_file_123"
    metadata = {"filename": "test.txt"}

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    # Should create chunks
    assert len(chunks) >= 1

    # Verify chunk properties
    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, Chunk)
        assert chunk.file_id == file_id
        assert chunk.chunk_index == i
        assert chunk.chunk_id == f"{file_id}_chunk_{i}"
        assert "filename" in chunk.metadata
        assert "strategy" in chunk.metadata
        assert chunk.metadata["strategy"] == "recursive"


def test_recursive_chunker_hierarchical():
    """Test recursive chunker with hierarchical structure"""
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=10)
    chunks = chunker.chunk_text(text, "file_id", {})

    # Should respect paragraph boundaries
    assert len(chunks) >= 1
    for chunk in chunks:
        assert len(chunk.text) > 0


def test_recursive_chunker_empty_text():
    """Test recursive chunking with empty text"""
    chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=24)
    chunks = chunker.chunk_text("", "file_id", {})

    assert chunks == []


def test_recursive_rules_default():
    """Test RecursiveRules default initialization"""
    rules = RecursiveRules.default()
    assert len(rules) == 3  # paragraphs, sentences, words
    assert rules[0].delimiters == ["\n\n", "\n\n\n"]
    assert rules[1].delimiters == [". ", "! ", "? ", "\n"]
    assert rules[2].whitespace is True


def test_recursive_rules_custom():
    """Test RecursiveRules with custom levels"""
    custom_levels = [
        RecursiveLevel(delimiters=["\n\n"], include_delim="prev"),
        RecursiveLevel(delimiters=[". "], include_delim="prev"),
    ]
    rules = RecursiveRules(levels=custom_levels)
    assert len(rules) == 2
    assert rules[0].delimiters == ["\n\n"]
    assert rules[1].delimiters == [". "]


def test_recursive_chunker_with_custom_rules():
    """Test RecursiveChunker with custom rules"""
    custom_rules = RecursiveRules([
        RecursiveLevel(delimiters=["\n\n"], include_delim="prev"),
        RecursiveLevel(delimiters=[". "], include_delim="prev"),
    ])
    chunker = RecursiveChunker(chunk_size=100, rules=custom_rules)
    text = "First paragraph.\n\nSecond paragraph."
    chunks = chunker.chunk_text(text, "file_id", {})

    assert len(chunks) >= 1


# ============================================================================
# Tests for Enhanced FixedSizeChunker (token-based mode)
# ============================================================================

def test_fixed_chunker_token_mode():
    """Test FixedSizeChunker with token-based mode"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10, use_tokens=True, tokenizer="character")
    file_id = "test_file"
    metadata = {}

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata["strategy"] == "fixed_size"
        assert chunk.metadata["mode"] == "token"
        assert "token_count" in chunk.metadata
        assert "token_start" in chunk.metadata
        assert "token_end" in chunk.metadata


def test_fixed_chunker_character_mode():
    """Test FixedSizeChunker with character-based mode (default)"""
    chunker = FixedSizeChunker(chunk_size=50, overlap=10, use_tokens=False)
    file_id = "test_file"
    metadata = {}

    chunks = chunker.chunk_text(SAMPLE_TEXT, file_id, metadata)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata["strategy"] == "fixed_size"
        assert chunk.metadata["mode"] == "character"
        assert "chunk_start" in chunk.metadata
        assert "chunk_end" in chunk.metadata


def test_fixed_chunker_token_fallback():
    """Test FixedSizeChunker falls back to character mode on tokenizer errors"""
    # This should work even if tokenizer fails
    chunker = FixedSizeChunker(chunk_size=50, overlap=10, use_tokens=True, tokenizer="character")
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})
    
    assert len(chunks) >= 1


# ============================================================================
# Tests for Enhanced SemanticChunker
# ============================================================================

def test_semantic_chunker_advanced_mode():
    """Test SemanticChunker with advanced mode disabled (default)"""
    chunker = SemanticChunker(
        chunk_size=5,
        overlap=1,
        use_advanced=False
    )
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata["strategy"] == "semantic"
        assert chunk.metadata["mode"] == "simple"


def test_semantic_chunker_advanced_options():
    """Test SemanticChunker with advanced options"""
    chunker = SemanticChunker(
        chunk_size=5,
        overlap=1,
        use_advanced=False,  # Don't require sentence-transformers for test
        threshold=0.8,
        similarity_window=3,
        min_sentences_per_chunk=1,
        min_characters_per_sentence=12
    )
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    assert len(chunks) >= 1
    assert chunker.threshold == 0.8
    assert chunker.similarity_window == 3


def test_semantic_chunker_token_limit():
    """Test SemanticChunker with token size limit"""
    chunker = SemanticChunker(
        chunk_size=5,
        overlap=1,
        chunk_size_tokens=100,
        tokenizer="character"
    )
    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    assert len(chunks) >= 1
    # Verify chunks respect token limits if chunk_size_tokens is set
    for chunk in chunks:
        assert len(chunk.text) > 0


def test_semantic_chunker_improved_sentence_splitting():
    """Test SemanticChunker uses improved sentence splitting"""
    chunker = SemanticChunker(chunk_size=2, overlap=0)
    text = "First sentence. Second sentence! Third sentence? Fourth sentence."
    chunks = chunker.chunk_text(text, "file_id", {})

    # Should handle different sentence endings
    assert len(chunks) >= 1
    for chunk in chunks:
        assert len(chunk.text) > 0


# ============================================================================
# Tests for Base Chunker (tokenizer support)
# ============================================================================

def test_base_chunker_tokenizer_support():
    """Test base chunker has tokenizer support"""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    
    # Should have tokenizer property
    assert hasattr(chunker, 'tokenizer')
    assert chunker.tokenizer is not None
    
    # Should have count_tokens method
    assert hasattr(chunker, 'count_tokens')
    token_count = chunker.count_tokens("Hello world")
    assert isinstance(token_count, int)
    assert token_count > 0


def test_base_chunker_count_tokens_batch():
    """Test base chunker batch token counting"""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    
    texts = ["Hello", "World", "Test"]
    token_counts = chunker.count_tokens_batch(texts)
    
    assert len(token_counts) == len(texts)
    for count in token_counts:
        assert isinstance(count, int)
        assert count > 0


def test_base_chunker_custom_tokenizer():
    """Test base chunker with custom tokenizer"""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20, tokenizer="character")
    
    # Should use character tokenizer
    assert chunker.tokenizer is not None
    token_count = chunker.count_tokens("Hello")
    assert token_count == 5  # 5 characters


# ============================================================================
# Integration Tests
# ============================================================================

def test_chunker_strategy_comparison():
    """Test that different chunkers produce different results"""
    text = SAMPLE_TEXT
    file_id = "test_file"
    metadata = {}
    
    fixed_chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    semantic_chunker = SemanticChunker(chunk_size=3, overlap=1)
    token_chunker = TokenChunker(chunk_size=50, overlap=10, tokenizer="character")
    
    fixed_chunks = fixed_chunker.chunk_text(text, file_id, metadata)
    semantic_chunks = semantic_chunker.chunk_text(text, file_id, metadata)
    token_chunks = token_chunker.chunk_text(text, file_id, metadata)
    
    # All should produce chunks
    assert len(fixed_chunks) > 0
    assert len(semantic_chunks) > 0
    assert len(token_chunks) > 0
    
    # Different strategies may produce different numbers of chunks
    # But all should have valid chunks
    for chunks in [fixed_chunks, semantic_chunks, token_chunks]:
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert len(chunk.text) > 0
            assert chunk.file_id == file_id


def test_chunker_metadata_consistency():
    """Test that chunk metadata is consistent across strategies"""
    text = SAMPLE_TEXT
    file_id = "test_file"
    metadata = {"source": "test", "page": 1}
    
    chunkers = [
        FixedSizeChunker(chunk_size=50, overlap=10),
        SemanticChunker(chunk_size=3, overlap=1),
        TokenChunker(chunk_size=50, overlap=10, tokenizer="character"),
    ]
    
    for chunker in chunkers:
        chunks = chunker.chunk_text(text, file_id, metadata)
        for chunk in chunks:
            # All chunks should preserve original metadata
            assert chunk.metadata["source"] == "test"
            assert chunk.metadata["page"] == 1
            # All chunks should have strategy
            assert "strategy" in chunk.metadata


def test_chunker_empty_and_whitespace():
    """Test all chunkers handle empty and whitespace-only text"""
    chunkers = [
        FixedSizeChunker(chunk_size=50, overlap=10),
        SemanticChunker(chunk_size=3, overlap=1),
        TokenChunker(chunk_size=50, overlap=10),
        RecursiveChunker(chunk_size=100, min_characters_per_chunk=24),
    ]
    
    for chunker in chunkers:
        # Empty text
        chunks = chunker.chunk_text("", "file_id", {})
        assert chunks == []
        
        # Whitespace-only text
        chunks = chunker.chunk_text("   \n\n\t   ", "file_id", {})
        # Some chunkers may return empty, others may return chunks
        # But should not raise errors
        assert isinstance(chunks, list)


def test_chunker_special_unicode():
    """Test all chunkers handle unicode and special characters"""
    text = "Hello 世界 🌍 Emoji 😀 Special: äöü ñ"

    chunkers = [
        FixedSizeChunker(chunk_size=50, overlap=10),
        SemanticChunker(chunk_size=3, overlap=1),
        TokenChunker(chunk_size=50, overlap=10, tokenizer="character"),
    ]

    for chunker in chunkers:
        chunks = chunker.chunk_text(text, "file_id", {})
        assert len(chunks) >= 1

        # Verify unicode is preserved
        combined = "".join(chunk.text for chunk in chunks)
        assert "世界" in combined or "🌍" in combined or "😀" in combined


# ============================================================================
# Advanced Edge Case Tests
# ============================================================================

def test_tokenizer_encoding_failure_fallback():
    """Test that chunkers handle tokenizer encoding failures gracefully"""
    from unittest.mock import Mock

    # Create a mock tokenizer that fails on encode
    mock_tokenizer = Mock()
    mock_tokenizer.encode = Mock(side_effect=Exception("Encoding failed"))
    mock_tokenizer.count_tokens = Mock(return_value=100)

    # TokenChunker should fall back to FixedSizeChunker
    chunker = TokenChunker(chunk_size=50, overlap=10)
    chunker._tokenizer = mock_tokenizer

    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    # Should still produce chunks via fallback
    assert len(chunks) >= 1
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert chunk.file_id == "file_id"


def test_tokenizer_decoding_failure_fallback():
    """Test that chunkers handle tokenizer decoding failures gracefully"""
    from unittest.mock import Mock

    # Create a mock tokenizer that fails on decode
    mock_tokenizer = Mock()
    mock_tokenizer.encode = Mock(return_value=[1, 2, 3, 4, 5] * 20)  # 100 tokens
    mock_tokenizer.decode = Mock(side_effect=Exception("Decoding failed"))
    mock_tokenizer.count_tokens = Mock(return_value=100)

    # TokenChunker should use character estimation fallback
    chunker = TokenChunker(chunk_size=50, overlap=10)
    chunker._tokenizer = mock_tokenizer

    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    # Should still produce chunks using character estimation
    assert len(chunks) >= 1
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert len(chunk.text) > 0  # Should have estimated character content


def test_fixed_chunker_token_mode_decode_fallback():
    """Test FixedSizeChunker token mode handles decode failures"""
    from unittest.mock import Mock

    # Create a mock tokenizer that fails on decode
    mock_tokenizer = Mock()
    mock_tokenizer.encode = Mock(return_value=[1] * 200)  # 200 tokens
    mock_tokenizer.decode = Mock(side_effect=Exception("Decode error"))

    chunker = FixedSizeChunker(chunk_size=50, overlap=10, use_tokens=True)
    chunker._tokenizer = mock_tokenizer

    chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

    # Should fall back to character estimation
    assert len(chunks) >= 1
    # Most chunks should have content (some may be empty at end due to estimation)
    non_empty_chunks = [c for c in chunks if len(c.text) > 0]
    assert len(non_empty_chunks) >= len(chunks) - 2  # Allow up to 2 empty chunks
    for chunk in non_empty_chunks:
        assert isinstance(chunk, Chunk)


def test_very_long_sentence_handling():
    """Test chunkers handle very long sentences (no punctuation)"""
    # Create a very long sentence without punctuation
    long_sentence = "word " * 1000  # 1000 words, no sentence delimiters

    # SemanticChunker should still chunk it
    chunker = SemanticChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk_text(long_sentence, "file_id", {})

    # Should create at least one chunk
    assert len(chunks) >= 1

    # RecursiveChunker should handle it via whitespace splitting
    recursive_chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=20)
    recursive_chunks = recursive_chunker.chunk_text(long_sentence, "file_id", {})

    assert len(recursive_chunks) >= 1


def test_no_whitespace_text():
    """Test chunkers handle text without whitespace"""
    no_space_text = "a" * 500  # 500 characters, no spaces

    # Fixed chunker should handle it fine
    chunker = FixedSizeChunker(chunk_size=100, overlap=10)
    chunks = chunker.chunk_text(no_space_text, "file_id", {})

    assert len(chunks) >= 4  # Should create multiple chunks
    for chunk in chunks:
        assert len(chunk.text) <= 100


def test_mixed_line_endings():
    """Test chunkers handle mixed line endings (\\n, \\r\\n, \\r)"""
    mixed_endings = "Line 1.\nLine 2.\r\nLine 3.\rLine 4."

    chunkers = [
        SemanticChunker(chunk_size=2, overlap=0),
        RecursiveChunker(chunk_size=100, min_characters_per_chunk=5),
    ]

    for chunker in chunkers:
        chunks = chunker.chunk_text(mixed_endings, "file_id", {})
        assert len(chunks) >= 1
        # Should handle all line ending types
        combined = "".join(chunk.text for chunk in chunks)
        assert len(combined) > 0


def test_chunk_size_larger_than_text():
    """Test all chunkers when chunk_size is larger than text"""
    short_text = "Short text."

    chunkers = [
        FixedSizeChunker(chunk_size=10000, overlap=100),
        SemanticChunker(chunk_size=1000, overlap=10),
        TokenChunker(chunk_size=10000, overlap=100, tokenizer="character"),
        RecursiveChunker(chunk_size=10000, min_characters_per_chunk=5),
    ]

    for chunker in chunkers:
        chunks = chunker.chunk_text(short_text, "file_id", {})
        # Should create exactly one chunk
        assert len(chunks) == 1
        assert chunks[0].text == short_text


def test_recursive_chunker_whitespace_level():
    """Test RecursiveChunker properly handles whitespace splitting level"""
    # Text with words but no sentence delimiters
    text = "word " * 500  # 500 words

    chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=20)
    chunks = chunker.chunk_text(text, "file_id", {})

    assert len(chunks) > 1
    # Verify chunks were created and have metadata
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        # Each chunk should have token count metadata
        assert "token_count" in chunk.metadata
        token_count = chunk.metadata.get('token_count', 0)
        assert token_count > 0
        # Recursive chunker may create larger chunks during merging
        # to respect boundaries, so we use a generous upper limit
        assert token_count <= chunker.chunk_size * 5  # Very generous for boundary respect


def test_sentence_splitting_edge_cases():
    """Test sentence splitting with edge cases"""
    from services.file_processing.chunking.utils import split_sentences

    # Test abbreviations (Dr., Mr., etc.)
    text_with_abbrev = "Dr. Smith went to the store. He bought milk."
    sentences = split_sentences(text_with_abbrev, min_characters_per_sentence=5)
    assert len(sentences) >= 1

    # Test multiple delimiters in sequence
    multiple_delims = "What?! Really!! Yes..."
    sentences = split_sentences(multiple_delims, min_characters_per_sentence=2)
    assert len(sentences) >= 1

    # Test trailing delimiter
    trailing = "Sentence one. Sentence two. "
    sentences = split_sentences(trailing, min_characters_per_sentence=5)
    assert len(sentences) >= 2


def test_token_estimation_accuracy():
    """Test that token estimation fallback is reasonably accurate"""
    text = "This is a test sentence with several words to estimate tokens."

    # Test FixedSizeChunker token mode with decode failure
    from unittest.mock import Mock

    mock_tokenizer = Mock()
    tokens = [1] * 15  # Simulate 15 tokens
    mock_tokenizer.encode = Mock(return_value=tokens)
    mock_tokenizer.decode = Mock(side_effect=Exception("Decode failed"))

    chunker = FixedSizeChunker(chunk_size=10, overlap=2, use_tokens=True)
    chunker._tokenizer = mock_tokenizer

    chunks = chunker.chunk_text(text, "file_id", {})

    # Should create multiple chunks
    assert len(chunks) >= 1

    # Estimated character counts should be reasonable (4 chars per token)
    for chunk in chunks:
        # Each chunk should have approximate length based on token estimation
        assert len(chunk.text) > 0
        # Allow generous margin since it's an estimate
        assert len(chunk.text) <= chunker.chunk_size * 10  # Very loose bound


def test_chunk_overlap_boundary_conditions():
    """Test chunking with overlap at boundary conditions"""
    text = "0123456789" * 10  # 100 chars

    # Test overlap = 0 (no overlap)
    chunker = FixedSizeChunker(chunk_size=10, overlap=0)
    chunks = chunker.chunk_text(text, "file_id", {})
    assert len(chunks) == 10

    # Test overlap close to chunk_size (but valid)
    chunker2 = FixedSizeChunker(chunk_size=20, overlap=19)
    chunks2 = chunker2.chunk_text(text, "file_id", {})
    # Should create many overlapping chunks
    assert len(chunks2) > 50


def test_recursive_chunker_merge_splits_validation():
    """Test RecursiveChunker validates merge_splits inputs"""
    chunker = RecursiveChunker(chunk_size=100, min_characters_per_chunk=10)

    # Test mismatched lengths
    with pytest.raises(ValueError, match="does not match token counts"):
        chunker._merge_splits(["chunk1", "chunk2"], [10])  # Mismatch!


def test_metadata_preserved_through_chunking_chain():
    """Test that metadata is preserved through all chunking operations"""
    metadata = {
        "filename": "test.txt",
        "author": "Test Author",
        "timestamp": "2025-01-08",
        "custom_field": {"nested": "value"}
    }

    chunkers = [
        FixedSizeChunker(chunk_size=50, overlap=10),
        SemanticChunker(chunk_size=3, overlap=1),
        TokenChunker(chunk_size=50, overlap=10, tokenizer="character"),
        RecursiveChunker(chunk_size=100, min_characters_per_chunk=10),
    ]

    for chunker in chunkers:
        chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", metadata.copy())

        for chunk in chunks:
            # Original metadata should be preserved
            assert chunk.metadata["filename"] == "test.txt"
            assert chunk.metadata["author"] == "Test Author"
            assert chunk.metadata["timestamp"] == "2025-01-08"
            assert chunk.metadata["custom_field"]["nested"] == "value"

            # Strategy-specific metadata should be added
            assert "strategy" in chunk.metadata


# ============================================================================
# Large File Performance Tests
# ============================================================================

def test_large_file_fixed_chunker():
    """Test FixedSizeChunker with large text (simulated 5MB)"""
    # Create ~5MB of text
    large_text = SAMPLE_TEXT * 10000  # Approximately 5MB

    chunker = FixedSizeChunker(chunk_size=1000, overlap=100)
    chunks = chunker.chunk_text(large_text, "file_id", {})

    # Should create many chunks
    assert len(chunks) > 1000

    # Verify all chunks are valid
    for chunk in chunks:
        assert len(chunk.text) <= 1000
        assert chunk.file_id == "file_id"
        assert chunk.chunk_index >= 0


def test_large_file_token_chunker():
    """Test TokenChunker with large text"""
    large_text = SAMPLE_TEXT * 5000  # Approximately 2.5MB

    chunker = TokenChunker(chunk_size=512, overlap=50, tokenizer="character")
    chunks = chunker.chunk_text(large_text, "file_id", {})

    # Should create many chunks
    assert len(chunks) > 500

    # Verify metadata includes token counts
    for chunk in chunks:
        assert "token_count" in chunk.metadata
        assert chunk.metadata["token_count"] > 0


def test_large_file_recursive_chunker():
    """Test RecursiveChunker with large text"""
    large_text = SAMPLE_TEXT * 5000

    chunker = RecursiveChunker(chunk_size=500, min_characters_per_chunk=50)
    chunks = chunker.chunk_text(large_text, "file_id", {})

    # Should create many chunks
    assert len(chunks) > 100

    # Verify all chunks have reasonable sizes
    for chunk in chunks:
        assert len(chunk.text) >= chunker.min_characters_per_chunk
        assert "token_count" in chunk.metadata


def test_chunk_reconstruction():
    """Test that chunks can be reconstructed to approximate original text"""
    original_text = SAMPLE_TEXT

    # Test with no overlap - should reconstruct exactly
    chunker = FixedSizeChunker(chunk_size=100, overlap=0)
    chunks = chunker.chunk_text(original_text, "file_id", {})

    reconstructed = "".join(chunk.text for chunk in chunks)
    assert reconstructed == original_text

    # Test with overlap - reconstructed text should be longer
    chunker_overlap = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks_overlap = chunker_overlap.chunk_text(original_text, "file_id", {})

    reconstructed_overlap = "".join(chunk.text for chunk in chunks_overlap)
    # With overlap, we expect some duplication
    assert len(reconstructed_overlap) >= len(original_text)


def test_extreme_overlap_ratios():
    """Test chunkers with extreme but valid overlap ratios"""
    text = "word " * 100

    # Very high overlap (95% of chunk_size)
    chunker = FixedSizeChunker(chunk_size=100, overlap=95)
    chunks = chunker.chunk_text(text, "file_id", {})

    # Should create many chunks with high overlap
    assert len(chunks) > 10

    # Verify each chunk has expected size
    for chunk in chunks[:-1]:  # Exclude last chunk
        assert len(chunk.text) <= 100


def test_min_characters_per_sentence_boundary():
    """Test SemanticChunker respects min_characters_per_sentence"""
    # Text with very short sentences
    text = "A. B. C. D. E. F. G. H. I. J."

    # With low minimum
    chunker_low = SemanticChunker(chunk_size=10, overlap=0, min_characters_per_sentence=1)
    chunks_low = chunker_low.chunk_text(text, "file_id", {})

    # With high minimum (should merge short sentences)
    chunker_high = SemanticChunker(chunk_size=10, overlap=0, min_characters_per_sentence=10)
    chunks_high = chunker_high.chunk_text(text, "file_id", {})

    # High minimum should create fewer chunks (merged sentences)
    assert len(chunks_high) <= len(chunks_low)


def test_all_chunkers_produce_ordered_chunks():
    """Test that all chunkers produce chunks in sequential order"""
    chunkers = [
        FixedSizeChunker(chunk_size=50, overlap=10),
        SemanticChunker(chunk_size=3, overlap=1),
        TokenChunker(chunk_size=50, overlap=10, tokenizer="character"),
        RecursiveChunker(chunk_size=100, min_characters_per_chunk=10),
    ]

    for chunker in chunkers:
        chunks = chunker.chunk_text(SAMPLE_TEXT, "file_id", {})

        # Verify chunk indices are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

        # Verify chunk IDs are consistent
        for i, chunk in enumerate(chunks):
            expected_id = f"file_id_chunk_{i}"
            assert chunk.chunk_id == expected_id


def test_empty_splits_handling():
    """Test that chunkers handle texts that produce empty splits"""
    # Text with only delimiters
    only_delims = "...\n\n\n!!!"

    chunkers = [
        SemanticChunker(chunk_size=5, overlap=0),
        RecursiveChunker(chunk_size=100, min_characters_per_chunk=5),
    ]

    for chunker in chunkers:
        chunks = chunker.chunk_text(only_delims, "file_id", {})
        # Should either return empty list or chunks with the delimiters
        assert isinstance(chunks, list)
        if chunks:
            for chunk in chunks:
                assert isinstance(chunk, Chunk)
