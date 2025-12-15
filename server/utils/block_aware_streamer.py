"""
Block-aware streaming utility for smart buffering of code blocks.

This module provides utilities to buffer code blocks until complete while streaming
normal text immediately for optimal user experience during LLM response streaming.
"""

import re
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class StreamerMode(Enum):
    """Current buffering mode for the streamer."""
    NORMAL = "normal"      # Immediate streaming (pass-through)
    CODE_BLOCK = "code"    # Buffering code block until complete


@dataclass
class StreamChunk:
    """Represents a streamable chunk of content."""
    content: str
    is_code_block: bool = False
    language: Optional[str] = None  # For code blocks: python, javascript, etc.


class BlockAwareStreamer:
    """
    Streams text immediately while buffering code blocks until complete.

    - Normal text: Streamed immediately as received (pass-through)
    - Code blocks: Buffered until closing ``` is received, then sent as one chunk

    This ensures code blocks, charts, and mermaid diagrams render correctly
    while text appears in real-time like ChatGPT/Claude.

    Example usage:
        streamer = BlockAwareStreamer()
        for token in llm_tokens:
            chunks = streamer.add_text(token)
            for chunk in chunks:
                yield chunk.content
        # At end, flush remaining
        remaining = streamer.flush()
        if remaining:
            yield remaining.content
    """

    def __init__(self, max_buffer_size: int = 1_000_000):
        """
        Initialize the block-aware streamer.

        Args:
            max_buffer_size: Maximum buffer size in characters (default 1MB).
                            Prevents memory issues with malformed responses.
        """
        self.buffer = ""
        self.mode = StreamerMode.NORMAL
        self.code_block_language: Optional[str] = None
        self.max_buffer_size = max_buffer_size

    def add_text(self, new_text: str) -> List[StreamChunk]:
        """
        Add new text and return chunks ready for streaming.

        In NORMAL mode: Text is streamed immediately (with minimal buffering
        only to detect code block starts).

        In CODE_BLOCK mode: Text is buffered until the closing ``` is found.

        Args:
            new_text: New text token/chunk from LLM

        Returns:
            List of StreamChunk objects ready to be streamed
        """
        if not new_text:
            return []

        self.buffer += new_text
        chunks: List[StreamChunk] = []

        # Safety check: prevent unbounded memory growth
        if len(self.buffer) > self.max_buffer_size:
            # Force flush to prevent memory issues
            chunks.append(StreamChunk(
                content=self.buffer,
                is_code_block=(self.mode == StreamerMode.CODE_BLOCK),
                language=self.code_block_language if self.mode == StreamerMode.CODE_BLOCK else None
            ))
            self.buffer = ""
            self.mode = StreamerMode.NORMAL
            self.code_block_language = None
            return chunks

        # Process buffer based on current mode
        while True:
            if self.mode == StreamerMode.NORMAL:
                result = self._process_normal_mode()
            else:
                result = self._process_code_block_mode()

            if result is None:
                break
            chunks.append(result)

        return chunks

    def _process_normal_mode(self) -> Optional[StreamChunk]:
        """
        Process buffer in normal (immediate streaming) mode.

        Streams text immediately, only buffering when we detect
        the potential start of a code block.

        Returns:
            StreamChunk if content ready, None if still buffering
        """
        if not self.buffer:
            return None

        # Check for code block start (``` at line start)
        code_start_idx = self._find_code_block_start()

        if code_start_idx is not None:
            # Found code block start
            if code_start_idx > 0:
                # Yield text before the code block immediately
                text_before = self.buffer[:code_start_idx]
                self.buffer = self.buffer[code_start_idx:]
                return StreamChunk(content=text_before, is_code_block=False)

            # Buffer starts with ``` - check if we have the full opening line
            newline_idx = self.buffer.find('\n')
            if newline_idx == -1:
                # Haven't received full opening line yet, keep buffering
                return None

            # Extract language specifier (if any)
            opening_line = self.buffer[:newline_idx]
            match = re.match(r'^```(\w*)', opening_line)
            if match:
                self.code_block_language = match.group(1) if match.group(1) else None
                self.mode = StreamerMode.CODE_BLOCK
                # Don't yield anything yet - continue buffering the code block
                return None

        # Check for potential code block start at the end of buffer
        # (partial ``` that might become a full code block)
        safe_content = self._get_safe_content_to_stream()

        if safe_content:
            self.buffer = self.buffer[len(safe_content):]
            return StreamChunk(content=safe_content, is_code_block=False)

        return None

    def _get_safe_content_to_stream(self) -> str:
        """
        Get content that's safe to stream immediately.

        Holds back any trailing characters that might be the start of a code block.

        Returns:
            Content safe to stream (may be empty if we need to wait)
        """
        if not self.buffer:
            return ""

        # Find the last newline - everything before it is safe if no ``` found
        last_newline = self.buffer.rfind('\n')

        if last_newline == -1:
            # No newline - check if buffer could be start of code block
            # Only hold back if it's just backticks
            if self.buffer in ('`', '``', '```'):
                return ""
            if self.buffer.startswith('```'):
                # Might be code block start, need to wait for newline
                return ""
            # Safe to stream everything
            return self.buffer

        # We have newlines - check the last line
        last_line = self.buffer[last_newline + 1:]

        # If last line starts with or is backticks, hold it back
        if last_line in ('`', '``', '```') or last_line.startswith('```'):
            # Stream everything up to and including the last newline
            return self.buffer[:last_newline + 1]

        # Everything is safe to stream
        return self.buffer

    def _process_code_block_mode(self) -> Optional[StreamChunk]:
        """
        Process buffer in code block mode.

        Buffers everything until we find the closing ```.

        Returns:
            StreamChunk with complete code block, or None if still buffering
        """
        # Look for closing ```
        closing_idx = self._find_code_block_end()

        if closing_idx is None:
            # Still buffering code block
            return None

        # Found closing ``` - extract complete code block
        # Include the closing ``` and any trailing newline
        end_idx = closing_idx + 3

        # Check if there's a newline after closing ```
        if end_idx < len(self.buffer) and self.buffer[end_idx] == '\n':
            end_idx += 1

        code_block = self.buffer[:end_idx]
        self.buffer = self.buffer[end_idx:]

        # Reset to normal mode
        self.mode = StreamerMode.NORMAL
        language = self.code_block_language
        self.code_block_language = None

        return StreamChunk(
            content=code_block,
            is_code_block=True,
            language=language
        )

    def _find_code_block_start(self) -> Optional[int]:
        """
        Find the start of a code block in the buffer.

        Only detects ``` at the start of a line (not inline backticks).

        Returns:
            Index of ``` start, or None if not found
        """
        search_start = 0

        while True:
            idx = self.buffer.find('```', search_start)

            if idx == -1:
                return None

            # Check if it's at line start (or start of text)
            if idx == 0 or self.buffer[idx - 1] == '\n':
                return idx

            # Not at line start - keep searching
            search_start = idx + 1

    def _find_code_block_end(self) -> Optional[int]:
        """
        Find the closing ``` for the current code block.

        Returns:
            Index of closing ```, or None if not found
        """
        # Start searching after the opening ``` line
        first_newline = self.buffer.find('\n')
        if first_newline == -1:
            return None

        search_start = first_newline + 1

        while True:
            idx = self.buffer.find('```', search_start)

            if idx == -1:
                return None

            # Verify closing ``` is at line start
            if idx == 0 or self.buffer[idx - 1] == '\n':
                return idx

            search_start = idx + 1

    def flush(self) -> Optional[StreamChunk]:
        """
        Flush any remaining buffered content.

        Call this when the stream ends to get any remaining content.

        Returns:
            StreamChunk with remaining content, or None if buffer empty
        """
        if not self.buffer:
            return None

        chunk = StreamChunk(
            content=self.buffer,
            is_code_block=(self.mode == StreamerMode.CODE_BLOCK),
            language=self.code_block_language if self.mode == StreamerMode.CODE_BLOCK else None
        )

        # Reset state
        self.buffer = ""
        self.mode = StreamerMode.NORMAL
        self.code_block_language = None

        return chunk

    def get_buffered_content(self) -> str:
        """Get current buffered content (for debugging/testing)."""
        return self.buffer

    def is_in_code_block(self) -> bool:
        """Check if currently buffering a code block."""
        return self.mode == StreamerMode.CODE_BLOCK

    def reset(self):
        """Reset the streamer state."""
        self.buffer = ""
        self.mode = StreamerMode.NORMAL
        self.code_block_language = None
