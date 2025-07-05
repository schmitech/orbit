"""
Configuration summary logging utilities for the inference server.

This module handles logging comprehensive configuration summaries, including:
- Server mode and provider configurations
- Service settings and capabilities
- API settings and security configurations
- Model information and endpoint details
- System monitoring and debugging information
"""

import logging
import sys
from typing import Dict, Any, Optional, NoReturn
from fastapi import FastAPI
from config.config_manager import _is_true_value


class ConfigurationSummaryLogger:
    """
    Handles comprehensive configuration summary logging for the inference server.
    
    This class is responsible for:
    - Logging server configuration overviews
    - Providing detailed provider and service information
    - Formatting configuration data for easy reading
    - Supporting debugging and system monitoring
    - Generating documentation-ready configuration reports
    """
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Initialize the ConfigurationSummaryLogger.
        
        Args:
            config: The application configuration dictionary
            logger: Logger instance for configuration summary logging
        """
        self.config = config
        self.logger = logger
    
    def _log_message(self, message: str, level: str = 'info', indent: int = 0) -> None:
        """
        Log a message with consistent formatting and avoid duplication.
        
        Args:
            message: The message to log
            level: The log level ('info', 'warning', 'error')
            indent: Number of spaces to indent the message
        """
        formatted_message = " " * indent + message
        
        # Log to the configured logger
        if level == 'warning':
            self.logger.warning(formatted_message)
        elif level == 'error':
            self.logger.error(formatted_message)
        else:
            self.logger.info(formatted_message)
    
    def log_configuration_summary(self, app: Optional[FastAPI] = None) -> None:
        """
        Log a comprehensive summary of the server configuration.
        
        Args:
            app: Optional FastAPI application instance for accessing runtime state
        """
        try:
            # Header
            self._log_message("=" * 50)
            self._log_message("Server Configuration Summary")
            self._log_message("=" * 50)
            
            # Core Configuration
            self._log_server_mode()
            self._log_provider_configurations()
            
            # Security Configuration
            self._log_security_configurations()
            
            # Service Configuration
            self._log_service_configurations()
            
            # API Configuration
            self._log_api_configurations()
            
            # Model and Runtime Information
            self._log_model_information()
            if app:
                self._log_runtime_information(app)
            
            # Endpoint Information
            self._log_endpoint_information()
            
            # System Settings
            self._log_system_settings()
            
            # Footer
            self._log_message("=" * 50)
            self._log_message("✅ Server is ready and accepting requests")
            self._log_message("=" * 50)
            
        except Exception as e:
            self._log_message(f"Error logging configuration summary: {str(e)}", level='error')
    
    def _log_server_mode(self) -> None:
        """Log server mode and operational settings."""
        try:
            inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
            self._log_message(f"Mode: {'INFERENCE-ONLY' if inference_only else 'FULL'} (RAG {'disabled' if inference_only else 'enabled'})")
            self._log_message("-" * 50)
        except Exception as e:
            self._log_message(f"Error logging server mode: {str(e)}", level='error')
    
    def _log_security_configurations(self) -> None:
        """Log security-related configurations."""
        try:
            # Authentication Configuration
            auth_config = self.config.get('auth', {})
            auth_enabled = _is_true_value(auth_config.get('enabled', False))
            self._log_message(f"🔐 Authentication Service: {'ENABLED' if auth_enabled else 'DISABLED'}")
            
            if auth_enabled:
                self._log_message(f"Session duration: {auth_config.get('session_duration_hours', 12)} hours", indent=2)
                self._log_message(f"Default admin username: {auth_config.get('default_admin_username', 'admin')}", indent=2)
                self._log_message(f"Password hashing iterations: {auth_config.get('pbkdf2_iterations', 600000)}", indent=2)
                self._log_message(f"Credential storage: {auth_config.get('credential_storage', 'keyring')}", indent=2)
            else:
                self._log_message("⚠️  WARNING: Authentication is DISABLED!", level='warning', indent=2)
            
            # LLM Guard Configuration
            llm_guard_config = self.config.get('llm_guard', {})
            llm_guard_enabled = bool(llm_guard_config) and llm_guard_config.get('enabled', True)
            self._log_message(f"LLM Guard: {'enabled' if llm_guard_enabled else 'disabled'}")
            
            if llm_guard_enabled:
                service_config = llm_guard_config.get('service', {})
                security_config = llm_guard_config.get('security', {})
                self._log_message(f"LLM Guard service URL: {service_config.get('base_url', 'http://localhost:8000')}", indent=2)
                self._log_message(f"Default risk threshold: {security_config.get('risk_threshold', 0.6)}", indent=2)
                self._log_message("Available input scanners: 7 (default)", indent=2)
                self._log_message("Available output scanners: 4 (default)", indent=2)
            
            # Safety Configuration
            safety_config = self.config.get('safety', {})
            safety_enabled = _is_true_value(safety_config.get('enabled', False))
            self._log_message(f"Safety: {'enabled' if safety_enabled else 'disabled'}")
            
            if safety_enabled:
                self._log_message(f"Safety mode: {safety_config.get('mode', 'strict')}", indent=2)
                safety_moderator = safety_config.get('moderator')
                if safety_moderator:
                    self._log_message(f"Safety moderator: {safety_moderator}", indent=2)
                    moderators_config = self.config.get('moderators', {}).get(safety_moderator, {})
                    if moderators_config:
                        self._log_message(f"Moderation model: {moderators_config.get('model', 'unknown')}", indent=2)
                        if 'temperature' in moderators_config:
                            self._log_message(f"Moderation temperature: {moderators_config['temperature']}", indent=2)
                        if 'max_tokens' in moderators_config:
                            self._log_message(f"Moderation max tokens: {moderators_config['max_tokens']}", indent=2)
                        if 'batch_size' in moderators_config:
                            self._log_message(f"Moderation batch size: {moderators_config['batch_size']}", indent=2)
                else:
                    self._log_message("Safety moderator: not specified (will use inference provider)", indent=2)
        except Exception as e:
            self._log_message(f"Error logging security configurations: {str(e)}", level='error')
    
    def _log_provider_configurations(self) -> None:
        """Log provider configuration details."""
        try:
            # Get selected providers
            inference_provider = self.config.get('general', {}).get('inference_provider', 'ollama')
            self._log_message(f"Inference provider: {inference_provider}")
            
            # Only log embedding info if not in inference_only mode
            inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
            if not inference_only:
                # Get embedding configuration
                embedding_config = self.config.get('embedding', {})
                embedding_enabled = _is_true_value(embedding_config.get('enabled', True))
                embedding_provider = embedding_config.get('provider', 'ollama')
                
                self._log_message(f"Embedding: {'enabled' if embedding_enabled else 'disabled'}")
                
                if embedding_enabled:
                    self._log_message(f"Embedding provider: {embedding_provider}")
                    
                    if embedding_provider in self.config.get('embeddings', {}):
                        embed_model = self.config['embeddings'][embedding_provider].get('model', 'unknown')
                        self._log_message(f"Embedding model: {embed_model}")
        except Exception as e:
            self._log_message(f"Error logging provider configurations: {str(e)}", level='error')
    
    def _log_service_configurations(self) -> None:
        """Log service configuration details."""
        try:
            # Log chat history information if in inference_only mode
            inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
            if inference_only:
                self._log_chat_history_configuration()
        except Exception as e:
            self._log_message(f"Error logging service configurations: {str(e)}", level='error')
    
    def _log_chat_history_configuration(self) -> None:
        """Log chat history service configuration."""
        try:
            chat_history_config = self.config.get('chat_history', {})
            chat_history_enabled = _is_true_value(chat_history_config.get('enabled', True))
            self._log_message(f"Chat History: {'enabled' if chat_history_enabled else 'disabled'}")
            
            if chat_history_enabled:
                self._log_message(f"Default message limit: {chat_history_config.get('default_limit', 50)}", indent=2)
                self._log_message(f"Store metadata: {chat_history_config.get('store_metadata', True)}", indent=2)
                self._log_message(f"Retention days: {chat_history_config.get('retention_days', 90)}", indent=2)
                self._log_message(f"Session auto-generate: {chat_history_config.get('session', {}).get('auto_generate', True)}", indent=2)
                self._log_message("Max conversation messages: dynamically calculated based on inference provider context window", indent=2)
        except Exception as e:
            self._log_message(f"Error logging chat history configuration: {str(e)}", level='error')
    
    def _log_api_configurations(self) -> None:
        """Log API and security configuration details."""
        try:
            # Get session ID configuration
            session_config = self.config.get('general', {}).get('session_id', {})
            session_enabled = _is_true_value(session_config.get('required', False))
            session_header = session_config.get('header_name', 'X-Session-ID')
            self._log_message(f"Session ID: {'enabled' if session_enabled else 'disabled'} (header: {session_header})")
            
            # Get API key configuration
            api_key_config = self.config.get('api_keys', {})
            api_key_enabled = _is_true_value(api_key_config.get('enabled', True))
            api_key_header = api_key_config.get('header_name', 'X-API-Key')
            self._log_message(f"API Key: {'enabled' if api_key_enabled else 'disabled'} (header: {api_key_header})")
        except Exception as e:
            self._log_message(f"Error logging API configurations: {str(e)}", level='error')
    
    def _log_model_information(self) -> None:
        """Log model configuration details."""
        try:
            # Log model information based on the selected inference provider
            inference_provider = self.config.get('general', {}).get('inference_provider', 'ollama')
            if inference_provider in self.config.get('inference', {}):
                model_name = self.config['inference'][inference_provider].get('model', 'unknown')
                self._log_message(f"Server running with {model_name} model")
        except Exception as e:
            self._log_message(f"Error logging model information: {str(e)}", level='error')
    
    def _log_runtime_information(self, app: FastAPI) -> None:
        """Log runtime-specific information when available."""
        try:
            # Log retriever information only if not in inference_only mode and retriever exists
            inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
            if not inference_only and hasattr(app.state, 'retriever') and app.state.retriever is not None:
                try:
                    self._log_message(f"Confidence threshold: {app.state.retriever.confidence_threshold}")
                except AttributeError:
                    # Skip logging if retriever is not fully initialized
                    pass
            
            # Log service statuses
            chat_history_loaded = hasattr(app.state, 'chat_history_service') and app.state.chat_history_service is not None
            self._log_message(f"Chat History Service: {'loaded' if chat_history_loaded else 'not loaded'}")
            
            auth_service_loaded = hasattr(app.state, 'auth_service') and app.state.auth_service is not None
            self._log_message(f"🔐 Authentication Service: {'loaded' if auth_service_loaded else 'not loaded'}")
            
            moderator_loaded = hasattr(app.state, 'moderator_service') and app.state.moderator_service is not None
            self._log_message(f"Moderator Service: {'loaded' if moderator_loaded else 'not loaded'}")
            
        except Exception as e:
            self._log_message(f"Error logging runtime information: {str(e)}", level='error')
    
    def _log_endpoint_information(self) -> None:
        """Log API endpoint information."""
        try:
            self._log_message("API Endpoints:")
            self._log_message("  - MCP Completion Endpoint: POST /v1/chat", indent=2)
            self._log_message("  - Health check: GET /health", indent=2)
        except Exception as e:
            self._log_message(f"Error logging endpoint information: {str(e)}", level='error')
    
    def _log_system_settings(self) -> None:
        """Log system-level settings."""
        try:
            verbose_enabled = _is_true_value(self.config.get('general', {}).get('verbose', False))
            self._log_message(f"Verbose mode: {verbose_enabled}")
        except Exception as e:
            self._log_message(f"Error logging system settings: {str(e)}", level='error')
    
    def generate_configuration_report(self) -> Dict[str, Any]:
        """
        Generate a structured configuration report for programmatic use.
        
        Returns:
            A dictionary containing structured configuration information
        """
        try:
            inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
            
            report = {
                'server_mode': {
                    'inference_only': inference_only,
                    'rag_enabled': not inference_only
                },
                'providers': {
                    'inference': self.config.get('general', {}).get('inference_provider', 'ollama')
                },
                'services': {
                    'auth': {
                        'enabled': _is_true_value(self.config.get('auth', {}).get('enabled', False)),
                        'session_duration_hours': self.config.get('auth', {}).get('session_duration_hours', 12),
                        'default_admin_username': self.config.get('auth', {}).get('default_admin_username', 'admin'),
                        'pbkdf2_iterations': self.config.get('auth', {}).get('pbkdf2_iterations', 600000),
                        'credential_storage': self.config.get('auth', {}).get('credential_storage', 'keyring')
                    },
                    'llm_guard': {
                        'enabled': self._get_llm_guard_enabled_status(),
                        'base_url': self._get_llm_guard_base_url(),
                        'default_risk_threshold': self._get_llm_guard_risk_threshold(),
                        'fallback_behavior': self._get_llm_guard_fallback_behavior()
                    }
                },
                'api': {
                    'session_id_required': _is_true_value(self.config.get('general', {}).get('session_id', {}).get('required', False)),
                    'api_key_enabled': _is_true_value(self.config.get('api_keys', {}).get('enabled', True))
                },
                'system': {
                    'verbose': _is_true_value(self.config.get('general', {}).get('verbose', False))
                }
            }
            
            # Add embedding info if not in inference_only mode
            if not inference_only:
                embedding_config = self.config.get('embedding', {})
                report['providers']['embedding'] = {
                    'enabled': _is_true_value(embedding_config.get('enabled', True)),
                    'provider': embedding_config.get('provider', 'ollama')
                }
            
            # Add chat history info if in inference_only mode
            if inference_only:
                chat_history_config = self.config.get('chat_history', {})
                report['services']['chat_history'] = {
                    'enabled': _is_true_value(chat_history_config.get('enabled', True)),
                    'default_limit': chat_history_config.get('default_limit', 50),
                    'retention_days': chat_history_config.get('retention_days', 90)
                }
            
            return report
        except Exception as e:
            self._log_message(f"Error generating configuration report: {str(e)}", level='error')
            return {
                'error': f"Failed to generate configuration report: {str(e)}",
                'server_mode': {'inference_only': False, 'rag_enabled': True}
            }
    
    def _get_llm_guard_enabled_status(self) -> bool:
        """Get LLM Guard enabled status from either configuration structure"""
        llm_guard_config = self.config.get('llm_guard', {})
        if llm_guard_config:
            if 'enabled' in llm_guard_config:
                return llm_guard_config.get('enabled', False)
            else:
                return True
        return False
    
    def _get_llm_guard_base_url(self) -> str:
        """Get LLM Guard base URL from either configuration structure"""
        llm_guard_config = self.config.get('llm_guard', {})
        return llm_guard_config.get('service', {}).get('base_url', 'http://localhost:8000')
    
    def _get_llm_guard_risk_threshold(self) -> float:
        """Get LLM Guard risk threshold from either configuration structure"""
        llm_guard_config = self.config.get('llm_guard', {})
        return llm_guard_config.get('security', {}).get('risk_threshold', 0.6)
    
    def _get_llm_guard_fallback_behavior(self) -> str:
        """Get LLM Guard fallback behavior from either configuration structure"""
        llm_guard_config = self.config.get('llm_guard', {})
        return llm_guard_config.get('fallback', {}).get('on_error', 'allow')