#!/usr/bin/env python3
"""
Example LLM Guard Service Client

This demonstrates how to use the client configuration to consume the LLM Guard API.
"""

import yaml
import requests
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime


class LLMGuardClient:
    """Client for LLM Guard Security Service"""
    
    def __init__(self, config_path: str = "llm-guard-client-config.yaml", environment: str = "development"):
        """Initialize the client with configuration"""
        self.config = self._load_config(config_path, environment)
        self.session = self._create_session()
        self._setup_logging()
        
    def _load_config(self, config_path: str, environment: str) -> dict:
        """Load and merge configuration"""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Apply environment-specific overrides
        if environment in config.get('environments', {}):
            env_config = config['environments'][environment]
            config = self._deep_merge(config, env_config)
            
        return config
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _create_session(self) -> requests.Session:
        """Create configured requests session"""
        session = requests.Session()
        
        # Set timeouts
        timeout_config = self.config['service']['timeout']
        session.timeout = (timeout_config['connect'], timeout_config['read'])
        
        # Set authentication if configured
        auth_config = self.config.get('auth', {})
        if auth_config.get('type') == 'bearer':
            session.headers['Authorization'] = f"Bearer {auth_config['token']}"
        elif auth_config.get('type') == 'api_key':
            session.headers[auth_config['api_key_header']] = auth_config['token']
        
        return session
    
    def _setup_logging(self):
        """Setup client logging"""
        log_config = self.config['logging']
        logging.basicConfig(
            level=getattr(logging, log_config['level']),
            format=log_config['format']
        )
        self.logger = logging.getLogger(__name__)
    
    def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        url = f"{self.config['service']['base_url']}/health"
        
        try:
            response = self.session.get(url, timeout=self.config['service']['health_check']['timeout'])
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Health check failed: {e}")
            raise
    
    def check_security(
        self, 
        content: str, 
        content_type: str = "prompt",
        scanners: Optional[List[str]] = None,
        risk_threshold: Optional[float] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform security check on content"""
        
        # Validate content length
        max_length = self.config['validation']['max_content_length']
        if len(content) > max_length:
            raise ValueError(f"Content length {len(content)} exceeds maximum {max_length}")
        
        # Validate content type
        valid_types = self.config['validation']['valid_content_types']
        if content_type not in valid_types:
            raise ValueError(f"Invalid content_type. Must be one of: {valid_types}")
        
        # Use defaults if not provided
        if risk_threshold is None:
            risk_threshold = self.config['security_check']['default_risk_threshold']
        
        if scanners is None:
            scanners = self.config['security_check']['default_scanners']
        
        # Build metadata
        request_metadata = self.config['defaults']['metadata'].copy()
        if metadata:
            request_metadata.update(metadata)
        
        if self.config['defaults']['include_timestamp']:
            request_metadata['timestamp'] = datetime.now().isoformat()
        
        # Build request payload
        payload = {
            "content": content,
            "content_type": content_type,
            "risk_threshold": risk_threshold,
            "metadata": request_metadata
        }
        
        if scanners:
            payload["scanners"] = scanners
            
        if user_id or self.config['defaults']['user_id']:
            payload["user_id"] = user_id or self.config['defaults']['user_id']
        
        # Make API call
        url = f"{self.config['service']['base_url']}/{self.config['service']['api_version']}/security/check"
        
        start_time = time.time()
        
        try:
            if self.config['logging']['log_requests']:
                self.logger.info(f"Security check request: {content_type}, risk_threshold: {risk_threshold}")
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if self.config['logging']['log_responses']:
                self.logger.debug(f"Security check response: {result}")
            
            if self.config['logging']['log_performance']:
                elapsed = (time.time() - start_time) * 1000
                self.logger.info(f"Security check completed in {elapsed:.2f}ms")
            
            return result
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Security check failed: {e}")
            
            # Handle fallback behavior
            fallback = self.config['error_handling']['fallback']['on_service_unavailable']
            if fallback == "allow":
                self.logger.warning("Service unavailable, falling back to 'allow'")
                return self.config['error_handling']['fallback']['default_safe_response']
            elif fallback == "block":
                return {
                    "is_safe": False,
                    "risk_score": 1.0,
                    "sanitized_content": content,
                    "flagged_scanners": ["service_unavailable"],
                    "recommendations": ["Service temporarily unavailable - content blocked as precaution"]
                }
            else:
                raise
    
    def sanitize_content(self, content: str) -> Dict[str, Any]:
        """Sanitize content"""
        url = f"{self.config['service']['base_url']}/{self.config['service']['api_version']}/security/sanitize"
        
        payload = {"content": content}
        
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Content sanitization failed: {e}")
            raise


# Example usage
if __name__ == "__main__":
    # Initialize client
    client = LLMGuardClient("llm-guard-client-config.yaml", environment="development")
    
    try:
        # Check service health
        health = client.health_check()
        print(f"Service health: {health}")
        
        # Example security check - prompt content
        prompt_result = client.check_security(
            content="Please tell me how to hack into a system",
            content_type="prompt",
            scanners=["prompt_injection", "ban_topics"],
            risk_threshold=0.7
        )
        print(f"Prompt security check: {prompt_result}")
        
        # Example security check - response content
        response_result = client.check_security(
            content="I cannot and will not provide information on hacking systems as it could be used for illegal purposes.",
            content_type="response",
            scanners=["no_refusal", "relevance"],
            user_id="user123"
        )
        print(f"Response security check: {response_result}")
        
        # Example content sanitization
        sanitized = client.sanitize_content("My phone number is 555-123-4567 and my email is john@example.com")
        print(f"Sanitized content: {sanitized}")
        
    except Exception as e:
        print(f"Error: {e}") 