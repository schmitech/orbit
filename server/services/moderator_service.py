"""
Moderator Service
================

A service that provides safety verification for user queries using configurable
moderators through LLM-based verification or content moderation API.

This service isolates the safety check logic for easier testing and reuse
across different client components.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Tuple, Optional

# Import from new AI services architecture
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType
from ai_services.registry import register_all_services

from utils import is_true_value

# Configure logging
logger = logging.getLogger(__name__)


class ModeratorService:
    """Handles safety verification of user queries using LLM-based guardrails or content moderation API"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the ModeratorService
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get safety configuration
        safety_config = config.get('safety', {})
        
        # Initialize safety check configuration
        self.enabled = is_true_value(safety_config.get('enabled', True))
        self.safety_mode = safety_config.get('mode', 'strict')
        if self.safety_mode not in ['strict', 'fuzzy', 'disabled']:
            logger.warning(f"Unknown safety mode '{self.safety_mode}', defaulting to 'strict'")
            self.safety_mode = 'strict'
            
        # Get moderator information
        # First check for moderator, otherwise use the general inference provider
        self.moderator_name = safety_config.get('moderator')

        # Debug output to help identify configuration issues
        if self.moderator_name:
            logger.info(f"Configured moderator from safety config: {self.moderator_name}")
        else:
            logger.info("No moderator specified in safety config, will use inference provider")

        # Ensure all AI services are registered
        # Note: If already registered by ServiceFactory, this will be a no-op
        register_all_services(config)

        # Check available moderation services from new factory
        available_services = AIServiceFactory.list_available_services()
        available_moderators = available_services.get('moderation', [])
        logger.info(f"Available moderators: {available_moderators}")

        # If using a recognized moderator
        if self.moderator_name and self.moderator_name in available_moderators:
            try:
                self.use_moderator = True
                # Use new AI services factory
                self.moderator = AIServiceFactory.create_service(
                    ServiceType.MODERATION,
                    self.moderator_name,
                    config
                )
                logger.info(f"Safety service using moderator: {self.moderator_name}")
            except (ValueError, Exception) as e:
                # If moderator initialization fails (e.g., missing API key), try to fall back
                logger.warning(f"Failed to initialize {self.moderator_name} moderator: {str(e)}")
                self._fallback_to_alternative_moderator(config, safety_config)
        else:
            # If no valid moderator, fall back to using the general inference provider
            self._fallback_to_inference_provider(config, safety_config)
        
        # Get retry configuration
        self.max_retries = safety_config.get('max_retries', 3)
        self.retry_delay = safety_config.get('retry_delay', 1.0)
        self.request_timeout = safety_config.get('request_timeout', 15)
        self.allow_on_timeout = safety_config.get('allow_on_timeout', False)
        
        # Initialize session as None (lazy initialization)
        self.session = None
        # Model parameters (used only when not using a dedicated moderator)
        if not self.use_moderator:
            self.temperature = safety_config.get('temperature', 0.0)
            self.top_p = safety_config.get('top_p', 1.0)
            self.top_k = safety_config.get('top_k', 1)
            self.num_predict = safety_config.get('num_predict', 20)
            self.stream = is_true_value(safety_config.get('stream', False))
            self.repeat_penalty = safety_config.get('repeat_penalty', 1.1)
            
            # Load safety prompt for LLM-based approach
            self.safety_prompt = self._load_safety_prompt(safety_config)
        
        if self.use_moderator:
            logger.debug(f"ModeratorService initialized with moderator {self.moderator_name}, enabled={self.enabled}, mode={self.safety_mode}")
        else:
            provider = getattr(self, 'provider', 'unknown')
            model = getattr(self, 'model', 'unknown')
            logger.debug(f"ModeratorService initialized with provider {provider}, model {model}, enabled={self.enabled}, mode={self.safety_mode}")

    def _fallback_to_alternative_moderator(self, config: Dict[str, Any], safety_config: Dict[str, Any]):
        """
        Try to fall back to an alternative moderator when the primary one fails.

        Args:
            config: Application configuration dictionary
            safety_config: Safety configuration dictionary
        """
        # Try to find an alternative moderator that doesn't require API keys
        alternative_moderators = ['ollama']  # Ollama doesn't require API keys

        # Get available moderators from new factory
        available_services = AIServiceFactory.list_available_services()
        available_moderators = available_services.get('moderation', [])

        for alt_moderator in alternative_moderators:
            if alt_moderator in available_moderators:
                try:
                    self.moderator_name = alt_moderator
                    self.use_moderator = True
                    # Use new AI services factory
                    self.moderator = AIServiceFactory.create_service(
                        ServiceType.MODERATION,
                        alt_moderator,
                        config
                    )
                    logger.info(f"Successfully fell back to {alt_moderator} moderator")
                    return
                except Exception as e:
                    logger.warning(f"Failed to initialize {alt_moderator} moderator: {str(e)}")
                    continue

        # If no alternative moderator works, check if we should disable safety
        if safety_config.get('disable_on_fallback', False):
            logger.warning("No moderators available and disable_on_fallback is enabled, disabling safety checks")
            self.enabled = False
            self.use_moderator = False
            return

        # Otherwise fall back to inference provider
        logger.warning("No alternative moderators available, falling back to inference provider")
        self._fallback_to_inference_provider(config, safety_config)

    def _fallback_to_inference_provider(self, config: Dict[str, Any], safety_config: Dict[str, Any]):
        """
        Fall back to using the general inference provider for safety checks.
        
        Args:
            config: Application configuration dictionary
            safety_config: Safety configuration dictionary
        """
        self.use_moderator = False
        # Get the general inference provider instead of using moderator name as provider
        self.provider = config.get('general', {}).get('inference_provider', 'ollama')
        self.model = safety_config.get('model', config.get('inference', {}).get(self.provider, {}).get('model', 'gemma3:1b'))
        self.base_url = config.get('inference', {}).get(self.provider, {}).get('base_url', 'http://localhost:11434')
        
        # Note: ModeratorFactory is deprecated, but we check available services instead
        available_services = AIServiceFactory.list_available_services()
        available_moderators = available_services.get('moderation', [])
        if self.moderator_name and self.moderator_name not in available_moderators:
            logger.warning(f"Configured moderator '{self.moderator_name}' not found in available services. Falling back to {self.provider}.")
        
        logger.info(f"Safety service using inference provider: {self.provider}")
        logger.info(f"Safety service using model: {self.model}")
        logger.info(f"Safety service using base URL: {self.base_url}")

    def _load_safety_prompt(self, safety_config: Dict[str, Any]) -> str:
        """
        Load the safety prompt from file or use default.
        
        Args:
            safety_config: Safety configuration dictionary
            
        Returns:
            str: The safety prompt text
        """
        import os
        
        # Try to load from configured path
        prompt_path = safety_config.get('safety_prompt_path', 'prompts/safety_prompt.txt')
        
        # If it's a relative path, make it relative to the project root
        if not os.path.isabs(prompt_path):
            # Try to find the project root (where config.yaml is located)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            prompt_path = os.path.join(project_root, prompt_path)
        
        try:
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt = f.read().strip()
                logger.debug(f"Loaded safety prompt from: {prompt_path}")
                return prompt
            else:
                logger.warning(f"Safety prompt file not found at: {prompt_path}")
        except Exception as e:
            logger.warning(f"Failed to load safety prompt from {prompt_path}: {str(e)}")
        
        # Fallback to default safety prompt
        default_prompt = """You are a safety checker. Analyze the following query and determine if it's safe to respond to.

A query is considered SAFE if it:
- Asks for factual information
- Requests help with legitimate tasks
- Seeks educational content
- Asks for creative writing or analysis
- Requests programming help for legitimate purposes

A query is considered UNSAFE if it:
- Requests harmful or illegal activities
- Asks for personal information about others
- Seeks to bypass security measures
- Requests content that could cause harm
- Asks for instructions on dangerous activities

Respond with exactly "SAFE: true" if the query is safe, or "SAFE: false" if it's unsafe.

Query: """

        logger.debug("Using default safety prompt")
        return default_prompt

    async def initialize(self):
        """Initialize the service and required connections"""
        if self.use_moderator and hasattr(self, 'moderator') and self.moderator is not None:
            # Initialize the moderator
            await self.moderator.initialize()
        else:
            # Initialize aiohttp session with appropriate timeouts
            if self.session is None:
                timeout = aiohttp.ClientTimeout(total=self.request_timeout)
                connector = aiohttp.TCPConnector(limit=20)
                self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            
    async def close(self):
        """Close connections and release resources"""
        if self.use_moderator and hasattr(self, 'moderator') and self.moderator is not None:
            await self.moderator.close()
        elif self.session:
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
            logger.debug(f"Skipping guardrail check - safety service is disabled for query: '{query}'")
            return True, None
            
        # If safety checks are disabled, always return safe
        if self.safety_mode == 'disabled':
            logger.debug("Safety checks disabled by configuration, skipping check")
            return True, None
        
        # If using a dedicated moderator, use it for content moderation
        if self.use_moderator:
            return await self._check_safety_with_moderator(query)
        
        # Otherwise use the legacy LLM-based approach
        return await self._check_safety_with_llm(query)
    
    async def _check_safety_with_moderator(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Check query safety using a dedicated content moderator.
        
        Args:
            query: The user message to check
            
        Returns:
            Tuple[bool, Optional[str]]: (is_safe, refusal_message)
        """
        # If moderator doesn't exist, fall back to LLM-based approach
        if not hasattr(self, 'moderator') or self.moderator is None:
            logger.warning("Moderator not available, falling back to LLM-based safety check")
            return await self._check_safety_with_llm(query)
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"🔍 Performing moderator safety check for query: '{query[:50]}...' (attempt {attempt+1}/{self.max_retries})")

                # Use the moderator to check content
                result = await self.moderator.moderate_content(query)
                
                # The content is safe if it's not flagged
                is_safe = not result.is_flagged

                # Add detailed logging with emojis
                if is_safe:
                    logger.debug(f"✅ MODERATION PASSED: Query was deemed SAFE by {self.moderator_name} moderator")
                    # Show all category scores for debugging
                    logger.debug(f"All category scores: {result.categories}")
                else:
                    # Get flagged categories with scores > 0.5
                    try:
                        flagged_categories = {k: v for k, v in result.categories.items() if v > 0.5}
                        logger.info(f"🛑 MODERATION BLOCKED: Query was flagged as UNSAFE by {self.moderator_name} moderator")
                        logger.info(f"⚠️ Flagged categories: {flagged_categories}")
                        logger.debug(f"All category scores: {result.categories}")
                    except Exception as category_error:
                        logger.error(f"Error processing moderation categories: {str(category_error)}")
                        logger.info("🛑 MODERATION BLOCKED: Query was flagged as UNSAFE (categories unavailable)")

                # Return appropriate response with category information for transparency
                if is_safe:
                    return True, None
                else:
                    # Get the primary flagged category to help users understand why
                    try:
                        flagged_categories = {k: v for k, v in result.categories.items() if v > 0.5}
                        if flagged_categories:
                            # Get the highest scoring category
                            primary_category = max(flagged_categories, key=flagged_categories.get)
                            # Map internal category names to user-friendly descriptions
                            # Supports OpenAI, Llama Guard 3, and Anthropic category names
                            category_descriptions = {
                                # OpenAI moderation categories
                                'harassment': 'harassment content',
                                'harassment_threatening': 'threatening content',
                                'hate': 'hateful content',
                                'hate_threatening': 'threatening hateful content',
                                'illicit': 'potentially harmful activities',
                                'illicit_violent': 'violent or harmful activities',
                                'self_harm': 'self-harm content',
                                'self_harm_instructions': 'self-harm instructions',
                                'self_harm_intent': 'self-harm related content',
                                'sexual': 'inappropriate content',
                                'sexual_minors': 'inappropriate content involving minors',
                                'violence': 'violent content',
                                'violence_graphic': 'graphic violence',
                                # Llama Guard 3 / MLCommons taxonomy categories
                                'violent_crimes': 'violent criminal activities',
                                'non_violent_crimes': 'illegal activities',
                                'sex_related_crimes': 'sex-related criminal content',
                                'child_exploitation': 'content involving minors',
                                'defamation': 'defamatory content',
                                'specialized_advice': 'potentially dangerous advice',
                                'privacy': 'privacy violations',
                                'intellectual_property': 'intellectual property concerns',
                                'indiscriminate_weapons': 'weapons of mass destruction',
                                'elections': 'election misinformation',
                                'code_interpreter_abuse': 'system abuse attempts',
                                # Generic/fallback categories
                                'policy_violation': 'content policy violation',
                                'interpreted_unsafe': 'potentially unsafe content',
                            }
                            category_desc = category_descriptions.get(primary_category, 'content policy violation')
                            refusal_message = f"I cannot assist with requests involving {category_desc}."
                        else:
                            refusal_message = "I cannot assist with that type of request."
                    except Exception:
                        refusal_message = "I cannot assist with that type of request."
                    return False, refusal_message
                
            except Exception as e:
                logger.error(f"❌ Error in moderator safety check: {str(e)}", exc_info=True)
                if attempt < self.max_retries - 1:
                    logger.debug(f"🔄 Retrying in {self.retry_delay} seconds... (Attempt {attempt+1} of {self.max_retries})")
                    await asyncio.sleep(self.retry_delay)
                else:
                    # If all retries fail and we're configured to allow on timeout
                    if self.allow_on_timeout:
                        logger.warning("⚠️ MODERATION ERROR: Allowing query through due to allow_on_timeout setting")
                        return True, None
                    logger.warning("🚫 MODERATION FAILED: Blocking query after multiple failed attempts")
                    return False, "I cannot assist with that request due to a service issue. Please try again later."
    
    async def _check_safety_with_llm(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Legacy method to check safety using LLM-based verification.
        
        Args:
            query: The user message to check
            
        Returns:
            Tuple[bool, Optional[str]]: (is_safe, refusal_message)
        """
        for attempt in range(self.max_retries):
            try:
                await self.initialize()  # Ensure session is initialized

                # Combine the loaded safety prompt with the query
                prompt = self.safety_prompt + " Query: " + query

                # Log the query being checked
                logger.debug(f"🔍 Performing LLM safety check for query: '{query[:50]}...' (attempt {attempt+1}/{self.max_retries})")
                logger.debug(f"📝 Using full safety prompt: '{prompt[:100]}...'")
                logger.debug(f"🤖 Sending safety check request to {self.provider} model: {self.model}")

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
                    f"{self.base_url}/api/chat",
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"❌ Safety check failed with status {response.status}: {error_text}")
                        return False, "I cannot assist with that type of request."

                    data = await response.json()
                    model_response = data.get("message", {}).get("content", "").strip()
                    
                    # Clean up the model response to handle potential whitespace and line break issues
                    model_response = ' '.join(model_response.split())
                    
                    end_time = asyncio.get_event_loop().time()

                    # Log timing and response
                    logger.debug(f"⏱️ Safety check completed in {end_time - start_time:.3f}s")
                    logger.debug(f"🔄 Safety check raw response: '{model_response}'")

                    # Process the response to determine safety
                    is_safe, refusal_message = await self._process_safety_response(model_response)

                    # Add more visible logging with emojis
                    if is_safe:
                        logger.debug("✅ LLM SAFETY CHECK PASSED: Query was deemed SAFE")
                    else:
                        logger.debug("🛑 LLM SAFETY CHECK BLOCKED: Query was deemed UNSAFE")

                    return is_safe, refusal_message

            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Safety check timed out (attempt {attempt+1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    logger.debug(f"🔄 Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error("❌ Safety check failed after all retry attempts")
                    # After all retries fail, default to allowing the query through if configured
                    if self.allow_on_timeout:
                        logger.warning("⚠️ Allowing query through due to allow_on_timeout setting")
                        return True, None
                    logger.warning("🚫 Blocking query after timeout")
                    return False, "I cannot assist with that request due to a service issue. Please try again later."
            except Exception as e:
                logger.error(f"❌ Error in safety check: {str(e)}", exc_info=True)
                if attempt < self.max_retries - 1:
                    logger.debug(f"🔄 Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    # If all retries fail, fallback to default response
                    logger.warning("🚫 Blocking query after error")
                    return False, "I cannot assist with that type of request."
    
    async def _process_safety_response(self, model_response: str) -> Tuple[bool, Optional[str]]:
            """
            Process the LLM response to determine if the query is safe.
            
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
            
            # If we detect refusal phrases in the response, consider it unsafe
            if any(phrase in model_response.lower() for phrase in direct_refusal_phrases):
                logger.warning(f"Model directly responded with refusal message: '{model_response}'")
                # Since the model directly refused, treat this as unsafe
                return False, model_response
            
            # Pattern matching for safety responses
            expected_exact = "SAFE: true"
            alt_expected = '"SAFE: true"'  # With double quotes
            
            # Check exact match first - allow for both quoted and unquoted versions
            is_safe_exact = model_response == expected_exact or model_response == alt_expected
            is_safe_fuzzy = False
            
            # If no exact match and fuzzy mode is enabled, check for fuzzy matches
            if not is_safe_exact and self.safety_mode == 'fuzzy':
                is_safe_fuzzy = self._is_likely_safe_response(model_response)
                if is_safe_fuzzy:
                    logger.warning(f"Safety check used fuzzy matching. Expected '{expected_exact}' but got '{model_response}'")
            
            # Use either exact or fuzzy match result based on safety mode
            is_safe = is_safe_exact or (self.safety_mode == 'fuzzy' and is_safe_fuzzy)

            logger.debug(f"Safety check result: mode={self.safety_mode}, exact={is_safe_exact}, fuzzy={is_safe_fuzzy}, final={is_safe}")

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
                    logger.debug("Query correctly identified as unsafe")
                else:
                    # This is an unrecognized format
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
