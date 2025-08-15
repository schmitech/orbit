#!/usr/bin/env python3
"""
LLM Guard Service

This service provides security checking and content sanitization capabilities
by integrating with the LLM Guard API. It handles prompt injection detection,
toxicity screening, content sanitization, and other security features.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, UTC

import aiohttp
from fastapi import HTTPException

from utils.text_utils import sanitize_error_message

# Configure logging
logger = logging.getLogger(__name__)


class LLMGuardService:
    """Service for LLM Guard security checking and content sanitization"""

    # Basic singleton support to avoid multiple instantiations
    _instance = None

    @classmethod
    def get_instance(cls, config: Dict[str, Any]) -> "LLMGuardService":
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the LLM Guard service with configuration"""
        # If already initialized via singleton path, bail early
        if getattr(self, "_initialized_config", False):
            return

        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Get LLM Guard configuration
        self.llm_guard_config = config.get('llm_guard', {})
        
        # Check if enabled field exists
        if 'enabled' in self.llm_guard_config:
            # Structure with explicit enabled field
            self.enabled = self.llm_guard_config.get('enabled', False)
        else:
            # Simplified structure - if section exists, it's enabled
            self.enabled = bool(self.llm_guard_config)
        
        # Initialize all attributes regardless of enabled status
        # Service connection settings
        service_config = self.llm_guard_config.get('service', {})
        self.base_url = service_config.get('base_url', 'http://localhost:8000')
        self.api_version = 'v1'  # Default API version
        
        # Timeout settings
        # Keep prior behavior for backward compat, but add a per-request override
        self.timeout = service_config.get('timeout', 30)
        self.connect_timeout = service_config.get('connect_timeout', 5)
        self.read_timeout = service_config.get('read_timeout', self.timeout)
        self.total_timeout = service_config.get('total_timeout', self.timeout)
        # Per-request total timeout used for guard calls; defaults to min(total, 10)
        self.request_timeout = service_config.get('request_timeout', min(self.total_timeout, 10))
        
        # Retry configuration - now configurable
        self.max_attempts = int(service_config.get('max_attempts', 2))
        self.backoff_factor = float(service_config.get('backoff_factor', 0.4))
        self.retry_status_codes = service_config.get('retry_status_codes', [500, 502, 503, 504])
        
        # Health check settings
        self.health_endpoint = '/health'
        self.health_interval = int(service_config.get('health_interval', 30))
        self.health_timeout = int(service_config.get('health_timeout', 5))
        
        # Security check defaults - load from configuration
        security_config = self.llm_guard_config.get('security', {})
        self.default_risk_threshold = security_config.get('risk_threshold', 0.6)
        
        # Available scanners (for reference/validation)
        self.available_input_scanners = [
            "anonymize", "ban_substrings", "ban_topics", "code",
            "prompt_injection", "secrets", "toxicity"
        ]
        self.available_output_scanners = [
            "bias", "no_refusal", "relevance", "sensitive"
        ]
        
        # Load scanner configurations from config
        scanner_config = security_config.get('scanners', {})
        self.configured_prompt_scanners = scanner_config.get('prompt', [])
        self.configured_response_scanners = scanner_config.get('response', [])
        
        # Validate configured scanners
        self._validate_scanner_configuration()
        
        # Error handling configuration - simplified structure
        fallback_config = self.llm_guard_config.get('fallback', {})
        self.fallback_behavior = fallback_config.get('on_error', 'allow')
        self.default_safe_response = {
            "is_safe": True,
            "risk_score": 0.0,
            "sanitized_content": None,
            "flagged_scanners": [],
            "recommendations": ["Service temporarily unavailable - content not scanned"]
        }
        
        # Client defaults - use defaults
        self.metadata = {
            'client_name': 'orbit-server',
            'client_version': '1.0.0'
        }
        self.include_timestamp = True
        self.default_user_id = None
        
        # Validation settings - use defaults
        self.max_content_length = 10000
        self.valid_content_types = ['prompt', 'response']
        
        # Circuit breaker configuration
        self.failure_threshold = int(service_config.get('failure_threshold', 3))
        self.circuit_reset_timeout = int(service_config.get('circuit_reset_timeout', 60))

        # Initialize state - always initialize these attributes
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_health_check = 0
        self._service_healthy = None
        self._initialized = False
        self._service_available = False
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._initialized_config = True
        
        if not self.enabled:
            logger.info("🚫 LLM Guard service is disabled")
        else:
            logger.info(f"✅ LLM Guard service initialized - Base URL: {self.base_url}")
            if self.verbose:
                logger.info(f"✅ LLM Guard Configuration:")
                logger.info(f"  Base URL: {self.base_url}")
                logger.info(f"  API Version: {self.api_version}")
                logger.info(f"  Timeout: {self.timeout}s")
                logger.info(f"  Default Risk Threshold: {self.default_risk_threshold}")
                logger.info(f"  Fallback Behavior: {self.fallback_behavior}")
                logger.info(f"  Configured Prompt Scanners: {self.configured_prompt_scanners}")
                logger.info(f"  Configured Response Scanners: {self.configured_response_scanners}")
                logger.info(f"  Available Input Scanners: {len(self.available_input_scanners)}")
                logger.info(f"  Available Output Scanners: {len(self.available_output_scanners)}")
    
    async def initialize(self) -> None:
        """Initialize the service"""
        if not self.enabled:
            logger.info("🚫 LLM Guard service is disabled, skipping initialization")
            return
            
        # Create aiohttp session with timeout and retry configuration
        timeout = aiohttp.ClientTimeout(
            connect=self.connect_timeout,
            sock_read=self.read_timeout,
            total=self.total_timeout
        )
        
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': f"Orbit-LLM-Guard-Client/{self.metadata.get('client_version', '1.0.0')}"
            }
        )
        
        # Perform initial health check
        health_check_passed = await self._check_service_health()
        
        if not health_check_passed:
            logger.error("❌ LLM Guard service health check failed - cancelling initialization")
            # Close the session since we won't be using it
            await self._session.close()
            self._session = None
            self._initialized = False
            self._service_available = False
            return
        
        self._initialized = True
        self._service_available = True
        logger.info("✅ LLM Guard service initialized successfully")

    def _is_circuit_open(self) -> bool:
        """Return True if circuit breaker is currently open."""
        return time.time() < self._circuit_open_until

    def _trip_circuit(self) -> None:
        """Open the circuit to prevent further calls for a cooldown period."""
        self._circuit_open_until = time.time() + self.circuit_reset_timeout
        self._service_available = False
        logger.warning(
            f"🔌 LLM Guard circuit opened for {self.circuit_reset_timeout}s after repeated failures"
        )

    def _record_success(self) -> None:
        self._failure_count = 0
        self._service_available = True
    
    async def _check_service_health(self) -> bool:
        """Check if the LLM Guard service is healthy"""
        if not self.enabled or not self._session:
            return False
            
        current_time = time.time()
        
        # Use cached health status if recent
        if (self._service_healthy is not None and 
            current_time - self._last_health_check < self.health_interval):
            return self._service_healthy
        
        try:
            url = f"{self.base_url}{self.health_endpoint}"
            
            if self.verbose:
                logger.info(f"🏥 LLM Guard health check: {url}")
            
            async with self._session.get(url, timeout=self.health_timeout) as response:
                if response.status == 200:
                    health_data = await response.json()
                    self._service_healthy = True
                    self._last_health_check = current_time
                    
                    if self.verbose:
                        logger.info(f"✅ LLM Guard service health check passed: {health_data}")
                    else:
                        logger.info(f"✅ LLM Guard service health check passed")
                    
                    return True
                else:
                    logger.warning(f"⚠️ LLM Guard service health check failed with status: {response.status}")
                    self._service_healthy = False
                    return False
                    
        except Exception as e:
            logger.error(f"❌ LLM Guard service health check failed: {sanitize_error_message(str(e))}")
            self._service_healthy = False
            return False
    
    async def check_security(
        self,
        content: str,
        content_type: str = "prompt",
        scanners: Optional[List[str]] = None,
        risk_threshold: Optional[float] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform security check on content
        
        Args:
            content: The content to check
            content_type: Type of content ('prompt' or 'response')
            scanners: List of scanners to use (if None, uses defaults)
            risk_threshold: Risk threshold (0.0-1.0)
            user_id: User ID for tracking
            metadata: Additional metadata
            
        Returns:
            Dictionary with security check results
        """
        if not self.enabled:
            logger.debug("🚫 LLM Guard service is disabled, returning safe response")
            return {
                "is_safe": True,
                "risk_score": 0.0,
                "sanitized_content": content,
                "flagged_scanners": [],
                "recommendations": ["LLM Guard service is disabled"]
            }
        
        # Check if service is available (initialized and healthy)
        if not self._service_available or self._is_circuit_open():
            logger.warning("🚫 LLM Guard service is not available (health check failed during initialization), returning safe response")
            return {
                "is_safe": True,
                "risk_score": 0.0,
                "sanitized_content": content,
                "flagged_scanners": [],
                "recommendations": ["LLM Guard service is not available"]
            }
        
        # Validate inputs
        self._validate_security_check_input(content, content_type, risk_threshold)
        
        # Map content type for server
        server_content_type = self._map_content_type_for_server(content_type)
        
        # Use defaults if not provided
        if risk_threshold is None:
            risk_threshold = self.default_risk_threshold
        
        if scanners is None:
            # Use configured scanners based on content type
            if content_type == "prompt":
                scanners = self.configured_prompt_scanners
            elif content_type == "response":
                scanners = self.configured_response_scanners
            else:
                scanners = []
            
            # Log which scanners are being used
            if self.verbose and scanners:
                logger.info(f"🔧 Using configured {content_type} scanners: {scanners}")
        
        # Build metadata
        request_metadata = self.metadata.copy()
        if metadata:
            request_metadata.update(metadata)
        
        if self.include_timestamp:
            request_metadata['timestamp'] = datetime.now(UTC).isoformat()
        
        # Build request payload
        payload = {
            "content": content,
            "content_type": server_content_type,  # Use mapped content type
            "risk_threshold": risk_threshold,
            "metadata": request_metadata
        }
        
        if scanners:
            payload["scanners"] = scanners
            
        if user_id or self.default_user_id:
            payload["user_id"] = user_id or self.default_user_id
        
        # Make API call with retry logic
        url = f"{self.base_url}/{self.api_version}/security/check"
        
        start_time = time.time()
        
        try:
            if self.verbose:
                logger.info(f"🔍 Performing LLM Guard security check for {content_type}: '{content[:50]}...'")
                logger.info(f"📊 Risk threshold: {risk_threshold}")
                if scanners:
                    logger.info(f"🔧 Using scanners: {scanners}")
                if user_id:
                    logger.info(f"👤 User ID: {user_id}")
            
            result = await self._make_request_with_retry("POST", url, payload)

            if self.verbose:
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"⏱️ LLM Guard security check completed in {elapsed:.2f}ms")
                
                # Log detailed results with emojis
                risk_score = result.get('risk_score', 0.0)
                is_safe = result.get('is_safe', True)
                flagged_scanners = result.get('flagged_scanners', [])
                recommendations = result.get('recommendations', [])
                
                if is_safe:
                    logger.info(f"✅ LLM GUARD PASSED: Content was deemed SAFE")
                    if risk_score > 0.0:
                        logger.info(f"⚠️ Low risk detected: {risk_score:.3f}")
                else:
                    logger.info(f"🛑 LLM GUARD BLOCKED: Content was flagged as UNSAFE")
                    logger.info(f"🚨 Risk score: {risk_score:.3f}")
                    if flagged_scanners:
                        logger.info(f"🚩 Flagged by scanners: {flagged_scanners}")
                    if recommendations:
                        logger.info(f"💡 Recommendations: {'; '.join(recommendations)}")
                
                # Log content preview (first 100 chars)
                content_preview = content[:100] + "..." if len(content) > 100 else content
                logger.debug(f"📝 Content preview: {content_preview}")
                
                # Log if content was sanitized
                sanitized_content = result.get('sanitized_content')
                if sanitized_content and sanitized_content != content:
                    sanitized_preview = sanitized_content[:100] + "..." if len(sanitized_content) > 100 else sanitized_content
                    logger.info(f"🧹 Content was sanitized: {sanitized_preview}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ LLM Guard security check failed: {sanitize_error_message(str(e))}")
            return await self._handle_service_error(content, e)
    
    async def sanitize_content(self, content: str) -> Dict[str, Any]:
        """
        Sanitize content by removing or masking sensitive information
        
        Args:
            content: The content to sanitize
            
        Returns:
            Dictionary with sanitized content
        """
        if not self.enabled:
            logger.debug("🚫 LLM Guard service is disabled, returning original content")
            return {
                "sanitized_content": content,
                "changes_made": False,
                "removed_items": []
            }
        
        # Check if service is available (initialized and healthy)
        if not self._service_available or self._is_circuit_open():
            logger.warning("🚫 LLM Guard service is not available (health check failed during initialization), returning original content")
            return {
                "sanitized_content": content,
                "changes_made": False,
                "removed_items": [],
                "error": "LLM Guard service is not available"
            }
        
        # Validate content length
        if len(content) > self.max_content_length:
            raise ValueError(f"Content length {len(content)} exceeds maximum {self.max_content_length}")
        
        url = f"{self.base_url}/{self.api_version}/security/sanitize"
        payload = {"content": content}
        
        start_time = time.time()
        
        try:
            if self.verbose:
                logger.info(f"🧹 Performing content sanitization")
                content_preview = content[:100] + "..." if len(content) > 100 else content
                logger.debug(f"📝 Content preview: {content_preview}")
            
            result = await self._make_request_with_retry("POST", url, payload)
            
            if self.verbose:
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"⏱️ Content sanitization completed in {elapsed:.2f}ms")
                
                # Log sanitization results with emojis
                changes_made = result.get('changes_made', False)
                removed_items = result.get('removed_items', [])
                sanitized_content = result.get('sanitized_content', content)
                
                if changes_made:
                    logger.info(f"✅ Content sanitized successfully")
                    if removed_items:
                        logger.info(f"🗑️ Removed items: {removed_items}")
                    if sanitized_content != content:
                        sanitized_preview = sanitized_content[:100] + "..." if len(sanitized_content) > 100 else sanitized_content
                        logger.info(f"🧹 Sanitized content: {sanitized_preview}")
                else:
                    logger.info(f"✅ Content unchanged - no sanitization needed")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Content sanitization failed: {sanitize_error_message(str(e))}")
            # Return original content as fallback
            return {
                "sanitized_content": content,
                "changes_made": False,
                "removed_items": [],
                "error": "Sanitization service unavailable"
            }
    
    async def get_available_scanners(self) -> Dict[str, List[str]]:
        """Get list of available scanners from the service"""
        if not self.enabled:
            return {
                "input_scanners": self.available_input_scanners,
                "output_scanners": self.available_output_scanners
            }
        
        # Check if service is available (initialized and healthy)
        if not self._service_available or self._is_circuit_open():
            logger.warning("🚫 LLM Guard service is not available (health check failed during initialization), returning configured defaults")
            return {
                "input_scanners": self.available_input_scanners,
                "output_scanners": self.available_output_scanners
            }
        
        try:
            url = f"{self.base_url}/{self.api_version}/security/scanners"
            result = await self._make_request_with_retry("GET", url)
            return result
            
        except Exception as e:
            logger.error(f"Failed to get available scanners: {sanitize_error_message(str(e))}")
            # Return configured defaults as fallback
            return {
                "input_scanners": self.available_input_scanners,
                "output_scanners": self.available_output_scanners
            }
    
    async def _make_request_with_retry(
        self,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        if not self._session:
            raise RuntimeError("Service not initialized")

        # Check if service is available
        if not self._service_available or self._is_circuit_open():
            raise RuntimeError("LLM Guard service is not available (health check failed during initialization)")

        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                kwargs = {}
                if data is not None:
                    kwargs['json'] = data
                # Apply a stricter per-request total timeout to avoid long hangs
                kwargs['timeout'] = aiohttp.ClientTimeout(total=self.request_timeout)

                async with self._session.request(method, url, **kwargs) as response:
                    if response.status in self.retry_status_codes:
                        if attempt < self.max_attempts - 1:
                            delay = self.backoff_factor * (2 ** attempt)
                            logger.warning(f"Request failed with status {response.status}, retrying in {delay}s")
                            await asyncio.sleep(delay)
                            self._failure_count += 1
                            if self._failure_count >= self.failure_threshold:
                                self._trip_circuit()
                            continue
                    
                    # Handle 422 errors with detailed logging
                    if response.status == 422:
                        try:
                            error_detail = await response.text()
                            logger.error(f"422 Unprocessable Entity - Request payload validation failed: {error_detail}")
                            if data and self.verbose:
                                logger.error(f"Request payload that failed: {data}")
                        except:
                            pass
                    
                    response.raise_for_status()
                    result = await response.json()
                    # Success resets breaker state
                    self._record_success()
                    return result
                    
            except Exception as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    delay = self.backoff_factor * (2 ** attempt)
                    logger.warning(f"Request attempt {attempt + 1} failed: {sanitize_error_message(str(e))}, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    self._failure_count += 1
                    if self._failure_count >= self.failure_threshold:
                        self._trip_circuit()
                    continue
                else:
                    break

        # All retries exhausted
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._trip_circuit()
        raise last_exception or RuntimeError("All retry attempts failed")
    
    async def _handle_service_error(self, content: str, error: Exception) -> Dict[str, Any]:
        """Handle service errors according to fallback configuration"""
        if self.fallback_behavior == "allow":
            logger.warning("Service unavailable, falling back to 'allow'")
            return self.default_safe_response.copy()
        elif self.fallback_behavior == "block":
            logger.warning("Service unavailable, falling back to 'block'")
            return {
                "is_safe": False,
                "risk_score": 1.0,
                "sanitized_content": content,
                "flagged_scanners": ["service_unavailable"],
                "recommendations": ["Service temporarily unavailable - content blocked as precaution"]
            }
        else:
            # Re-raise the exception if no fallback behavior is configured
            raise error
    
    def _validate_scanner_configuration(self) -> None:
        """Validate that configured scanners are supported"""
        # Validate prompt scanners
        invalid_prompt_scanners = [
            scanner for scanner in self.configured_prompt_scanners 
            if scanner not in self.available_input_scanners
        ]
        if invalid_prompt_scanners:
            logger.warning(f"Invalid prompt scanners in configuration: {invalid_prompt_scanners}")
            logger.warning(f"Available prompt scanners: {self.available_input_scanners}")
            # Remove invalid scanners
            self.configured_prompt_scanners = [
                scanner for scanner in self.configured_prompt_scanners 
                if scanner in self.available_input_scanners
            ]
        
        # Validate response scanners
        invalid_response_scanners = [
            scanner for scanner in self.configured_response_scanners 
            if scanner not in self.available_output_scanners
        ]
        if invalid_response_scanners:
            logger.warning(f"Invalid response scanners in configuration: {invalid_response_scanners}")
            logger.warning(f"Available response scanners: {self.available_output_scanners}")
            # Remove invalid scanners
            self.configured_response_scanners = [
                scanner for scanner in self.configured_response_scanners 
                if scanner in self.available_output_scanners
            ]
        
        if self.verbose:
            logger.info(f"Scanner validation complete:")
            logger.info(f"  Valid prompt scanners: {self.configured_prompt_scanners}")
            logger.info(f"  Valid response scanners: {self.configured_response_scanners}")

    def _map_content_type_for_server(self, content_type: str) -> str:
        """Map client content types to server-expected content types"""
        content_type_mapping = {
            "prompt": "prompt",      # User input -> prompt
            "response": "output"     # AI response -> output
        }
        
        mapped_type = content_type_mapping.get(content_type, content_type)
        
        if self.verbose and mapped_type != content_type:
            logger.info(f"Mapped content_type '{content_type}' to '{mapped_type}' for server")
        
        return mapped_type

    def _validate_security_check_input(
        self,
        content: str,
        content_type: str,
        risk_threshold: Optional[float]
    ) -> None:
        """Validate input parameters for security check"""
        # Validate content length
        if len(content) > self.max_content_length:
            raise ValueError(f"Content length {len(content)} exceeds maximum {self.max_content_length}")
        
        # Validate content type
        if content_type not in self.valid_content_types:
            raise ValueError(f"Invalid content_type. Must be one of: {self.valid_content_types}")
        
        # Validate risk threshold
        if risk_threshold is not None:
            if not (0.0 <= risk_threshold <= 1.0):
                raise ValueError(f"Risk threshold must be between 0.0 and 1.0, got: {risk_threshold}")
    
    async def is_service_healthy(self) -> bool:
        """Check if the LLM Guard service is currently healthy"""
        if not self.enabled:
            return False
        
        # If service is not available (failed initialization), return False
        if not self._service_available or self._is_circuit_open():
            return False
            
        return await self._check_service_health()
    
    async def get_service_info(self) -> Dict[str, Any]:
        """Get information about the LLM Guard service"""
        return {
            "enabled": self.enabled,
            "base_url": self.base_url if self.enabled else None,
            "api_version": self.api_version if self.enabled else None,
            "available": self._service_available if self.enabled else False,
            "healthy": await self.is_service_healthy() if self.enabled else False,
            "default_risk_threshold": self.default_risk_threshold,
            "configured_prompt_scanners": self.configured_prompt_scanners if self.enabled else [],
            "configured_response_scanners": self.configured_response_scanners if self.enabled else [],
            "available_input_scanners": self.available_input_scanners,
            "available_output_scanners": self.available_output_scanners,
            "max_content_length": self.max_content_length,
            "fallback_behavior": self.fallback_behavior if self.enabled else None
        }
    
    async def close(self) -> None:
        """Close the service and cleanup resources"""
        if hasattr(self, '_session') and self._session:
            await self._session.close()
            self._session = None
        
        logger.info("LLM Guard service closed")
        # Allow re-creation if needed
        type(self)._instance = None
