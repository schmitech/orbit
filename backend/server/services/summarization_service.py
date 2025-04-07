"""
Summarization Service
====================

A service that provides text summarization functionality using Ollama.
"""

import logging
import aiohttp
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)


class SummarizationService:
    """Handles text summarization using Ollama"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the SummarizationService
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama'].get('summarization_model', config['ollama']['model'])
        self.max_length = config['ollama'].get('max_summary_length', 100)  # Default to 100 tokens
        self.verbose = config.get('general', {}).get('verbose', False)
        self.session = None

    async def initialize(self):
        """Initialize the aiohttp session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout for summarization
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def summarize(self, text: str) -> str:
        """
        Summarize the given text
        
        Args:
            text: The text to summarize
            
        Returns:
            str: The summarized text
        """
        try:
            await self.initialize()
            
            # Create a prompt that focuses on the content without boilerplate
            prompt = f"""Please summarize the following text in {self.max_length} tokens or less. 
Focus on the key points and main ideas. Do not include any introductory phrases or explanations.
Just provide the summary directly:

{text}"""

            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": 0.1,  # Lower temperature for more focused summaries
                "top_p": 0.9,
                "num_predict": self.max_length,
                "stream": False
            }

            if self.verbose:
                logger.info(f"Summarizing text (length: {len(text)})")
                logger.info(f"Using model: {self.model}")
                logger.info(f"Max summary length: {self.max_length} tokens")

            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Summarization failed with status {response.status}")
                    return text  # Return original text if summarization fails
                
                data = await response.json()
                summary = data.get("response", "").strip()
                
                if self.verbose:
                    logger.info(f"Summary generated (length: {len(summary)})")
                
                return summary

        except Exception as e:
            logger.error(f"Error in summarization: {str(e)}")
            return text  # Return original text if summarization fails 