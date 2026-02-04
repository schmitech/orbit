"""
PersonaPlex Knowledge Service

Service for injecting grounded knowledge into PersonaPlex voice conversation prompts
using static facts files.

Static files are the recommended approach because:
- No vector DB dependency - Simpler deployment
- Faster startup - No embedding generation needed
- Full control - You curate exactly which facts are included
- Easier testing - Plain text files are easy to review and update

Facts files are simple text files with one fact per line.
Lines starting with # are treated as comments and ignored.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PersonaPlexKnowledgeService:
    """
    Service for loading static knowledge facts for PersonaPlex prompts.

    Loads facts from plain text files (one fact per line) and formats
    them for injection into PersonaPlex system prompts.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the knowledge service.

        Args:
            config: Global application configuration
        """
        self.config = config
        # Cache for loaded facts (keyed by file path)
        self._facts_cache: Dict[str, List[str]] = {}

    async def build_knowledge_context(
        self,
        facts_file: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> Optional[str]:
        """
        Load facts from a static text file.

        Args:
            facts_file: Path to text file (relative to project root or absolute)
            max_items: Maximum facts to include (None = all)

        Returns:
            Formatted facts string with bullet points, or None if no facts found
        """
        if not facts_file:
            logger.warning("No facts_file specified for knowledge injection")
            return None

        # Resolve path - support relative paths from project root
        if not os.path.isabs(facts_file):
            resolved_path = Path(facts_file)
            if not resolved_path.exists():
                # Try relative to server directory
                server_dir = Path(__file__).parent.parent.parent
                resolved_path = server_dir / facts_file
        else:
            resolved_path = Path(facts_file)

        # Check cache first
        cache_key = str(resolved_path)
        if cache_key in self._facts_cache:
            facts = self._facts_cache[cache_key]
            logger.debug(f"Using cached facts from '{facts_file}' ({len(facts)} items)")
        else:
            # Load from file
            if not resolved_path.exists():
                logger.error(f"Facts file not found: {resolved_path}")
                return None

            try:
                with open(resolved_path, 'r', encoding='utf-8') as f:
                    # Read lines, strip whitespace, filter empty lines and comments
                    facts = [
                        line.strip()
                        for line in f.readlines()
                        if line.strip() and not line.strip().startswith('#')
                    ]

                # Cache the loaded facts
                self._facts_cache[cache_key] = facts
                logger.info(f"Loaded {len(facts)} facts from '{facts_file}'")

            except Exception as e:
                logger.error(f"Error reading facts file '{facts_file}': {e}")
                return None

        if not facts:
            logger.warning(f"No facts found in '{facts_file}'")
            return None

        # Apply max_items limit if specified
        if max_items and len(facts) > max_items:
            facts = facts[:max_items]
            logger.debug(f"Limited to {max_items} facts")

        # Format as bullet points
        formatted = "\n".join(f"• {fact}" for fact in facts)
        return formatted

    def format_augmented_prompt(
        self,
        base_prompt: Optional[str],
        knowledge_context: Optional[str],
        header: str = "VERIFIED FACTS (you MUST use these exact values when answering):",
        footer: str = "When asked about any topic above, use the EXACT information provided. Do not estimate or guess different values."
    ) -> Optional[str]:
        """
        Combine base prompt with knowledge context.

        Args:
            base_prompt: The original system prompt
            knowledge_context: Formatted knowledge string from build_knowledge_context()
            header: Header text to introduce the knowledge section
            footer: Footer text to reinforce knowledge usage

        Returns:
            Augmented prompt string, or base_prompt if no knowledge
        """
        if not knowledge_context:
            return base_prompt

        if not base_prompt:
            return f"{header}\n{knowledge_context}\n\n{footer}"

        return f"{base_prompt}\n\n{header}\n{knowledge_context}\n\n{footer}"

    def clear_cache(self):
        """Clear the facts cache (useful for reloading after file changes)."""
        self._facts_cache.clear()
        logger.info("Facts cache cleared")
