"""
Tests for BlockAwareStreamer.

This module tests the block-aware streaming utility that buffers code blocks
while streaming normal text immediately.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.block_aware_streamer import BlockAwareStreamer, StreamChunk, StreamerMode


class TestBlockAwareStreamer:
    """Test suite for BlockAwareStreamer."""

    def test_immediate_streaming_basic(self):
        """Test that normal text streams immediately."""
        streamer = BlockAwareStreamer()

        # Simulate token-by-token input - should stream immediately
        chunks = []
        chunks.extend(streamer.add_text("Hello "))
        chunks.extend(streamer.add_text("world"))
        chunks.extend(streamer.add_text("!"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        # Verify content preserved
        combined = "".join(c.content for c in chunks)
        assert combined == "Hello world!"
        # Should have multiple chunks (streamed immediately)
        assert len(chunks) >= 1

    def test_immediate_streaming_tokens(self):
        """Test streaming with partial tokens (like LLM output)."""
        streamer = BlockAwareStreamer()

        chunks = []
        # Simulate LLM tokens that don't align with word boundaries
        for token in ["The", " qui", "ck ", "bro", "wn", " fox"]:
            chunks.extend(streamer.add_text(token))
        final = streamer.flush()
        if final:
            chunks.append(final)

        combined = "".join(c.content for c in chunks)
        assert combined == "The quick brown fox"

    def test_code_block_buffering_complete(self):
        """Test that code blocks are buffered completely."""
        streamer = BlockAwareStreamer()

        chunks = []
        # Send code block in pieces
        chunks.extend(streamer.add_text("Here is code:\n"))
        chunks.extend(streamer.add_text("```python\n"))
        chunks.extend(streamer.add_text("def hello():\n"))
        chunks.extend(streamer.add_text("    print('hi')\n"))
        chunks.extend(streamer.add_text("```\n"))
        chunks.extend(streamer.add_text("End."))
        final = streamer.flush()
        if final:
            chunks.append(final)

        # Should have at least one code block chunk
        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 1
        assert "def hello():" in code_chunks[0].content
        assert code_chunks[0].language == "python"

    def test_code_block_without_language(self):
        """Test code blocks without language specifier."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("```\n"))
        chunks.extend(streamer.add_text("some code\n"))
        chunks.extend(streamer.add_text("```\n"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 1
        assert code_chunks[0].language is None
        assert "some code" in code_chunks[0].content

    def test_multiple_code_blocks(self):
        """Test handling multiple code blocks in sequence."""
        streamer = BlockAwareStreamer()

        chunks = []
        # First code block
        chunks.extend(streamer.add_text("```python\ncode1\n```\n"))
        # Text between
        chunks.extend(streamer.add_text("Some text "))
        # Second code block
        chunks.extend(streamer.add_text("```javascript\ncode2\n```\n"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 2
        assert code_chunks[0].language == "python"
        assert code_chunks[1].language == "javascript"

    def test_partial_backticks_at_boundary(self):
        """Test handling of partial ``` at chunk boundary."""
        streamer = BlockAwareStreamer()

        chunks = []
        # Send text ending with partial backticks
        chunks.extend(streamer.add_text("text\n`"))
        chunks.extend(streamer.add_text("``python\ncode\n```"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        # Should correctly identify code block despite split
        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 1

    def test_inline_backticks_not_treated_as_block(self):
        """Test that inline `code` is not buffered as a block."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("Use `inline code` here "))
        final = streamer.flush()
        if final:
            chunks.append(final)

        # No code blocks should be detected (inline backticks)
        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 0

        # Content should be preserved
        combined = "".join(c.content for c in chunks)
        assert "`inline code`" in combined

    def test_backticks_not_at_line_start(self):
        """Test that ``` not at line start is not treated as block."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("some text ``` not a block"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        # Should not create code block
        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 0

    def test_max_buffer_protection(self):
        """Test that very long content forces flush."""
        streamer = BlockAwareStreamer(max_buffer_size=100)

        # Send content larger than max buffer
        long_text = "a" * 150
        chunks = streamer.add_text(long_text)

        # Should have forced a flush
        assert len(chunks) > 0
        assert streamer.buffer == ""

    def test_flush_returns_remaining(self):
        """Test that flush returns remaining buffered content."""
        streamer = BlockAwareStreamer()

        # Add text that ends with potential code block start
        streamer.add_text("text\n```")
        # Buffer should hold the backticks
        assert "```" in streamer.buffer

        # Flush should return it
        remaining = streamer.flush()
        assert remaining is not None
        assert "```" in remaining.content
        assert streamer.buffer == ""

    def test_flush_empty_buffer(self):
        """Test that flush returns None for empty buffer."""
        streamer = BlockAwareStreamer()
        assert streamer.flush() is None

    def test_is_in_code_block(self):
        """Test is_in_code_block state tracking."""
        streamer = BlockAwareStreamer()

        assert not streamer.is_in_code_block()

        # Enter code block
        streamer.add_text("```python\n")
        assert streamer.is_in_code_block()

        # Still in code block
        streamer.add_text("code here\n")
        assert streamer.is_in_code_block()

        # Exit code block
        streamer.add_text("```\n")
        assert not streamer.is_in_code_block()

    def test_reset(self):
        """Test reset clears all state."""
        streamer = BlockAwareStreamer()

        streamer.add_text("```python\ncode")
        assert streamer.buffer != ""
        assert streamer.is_in_code_block()

        streamer.reset()
        assert streamer.buffer == ""
        assert not streamer.is_in_code_block()
        assert streamer.code_block_language is None

    def test_chart_block(self):
        """Test chart blocks are buffered correctly."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("Here's a chart:\n"))
        chunks.extend(streamer.add_text("```chart\n"))
        chunks.extend(streamer.add_text("type: bar\n"))
        chunks.extend(streamer.add_text("data: [1,2,3]\n"))
        chunks.extend(streamer.add_text("```\n"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 1
        assert code_chunks[0].language == "chart"
        assert "type: bar" in code_chunks[0].content

    def test_mermaid_block(self):
        """Test mermaid diagram blocks are buffered correctly."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("```mermaid\n"))
        chunks.extend(streamer.add_text("graph TD\n"))
        chunks.extend(streamer.add_text("    A-->B\n"))
        chunks.extend(streamer.add_text("```\n"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        code_chunks = [c for c in chunks if c.is_code_block]
        assert len(code_chunks) == 1
        assert code_chunks[0].language == "mermaid"

    def test_incomplete_code_block_at_end(self):
        """Test incomplete code block at stream end is flushed."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("```python\n"))
        chunks.extend(streamer.add_text("incomplete code"))
        # No closing ``` - stream ends

        final = streamer.flush()
        assert final is not None
        assert final.is_code_block
        assert "incomplete code" in final.content

    def test_empty_input(self):
        """Test empty string input is handled."""
        streamer = BlockAwareStreamer()
        chunks = streamer.add_text("")
        assert chunks == []

    def test_whitespace_only(self):
        """Test whitespace-only input."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("   "))
        chunks.extend(streamer.add_text("\n"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        combined = "".join(c.content for c in chunks)
        assert combined == "   \n"

    def test_newlines_in_text(self):
        """Test newlines in normal text are preserved and streamed."""
        streamer = BlockAwareStreamer()

        chunks = []
        chunks.extend(streamer.add_text("Line 1\n"))
        chunks.extend(streamer.add_text("Line 2\n"))
        final = streamer.flush()
        if final:
            chunks.append(final)

        combined = "".join(c.content for c in chunks)
        assert "Line 1\n" in combined
        assert "Line 2" in combined

    def test_text_before_code_block_streams_immediately(self):
        """Test that text before a code block is streamed before buffering starts."""
        streamer = BlockAwareStreamer()

        chunks = []
        # Send text followed by code block start
        chunks.extend(streamer.add_text("Here is some text\n```python\n"))

        # Text before code block should be yielded
        text_chunks = [c for c in chunks if not c.is_code_block]
        assert len(text_chunks) >= 1
        combined_text = "".join(c.content for c in text_chunks)
        assert "Here is some text" in combined_text

        # Should be in code block mode now
        assert streamer.is_in_code_block()


class TestStreamChunk:
    """Test StreamChunk dataclass."""

    def test_defaults(self):
        """Test default values."""
        chunk = StreamChunk(content="test")
        assert chunk.content == "test"
        assert chunk.is_code_block is False
        assert chunk.language is None

    def test_code_block_chunk(self):
        """Test code block chunk."""
        chunk = StreamChunk(
            content="```python\ncode\n```",
            is_code_block=True,
            language="python"
        )
        assert chunk.is_code_block is True
        assert chunk.language == "python"


class TestStreamerMode:
    """Test StreamerMode enum."""

    def test_modes(self):
        """Test mode values."""
        assert StreamerMode.NORMAL.value == "normal"
        assert StreamerMode.CODE_BLOCK.value == "code"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
