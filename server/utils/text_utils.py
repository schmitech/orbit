"""
Utility functions for text processing
"""

import re
import warnings

# Suppress ftfy deprecation warnings before importing ftfy
warnings.filterwarnings("ignore", message=".*fix_entities.*", category=DeprecationWarning)

try:
    import markdown
    import nh3
    import ftfy
    from unidecode import unidecode
    TEXT_LIBS_AVAILABLE = True
except ImportError:
    TEXT_LIBS_AVAILABLE = False

# Minimal regex patterns for basic cleanup (fallback only)
RE_BASIC_SPACE = re.compile(r'([.,!?:;])([A-Za-z0-9])')
RE_SENTENCE_SPACE = re.compile(r'([.!?])([A-Z])')


def fix_text_formatting(text: str) -> str:
    """Fix common text formatting issues from LLM responses using proper text processing libraries"""
    if not text:
        return text
    
    if TEXT_LIBS_AVAILABLE:
        # Use professional text processing libraries
        text = normalize_text_with_libraries(text)
    else:
        # Fallback to basic regex fixes
        text = normalize_text_basic(text)
    
    return text

def normalize_text_with_libraries(text: str) -> str:
    """
    Normalize text using professional libraries for robust text processing.
    
    Uses:
    - ftfy: Fixes text encoding issues, mojibake, and common text corruption
    - unidecode: Handles unicode normalization
    - markdown + nh3: Handles markdown formatting and sanitization
    """
    try:
        # Step 1: Fix text encoding issues, mojibake, and spacing problems
        # ftfy is excellent at fixing common text formatting issues including:
        # - Spacing around punctuation
        # - Currency symbol formatting
        # - Number-word boundaries
        # - Unicode normalization
        # - Text corruption from encoding issues
        text = ftfy.fix_text(text)
        
        # Step 2: Normalize whitespace and clean up
        text = ftfy.fix_text_segment(
            text,
            # Fix spacing issues (using new parameter name)
            unescape_html=True,  # Changed from fix_entities=True
            # Remove control characters
            remove_terminal_escapes=True,
            # Normalize line breaks
            fix_line_breaks=True,
            # Fix character encoding
            fix_character_width=True,
            # Normalize quotes and dashes
            fix_surrogates=True
        )
        
        # Step 3: Handle any remaining unicode issues with unidecode if needed
        # (Only for extreme cases - ftfy usually handles this)
        # Uncomment if you need ASCII-only output:
        # text = unidecode(text)
        
        # Step 4: Apply markdown cleaning
        text = clean_markdown_response(text)
        
        return text
        
    except Exception as e:
        # If library processing fails, fall back to basic processing
        import logging
        logging.getLogger(__name__).warning(f"Text normalization failed, using fallback: {e}")
        return normalize_text_basic(text)

def normalize_text_basic(text: str) -> str:
    """Basic text normalization using regex (fallback when libraries unavailable)"""
    # Apply only essential regex fixes
    text = RE_BASIC_SPACE.sub(r'\1 \2', text)
    text = RE_SENTENCE_SPACE.sub(r'\1 \2', text)
    
    # Basic whitespace cleanup
    text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single space
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines to double newline
    text = text.strip()
    
    return text

def clean_markdown_response(text: str) -> str:
    """Clean and standardize markdown formatting using proper libraries"""
    if not TEXT_LIBS_AVAILABLE or not text:
        return text
    
    # Clean up common markdown formatting issues
    text = _fix_markdown_syntax(text)
    
    # Validate that the markdown is well-formed by parsing and reconstructing
    try:
        # Parse markdown to HTML and back to ensure proper structure
        md = markdown.Markdown()
        html = md.convert(text)
        
        # Clean HTML with nh3 to ensure safety
        allowed_tags = {
            'p', 'br', 'strong', 'em', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
        }
        allowed_attributes = {
            'a': {'href', 'title'},
            'img': {'src', 'alt', 'title'},
        }
        clean_html = nh3.clean(html, tags=allowed_tags, attributes=allowed_attributes)
        
        # If HTML was cleaned significantly, return the original text
        if len(clean_html) < len(html) * 0.8:
            return text
            
    except Exception:
        # If markdown processing fails, return the text with basic cleanup
        pass
    
    return text

def _fix_markdown_syntax(text: str) -> str:
    """Fix common markdown syntax issues"""
    # Fix code block formatting - ensure proper newlines around triple backticks
    text = re.sub(r'```(\w*)\s*\n?([^`]*?)```', r'```\1\n\2\n```', text, flags=re.DOTALL)
    
    # Fix inline code formatting - remove extra spaces inside backticks
    text = re.sub(r'`\s+([^`]+?)\s+`', r'`\1`', text)
    
    # Fix list formatting - ensure proper spacing after list markers
    text = re.sub(r'^(\s*[-*+])\s*([^\s])', r'\1 \2', text, flags=re.MULTILINE)
    text = re.sub(r'^(\s*\d+\.)\s*([^\s])', r'\1 \2', text, flags=re.MULTILINE)
    
    # Fix heading formatting - ensure space after hash symbols
    text = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
    
    # Fix bold/italic formatting - remove extra spaces inside markers
    text = re.sub(r'\*\*\s+([^*]+?)\s+\*\*', r'**\1**', text)
    text = re.sub(r'(?<!\*)\*\s+([^*]+?)\s+\*(?!\*)', r'*\1*', text)
    text = re.sub(r'__\s+([^_]+?)\s+__', r'__\1__', text)
    text = re.sub(r'(?<!_)_\s+([^_]+?)\s+_(?!_)', r'_\1_', text)
    
    # Fix link formatting - ensure proper spacing around links
    text = re.sub(r'\[\s+([^\]]+?)\s+\]', r'[\1]', text)
    
    # Clean up excessive whitespace while preserving intentional formatting
    # Remove trailing spaces at end of lines
    text = re.sub(r' +$', '', text, flags=re.MULTILINE)
    
    # Normalize multiple blank lines to maximum of 2
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # Remove leading/trailing whitespace from the entire text
    text = text.strip()
    
    return text

def sanitize_error_message(message: str) -> str:
    """Sanitize error messages to remove sensitive information"""
    # List of patterns to look for
    sensitive_patterns = [
        (r'password=([^&\s]+)', 'password=[REDACTED]'),
        (r'apiKey=([^&\s]+)', 'apiKey=[REDACTED]'),
        (r'api_key=([^&\s]+)', 'api_key=[REDACTED]'),
        (r'accessToken=([^&\s]+)', 'accessToken=[REDACTED]'),
        (r'access_token=([^&\s]+)', 'access_token=[REDACTED]'),
        (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer [REDACTED]'),
        (r'Basic\s+[A-Za-z0-9\-._~+/]+=*', 'Basic [REDACTED]'),
        # Auth patterns for URLs
        (r'https?://[^:]+:[^@]+@', 'https://[USER]:[REDACTED]@'),
        # Connection strings
        (r'mongodb(\+srv)?://[^:]+:[^@]+@', 'mongodb$1://[USER]:[REDACTED]@'),
        (r'postgres://[^:]+:[^@]+@', 'postgres://[USER]:[REDACTED]@'),
        # IP addresses - don't redact these as they're needed for debugging
        # but redact any sensitive path info
        (r'/home/[^/]+', '/home/[USER]'),
        # AWS keys pattern
        (r'AKIA[0-9A-Z]{16}', '[AWS_KEY_ID]'),
        (r'AWS_SECRET_ACCESS_KEY[=:]\s*[A-Za-z0-9/+]{40}', 'AWS_SECRET_ACCESS_KEY=[REDACTED]'),
    ]
    
    sanitized = message
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    
    return sanitized


def mask_api_key(api_key: str, show_last: bool = False, num_chars: int = 4) -> str:
    """
    Mask an API key for secure logging.
    
    Args:
        api_key: The API key to mask
        show_last: If True, show the last num_chars of the key, otherwise show the first num_chars
        num_chars: Number of characters to show
        
    Returns:
        A masked version of the API key
    """
    if not api_key:
        return "None"
        
    if len(api_key) <= num_chars:
        return "****"
        
    if show_last:
        return f"...{api_key[-num_chars:]}"
    else:
        return f"{api_key[:num_chars]}..."


def simple_fix_text(text: str) -> str:
    """Apply minimal text fixes to a chunk (focused on beginning of chunk only)"""
    # Only fix beginning of chunk if needed - for connecting to previous chunk
    if text and text[0].isalnum() and not text[0].isupper():
        # This might be continuing a sentence, so no changes needed
        return text
    elif text and text[0].isupper() and len(text) > 1:
        # This could be a new sentence, might need a space
        return " " + text if text[0].isupper() else text
    return text