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
from utils.language_detector import LanguageDetector
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
        self.safety_prompt = self._load_safety_prompt()
        
        # Get safety configuration
        safety_config = config.get('safety', {})
        
        # Initialize safety check configuration
        self.enabled = _is_true_value(safety_config.get('enabled', True))
        self.safety_mode = safety_config.get('mode', 'strict')
        if self.safety_mode not in ['strict', 'fuzzy', 'disabled']:
            logger.warning(f"Unknown safety mode '{self.safety_mode}', defaulting to 'strict'")
            self.safety_mode = 'strict'
            
        # Get provider information - use resolved_provider and resolved_model 
        # that were set by _resolve_provider_configs
        self.provider = safety_config.get('resolved_provider', 'ollama')
        self.model = safety_config.get('resolved_model', 'gemma3:12b')
        
        # Get provider-specific configuration
        provider_config = config.get('inference', {}).get(self.provider, {})
        self.base_url = provider_config.get('base_url', 'http://localhost:11434')
        
        if provider_config:
            logger.info(f"Safety service using provider: {self.provider}")
            logger.info(f"Safety service using base URL: {self.base_url}")
        else:
            # Fallback to legacy config for backward compatibility
            self.base_url = config.get('ollama', {}).get('base_url', 'http://localhost:11434')
            logger.warning(f"Using legacy config for safety service: {self.base_url}")
            
        # Get retry configuration
        self.max_retries = safety_config.get('max_retries', 3)
        self.retry_delay = safety_config.get('retry_delay', 1.0)
        self.request_timeout = safety_config.get('request_timeout', 15)
        self.allow_on_timeout = safety_config.get('allow_on_timeout', False)
        
        # Model parameters
        self.temperature = safety_config.get('temperature', 0.0)
        self.top_p = safety_config.get('top_p', 1.0)
        self.top_k = safety_config.get('top_k', 1)
        self.num_predict = safety_config.get('num_predict', 20)
        self.stream = _is_true_value(safety_config.get('stream', False))
        self.repeat_penalty = safety_config.get('repeat_penalty', 1.1)
        
        # Initialize session as None (lazy initialization)
        self.session = None
        # Handle both string and boolean values for verbose setting
        verbose_value = config.get('general', {}).get('verbose', False)
        self.verbose = _is_true_value(verbose_value)

        self.detector = LanguageDetector(self.verbose)
        
        if self.verbose:
            logger.info(f"GuardrailService initialized with provider {self.provider}, model {self.model}")

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
            connector = aiohttp.TCPConnector(limit=20)  # Use reasonable default limit
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def is_safe(self, query: str) -> bool:
        """
        Check if a query is safe to process.
        Simple wrapper around check_safety that just returns the boolean result.
        
        Args:
            query: The user message to check
            
        Returns:
            bool: True if the query is safe, False otherwise
        """
        is_safe, _ = await self.check_safety(query)
        return is_safe

    async def check_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform a safety verification check on the user query.
        Supports multilingual queries.
        
        Args:
            query: The user message to check for safety
            
        Returns:
            Tuple[bool, Optional[str]]: (is_safe, refusal_message)
                - is_safe: True if query is safe, False otherwise
                - refusal_message: None if safe, otherwise a refusal message to return
        """
        # If safety service is disabled, always return safe
        if not self.enabled:
            if self.verbose:
                logger.info(f"Skipping guardrail check - safety service is disabled for query: '{query}'")
            return True, None
            
        # If safety checks are disabled, always return safe
        if self.safety_mode == 'disabled':
            if self.verbose:
                logger.info("Safety checks disabled by configuration, skipping check")
            return True, None
            
        # Check if the query is in a non-English language
        query_language = self.detector.detect(query)
        is_non_english = query_language != "en"

        if self.verbose:
            logger.info(f"GuardrailService - Language detection result: '{query}' detected as '{query_language}'")

        for attempt in range(self.max_retries):
            try:
                await self.initialize()  # Ensure session is initialized

                # Combine the loaded safety prompt with the query
                prompt = self.safety_prompt + " Query: " + query
                
                # For non-English queries, add a specific instruction
                if is_non_english:
                    prompt = (
                        "You are evaluating whether a query is safe to respond to. "
                        "This query is in a non-English language. "
                        "Evaluate the meaning and intent of the query regardless of language. "
                        "If it is a safe, appropriate query about general information, knowledge, or assistance, respond with EXACTLY 'SAFE: true'. "
                        "If it is NOT safe or appropriate, respond with EXACTLY 'SAFE: false'. "
                        "Query: " + query
                    )
                
                # Log the query being checked
                if self.verbose:
                    logger.info(f"Performing safety check for query: '{query}' (attempt {attempt+1}/{self.max_retries})")
                    if is_non_english:
                        logger.info(f"Query detected as non-English, using specialized prompt")
                    logger.debug(f"Using full safety prompt: '{prompt}'")
                    logger.info(f"Sending safety check request to {self.provider} model: {self.model}")

                # Create payload for the API
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "repeat_penalty": self.repeat_penalty,
                    "num_predict": self.num_predict,
                    "stream": self.stream
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
                        if is_non_english:
                            logger.info(f"Processing non-English safety response")
                    
                    # Process the response to determine safety
                    is_safe, refusal_message = await self._process_safety_response(model_response, is_non_english)
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
    
    async def _process_safety_response(self, model_response: str, is_non_english: bool = False) -> Tuple[bool, Optional[str]]:
            """
            Process the LLM response to determine if the query is safe.
            Enhanced to handle non-English responses.
            
            Args:
                model_response: The raw response from the LLM
                is_non_english: Whether the original query was in a non-English language
                
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
            
            # If we detect refusal phrases in the response, consider it unsafe
            if any(phrase in model_response.lower() for phrase in direct_refusal_phrases):
                if self.verbose:
                    logger.warning(f"Model directly responded with refusal message: '{model_response}'")
                # Since the model directly refused, treat this as unsafe
                return False, model_response
            
            # Enhanced pattern matching for multilingual support
            expected_exact = "SAFE: true"
            alt_expected = '"SAFE: true"'  # With double quotes
            
            # For non-English queries, be more flexible with the response format
            if is_non_english:
                # For non-English, focus on detecting if "true" appears in the response with "safe"
                response_lower = model_response.lower()
                # More permissive check for non-English - look for both "safe" and "true" anywhere
                has_safe = "safe" in response_lower 
                has_true = "true" in response_lower
                has_false = "false" in response_lower
                
                if self.verbose:
                    logger.info(f"Non-English safety check components - has_safe: {has_safe}, has_true: {has_true}, has_false: {has_false}")
                    
                # If response contains both "safe" and "true" but not "false", consider it safe
                if has_safe and has_true and not has_false:
                    if self.verbose:
                        logger.info(f"Non-English query determined to be SAFE based on response: '{model_response}'")
                    return True, None
                    
                # If contains "safe: false" explicitly, mark as unsafe
                if "safe: false" in response_lower or "safe:false" in response_lower:
                    if self.verbose:
                        logger.info(f"Non-English query determined to be UNSAFE based on explicit 'safe: false' in response")
                    return False, "I cannot assist with that type of request."
                    
                # More generic approach - if we see the word "safe" with "true" near it
                safe_index = response_lower.find("safe")
                true_index = response_lower.find("true")
                false_index = response_lower.find("false")
                
                if safe_index != -1 and true_index != -1 and abs(safe_index - true_index) < 20:
                    # If "true" is closer to "safe" than "false" is
                    if false_index == -1 or abs(safe_index - true_index) < abs(safe_index - false_index):
                        if self.verbose:
                            logger.info(f"Non-English query determined to be SAFE based on proximity of 'safe' and 'true'")
                        return True, None
                
                # If we got here and are in fuzzy mode, try the fuzzy check as a fallback
                if self.safety_mode == "fuzzy":
                    is_fuzzy_safe = self._is_likely_safe_response(model_response)
                    if is_fuzzy_safe:
                        if self.verbose:
                            logger.info(f"Non-English query determined to be SAFE via fuzzy matching fallback")
                        return True, None
                        
                # If we can't determine safety, default to considering it unsafe
                if self.verbose:
                    logger.warning(f"Could not determine safety for non-English query with response: '{model_response}', defaulting to UNSAFE")
                return False, "I cannot assist with that type of request."
            
            # Standard processing for English queries
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
        Helper function to check if a response likely indicates safety when in fuzzy mode.
        Enhanced with more patterns for better matching.
        
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
            "safe true",  # More lenient pattern
            "query is safe",  # Natural language response
            "the query is safe",
            "this query is safe",
            "i believe this query is safe",
            "safe to respond",
            "safe for response",
            "determined to be safe",
            "seems safe",
            "appears safe"
        ]
        return any(pattern in resp for pattern in likely_safe_patterns)