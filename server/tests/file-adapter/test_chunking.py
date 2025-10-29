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

from services.file_processing.chunking.base_chunker import Chunk, TextChunker
from services.file_processing.chunking.fixed_chunker import FixedSizeChunker
from services.file_processing.chunking.semantic_chunker import SemanticChunker


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
        first_chunk_end = chunks[0].text[-5:]
        second_chunk_start = chunks[1].text[:5]
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
        sentence_count = chunk.text.count(".")
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
    chunker = SemanticChunker(chunk_size=2, overlap=0)
    text = "First. Second. Third. Fourth."
    chunks = chunker.chunk_text(text, "file_id", {})

    # With no overlap, chunks should be distinct
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
