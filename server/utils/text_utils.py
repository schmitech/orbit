"""
Utility functions for text processing
"""

import re
# Precompile regex patterns for text formatting
RE_PUNCTUATION_SPACE = re.compile(r'([.,!?:;])([A-Za-z0-9])')
RE_SENTENCE_SPACE = re.compile(r'([.!?])([A-Z])')
RE_WORD_SPACE = re.compile(r'([a-z])([A-Z])')


def fix_text_formatting(text: str) -> str:
    """Fix common text formatting issues from LLM responses using precompiled regex"""
    # Fix missing spaces after punctuation
    text = RE_PUNCTUATION_SPACE.sub(r'\1 \2', text)
    
    # Fix missing spaces between sentences
    text = RE_SENTENCE_SPACE.sub(r'\1 \2', text)
    
    # Fix missing spaces between words (lowercase followed by uppercase)
    text = RE_WORD_SPACE.sub(r'\1 \2', text)
    
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