"""
Guardrail Service
================

A service that provides safety verification for user queries using configurable
guardrails through LLM-based verification.

This service isolates the safety check logic for easier testing and reuse
across different client components.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Tuple, Optional

from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)


class GuardrailService:
    """Handles safety verification of user queries using LLM-based guardrails"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the GuardrailService
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.safety_prompt = self._load_safety_prompt()
        
        # Initialize safety check configuration
        self.safety_mode = config.get('safety', {}).get('mode', 'strict')
        if self.safety_mode not in ['strict', 'fuzzy', 'disabled']:
            logger.warning(f"Unknown safety mode '{self.safety_mode}', defaulting to 'strict'")
            self.safety_mode = 'strict'
            
        # Get retry configuration
        self.max_retries = self.config.get('safety', {}).get('max_retries', 3)
        self.retry_delay = self.config.get('safety', {}).get('retry_delay', 1.0)
        self.request_timeout = self.config.get('safety', {}).get('request_timeout', 15)
        self.allow_on_timeout = self.config.get('safety', {}).get('allow_on_timeout', False)
        
        # Use a dedicated safety model if specified, otherwise use the main model
        self.safety_model = (
            self.config.get('safety', {}).get('model') or 
            self.config.get('ollama', {}).get('safety_model') or 
            self.config['ollama']['model']
        )
        
        # Initialize session as None (lazy initialization)
        self.session = None
        # Handle both string and boolean values for verbose setting
        verbose_value = config.get('general', {}).get('verbose', False)
        self.verbose = _is_true_value(verbose_value)

    def _load_safety_prompt(self) -> str:
        """
        Load safety prompt from file if available
        
        Returns:
            str: The safety prompt content
            
        Raises:
            RuntimeError: If safety prompt cannot be loaded
        """
        try:
            prompt_file = self.config.get('general', {}).get('safety_prompt_file', '../prompts/safety_prompt.txt')
            with open(prompt_file, 'r') as file:
                # Clean up the prompt by stripping whitespace and normalizing linebreaks
                content = file.read()
                # Replace any unusual line endings and remove special characters
                content = content.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
                # Normalize whitespace (multiple spaces to single space)
                content = ' '.join(content.split())
                return content.strip()
        except Exception as e:
            logger.error(f"Could not load safety prompt from file {prompt_file}: {str(e)}")
            raise RuntimeError(f"Safety prompt file '{prompt_file}' is required but could not be loaded: {str(e)}")

    async def initialize(self):
        """Initialize the aiohttp session with appropriate timeouts"""
        if self.session is None:
            # Use the safety request timeout for the session
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            connector = aiohttp.TCPConnector(limit=self.config['ollama'].get('connector_limit', 20))
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def check_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform a safety verification check on the user query.
        
        Args:
            query: The user message to check for safety
            
        Returns:
            Tuple[bool, Optional[str]]: (is_safe, refusal_message)
                - is_safe: True if query is safe, False otherwise
                - refusal_message: None if safe, otherwise a refusal message to return
        """
        # If safety service is disabled, always return safe
        if not self.config.get('safety', {}).get('enabled', True):
            if self.verbose:
                logger.info(f"Skipping guardrail check - safety service is disabled for query: '{query}'")
            return True, None
            
        # If safety checks are disabled, always return safe
        if self.safety_mode == 'disabled':
            if self.verbose:
                logger.info("Safety checks disabled by configuration, skipping check")
            return True, None
            
        for attempt in range(self.max_retries):
            try:
                await self.initialize()  # Ensure session is initialized

                # Combine the loaded safety prompt with the query
                prompt = self.safety_prompt + " Query: " + query
                
                # Log the query being checked
                if self.verbose:
                    logger.info(f"Performing safety check for query: '{query}' (attempt {attempt+1}/{self.max_retries})")
                    logger.debug(f"Using full safety prompt: '{prompt}'")
                    logger.info(f"Sending safety check request to Ollama model: {self.safety_model}")

                # Create payload for Ollama API
                payload = {
                    "model": self.safety_model,
                    "prompt": prompt,
                    "temperature": self.config['safety'].get('temperature', 0.0),
                    "top_p": self.config['safety'].get('top_p', 1.0),
                    "top_k": self.config['safety'].get('top_k', 1),
                    "repeat_penalty": self.config['safety'].get('repeat_penalty', 1.1),
                    "num_predict": self.config['safety'].get('num_predict', 20),
                    "stream": self.config['safety'].get('stream', False)
                }

                start_time = asyncio.get_event_loop().time()
                
                async with self.session.post(
                    f"{self.base_url}/api/generate", 
                    json=payload
                ) as response:
                    if response.status != 200:
                        logger.error(f"Safety check failed with status {response.status}")
                        return False, "I cannot assist with that type of request."

                    data = await response.json()
                    model_response = data.get("response", "").strip()
                    
                    # Clean up the model response to handle potential whitespace and line break issues
                    model_response = ' '.join(model_response.split())
                    
                    end_time = asyncio.get_event_loop().time()
                    
                    # Log timing and response only in verbose mode
                    if self.verbose:
                        logger.info(f"Safety check completed in {end_time - start_time:.3f}s")
                        logger.info(f"Safety check raw response: '{model_response}'")
                    
                    # Process the response to determine safety
                    is_safe, refusal_message = self._process_safety_response(model_response)
                    return is_safe, refusal_message

            except asyncio.TimeoutError:
                logger.warning(f"Safety check timed out (attempt {attempt+1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    if self.verbose:
                        logger.info(f"Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error("Safety check failed after all retry attempts")
                    # After all retries fail, default to allowing the query through if configured
                    if self.allow_on_timeout:
                        logger.warning("Allowing query through due to allow_on_timeout setting")
                        return True, None
                    return False, "I cannot assist with that request due to a service issue. Please try again later."
            except Exception as e:
                logger.error(f"Error in safety check: {str(e)}", exc_info=True)
                if attempt < self.max_retries - 1:
                    if self.verbose:
                        logger.info(f"Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    # If all retries fail, fallback to default response
                    return False, "I cannot assist with that type of request."
    
    def _process_safety_response(self, model_response: str) -> Tuple[bool, Optional[str]]:
        """
        Process the LLM response to determine if the query is safe
        
        Args:
            model_response: The raw response from the LLM
            
        Returns:
            Tuple[bool, Optional[str]]: (is_safe, refusal_message)
                - is_safe: True if response indicates safety, False otherwise
                - refusal_message: None if safe, otherwise a refusal message
        """
        # Special case: if the model directly responds with a refusal message
        direct_refusal_phrases = [
            "i cannot assist with that",
            "i'm unable to",
            "i am unable to",
            "i can't respond to",
            "i cannot respond to",
            "i'm not able to",
            "sorry, i cannot"
        ]
        
        if any(phrase in model_response.lower() for phrase in direct_refusal_phrases):
            if self.verbose:
                logger.warning(f"Model directly responded with refusal message: '{model_response}'")
            # Since the model directly refused, treat this as unsafe
            return False, model_response
        
        # Check for variations of "SAFE: true" that might occur
        expected_exact = "SAFE: true"
        alt_expected = '"SAFE: true"'  # With double quotes
        
        # Check exact match first - allow for both quoted and unquoted versions
        is_safe_exact = model_response == expected_exact or model_response == alt_expected
        is_safe_fuzzy = False
        
        # If no exact match and fuzzy mode is enabled, check for fuzzy matches
        if not is_safe_exact and self.safety_mode == 'fuzzy':
            is_safe_fuzzy = self._is_likely_safe_response(model_response)
            if is_safe_fuzzy and self.verbose:
                logger.warning(f"Safety check used fuzzy matching. Expected '{expected_exact}' but got '{model_response}'")
        
        # Use either exact or fuzzy match result based on safety mode
        is_safe = is_safe_exact or (self.safety_mode == 'fuzzy' and is_safe_fuzzy)
        
        if self.verbose:
            logger.info(f"Safety check result: mode={self.safety_mode}, exact={is_safe_exact}, fuzzy={is_safe_fuzzy}, final={is_safe}")
        
        # Log any variations that might be causing issues
        if not is_safe and "safe" in model_response.lower():
            # Check for common "unsafe" response formats
            unsafe_patterns = [
                "safe: false",
                "\"safe: false\"",
                '"safe: false"',
                "safe:false"
            ]
            
            if any(pattern in model_response.lower() for pattern in unsafe_patterns):
                # This is a proper unsafe response, no warning needed
                if self.verbose:
                    logger.info("Query correctly identified as unsafe")
            else:
                # This is an unrecognized format
                if self.verbose:
                    logger.warning(f"Safety format mismatch. Response contains 'safe' but not recognized: '{model_response}'")
        
        refusal_message = None if is_safe else "I cannot assist with that type of request."
        return is_safe, refusal_message
    
    def _is_likely_safe_response(self, resp: str) -> bool:
        """
        Helper function to check if a response likely indicates safety when in fuzzy mode
        
        Args:
            resp: The model response to check
            
        Returns:
            bool: True if the response likely indicates safety, False otherwise
        """
        resp = resp.lower().strip()
        # Check for common patterns indicating safety
        likely_safe_patterns = [
            "safe: true", 
            "safe:true",
            "safe - true", 
            "safe = true",
            "\"safe\": true",
            "safe\"=true",
            "\"safe: true\"",
            # Add more patterns if needed
        ]
        return any(pattern in resp for pattern in likely_safe_patterns)