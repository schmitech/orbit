"""
Vector utilities and shared constants.
"""

import re

# Pre-compiled regex for efficient dimension mismatch detection
# Matches "dimension" followed by "match" or "expect" (case-insensitive)
DIMENSION_MISMATCH_PATTERN = re.compile(r"dimension.*(?:match|expect)", re.IGNORECASE)
