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
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the LLM Guard service with configuration"""
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Get LLM Guard configuration
        self.llm_guard_config = config.get('llm_guard', {})
        self.enabled = self.llm_guard_config.get('enabled', False)
        
        # Initialize all attributes regardless of enabled status
        # Service connection settings
        service_config = self.llm_guard_config.get('service', {})
        self.base_url = service_config.get('base_url', 'http://localhost:8000')
        self.api_version = service_config.get('api_version', 'v1')
        
        # Timeout settings
        timeout_config = service_config.get('timeout', {})
        self.connect_timeout = timeout_config.get('connect', 10)
        self.read_timeout = timeout_config.get('read', 30)
        self.total_timeout = timeout_config.get('total', 60)
        
        # Retry configuration
        retry_config = service_config.get('retry', {})
        self.max_attempts = retry_config.get('max_attempts', 3)
        self.backoff_factor = retry_config.get('backoff_factor', 0.3)
        self.retry_status_codes = retry_config.get('status_forcelist', [500, 502, 503, 504])
        
        # Health check settings
        health_config = service_config.get('health_check', {})
        self.health_endpoint = health_config.get('endpoint', '/health')
        self.health_interval = health_config.get('interval', 30)
        self.health_timeout = health_config.get('timeout', 5)
        
        # Security check defaults
        security_config = self.llm_guard_config.get('security_check', {})
        self.default_risk_threshold = security_config.get('default_risk_threshold', 0.5)
        self.default_scanners = security_config.get('default_scanners', [])
        self.available_input_scanners = security_config.get('available_input_scanners', [])
        self.available_output_scanners = security_config.get('available_output_scanners', [])
        
        # Error handling configuration
        error_config = self.llm_guard_config.get('error_handling', {})
        self.fallback_behavior = error_config.get('fallback', {}).get('on_service_unavailable', 'allow')
        self.default_safe_response = error_config.get('fallback', {}).get('default_safe_response', {
            "is_safe": True,
            "risk_score": 0.0,
            "sanitized_content": None,
            "flagged_scanners": [],
            "recommendations": ["Service temporarily unavailable - content not scanned"]
        })
        
        # Client defaults
        defaults_config = self.llm_guard_config.get('defaults', {})
        self.metadata = defaults_config.get('metadata', {})
        self.include_timestamp = defaults_config.get('include_timestamp', True)
        self.default_user_id = defaults_config.get('user_id', None)
        
        # Validation settings
        validation_config = self.llm_guard_config.get('validation', {})
        self.max_content_length = validation_config.get('max_content_length', 10000)
        self.valid_content_types = validation_config.get('valid_content_types', ['prompt', 'response'])
        
        # Initialize state - always initialize these attributes
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_health_check = 0
        self._service_healthy = None
        self._initialized = False
        
        if not self.enabled:
            logger.info("LLM Guard service is disabled")
        else:
            logger.info(f"LLM Guard service initialized - Base URL: {self.base_url}")
    
    async def initialize(self) -> None:
        """Initialize the service"""
        if not self.enabled:
            logger.info("LLM Guard service is disabled, skipping initialization")
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
        await self._check_service_health()
        
        self._initialized = True
        logger.info("LLM Guard service initialized successfully")
    
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
            
            async with self._session.get(url, timeout=self.health_timeout) as response:
                if response.status == 200:
                    health_data = await response.json()
                    self._service_healthy = True
                    self._last_health_check = current_time
                    
                    if self.verbose:
                        logger.info(f"LLM Guard service health check passed: {health_data}")
                    
                    return True
                else:
                    logger.warning(f"LLM Guard service health check failed with status: {response.status}")
                    self._service_healthy = False
                    return False
                    
        except Exception as e:
            logger.error(f"LLM Guard service health check failed: {sanitize_error_message(str(e))}")
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
            logger.debug("LLM Guard service is disabled, returning safe response")
            return {
                "is_safe": True,
                "risk_score": 0.0,
                "sanitized_content": content,
                "flagged_scanners": [],
                "recommendations": ["LLM Guard service is disabled"]
            }
        
        # Validate inputs
        self._validate_security_check_input(content, content_type, risk_threshold)
        
        # Use defaults if not provided
        if risk_threshold is None:
            risk_threshold = self.default_risk_threshold
        
        if scanners is None:
            scanners = self.default_scanners
        
        # Build metadata
        request_metadata = self.metadata.copy()
        if metadata:
            request_metadata.update(metadata)
        
        if self.include_timestamp:
            request_metadata['timestamp'] = datetime.now(UTC).isoformat()
        
        # Build request payload
        payload = {
            "content": content,
            "content_type": content_type,
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
                logger.info(f"Security check request: {content_type}, risk_threshold: {risk_threshold}")
            
            result = await self._make_request_with_retry("POST", url, payload)
            
            if self.verbose:
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"Security check completed in {elapsed:.2f}ms")
            
            return result
            
        except Exception as e:
            logger.error(f"Security check failed: {sanitize_error_message(str(e))}")
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
            logger.debug("LLM Guard service is disabled, returning original content")
            return {
                "sanitized_content": content,
                "changes_made": False,
                "removed_items": []
            }
        
        # Validate content length
        if len(content) > self.max_content_length:
            raise ValueError(f"Content length {len(content)} exceeds maximum {self.max_content_length}")
        
        url = f"{self.base_url}/{self.api_version}/security/sanitize"
        payload = {"content": content}
        
        try:
            result = await self._make_request_with_retry("POST", url, payload)
            return result
            
        except Exception as e:
            logger.error(f"Content sanitization failed: {sanitize_error_message(str(e))}")
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
        
        last_exception = None
        
        for attempt in range(self.max_attempts):
            try:
                kwargs = {}
                if data is not None:
                    kwargs['json'] = data
                
                async with self._session.request(method, url, **kwargs) as response:
                    if response.status in self.retry_status_codes:
                        if attempt < self.max_attempts - 1:
                            delay = self.backoff_factor * (2 ** attempt)
                            logger.warning(f"Request failed with status {response.status}, retrying in {delay}s")
                            await asyncio.sleep(delay)
                            continue
                    
                    response.raise_for_status()
                    return await response.json()
                    
            except Exception as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    delay = self.backoff_factor * (2 ** attempt)
                    logger.warning(f"Request attempt {attempt + 1} failed: {sanitize_error_message(str(e))}, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    break
        
        # All retries exhausted
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
        return await self._check_service_health()
    
    async def get_service_info(self) -> Dict[str, Any]:
        """Get information about the LLM Guard service"""
        return {
            "enabled": self.enabled,
            "base_url": self.base_url if self.enabled else None,
            "api_version": self.api_version if self.enabled else None,
            "healthy": await self.is_service_healthy() if self.enabled else False,
            "default_risk_threshold": self.default_risk_threshold,
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