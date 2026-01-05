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
from utils import is_true_value



logger = logging.getLogger(__name__)
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
            logger.warning(formatted_message)
        elif level == 'error':
            logger.error(formatted_message)
        else:
            logger.info(formatted_message)
    
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
            
            # Performance Settings
            self._log_performance_settings(app)
            
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
            self._log_message("Mode: FULL (RAG enabled)")
            self._log_message("-" * 50)
        except Exception as e:
            self._log_message(f"Error logging server mode: {str(e)}", level='error')
    
    def _log_security_configurations(self) -> None:
        """Log security-related configurations."""
        try:
            # Authentication Configuration
            auth_config = self.config.get('auth', {})
            # Authentication is always enabled - no option to disable
            self._log_message(f"🔐 Authentication Service: ENABLED (always required)")

            self._log_message(f"Session duration: {auth_config.get('session_duration_hours', 12)} hours", indent=2)
            self._log_message(f"Default admin username: {auth_config.get('default_admin_username', 'admin')}", indent=2)
            self._log_message(f"Password hashing iterations: {auth_config.get('pbkdf2_iterations', 600000)}", indent=2)
            self._log_message(f"Credential storage: {auth_config.get('credential_storage', 'keyring')}", indent=2)

            # CORS Configuration
            security_config = self.config.get('security', {})
            cors_config = security_config.get('cors', {})
            if cors_config:
                allowed_origins = cors_config.get('allowed_origins', ['*'])
                has_wildcard = '*' in allowed_origins
                allow_credentials = cors_config.get('allow_credentials', False)

                if has_wildcard:
                    # self._log_message("🌐 CORS: DEVELOPMENT MODE (wildcard origins)", level='warning')
                    self._log_message("Allowed origins: * (all origins)", indent=2)
                    self._log_message("Allow credentials: DISABLED (required for wildcard)", indent=2)
                else:
                    # self._log_message("🌐 CORS: PRODUCTION MODE (restricted origins)")
                    origin_count = len(allowed_origins)
                    self._log_message(f"Allowed origins: {origin_count} specific origin(s)", indent=2)
                    for origin in allowed_origins[:5]:  # Show first 5
                        self._log_message(f"  - {origin}", indent=4)
                    if origin_count > 5:
                        self._log_message(f"  ... and {origin_count - 5} more", indent=4)
                    self._log_message(f"Allow credentials: {'ENABLED' if allow_credentials else 'DISABLED'}", indent=2)

                self._log_message(f"Allowed methods: {', '.join(cors_config.get('allowed_methods', []))}", indent=2)
                self._log_message(f"Max age: {cors_config.get('max_age', 600)}s", indent=2)

            # Security Headers Configuration
            headers_config = security_config.get('headers', {})
            if headers_config.get('enabled', True):
                self._log_message("🛡️ Security Headers: ENABLED")
                if headers_config.get('content_security_policy'):
                    self._log_message("Content-Security-Policy: configured", indent=2)
                if headers_config.get('strict_transport_security'):
                    self._log_message("Strict-Transport-Security: configured", indent=2)
                if headers_config.get('x_content_type_options'):
                    self._log_message(f"X-Content-Type-Options: {headers_config.get('x_content_type_options')}", indent=2)
                if headers_config.get('x_frame_options'):
                    self._log_message(f"X-Frame-Options: {headers_config.get('x_frame_options')}", indent=2)
                if headers_config.get('x_xss_protection'):
                    self._log_message(f"X-XSS-Protection: {headers_config.get('x_xss_protection')}", indent=2)
            else:
                self._log_message("🛡️ Security Headers: DISABLED", level='warning')
                self._log_message("WARNING: Security headers are disabled - not recommended for production", indent=2, level='warning')

            # Request Limits Configuration
            request_limits = security_config.get('request_limits', {})
            if request_limits:
                max_body_size = request_limits.get('max_body_size_mb', 10)
                self._log_message(f"📦 Request Limits: max body size {max_body_size}MB")

            # Safety Configuration
            safety_config = self.config.get('safety', {})
            safety_enabled = is_true_value(safety_config.get('enabled', False))
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

            # Get embedding configuration
            embedding_config = self.config.get('embedding', {})
            embedding_enabled = is_true_value(embedding_config.get('enabled', True))
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
            # Log backend configuration
            self._log_backend_configuration()

            # Log chat history configuration
            self._log_chat_history_configuration()

            # Log autocomplete configuration
            self._log_autocomplete_configuration()

            # Log fault tolerance configuration
            self._log_fault_tolerance_configuration()
        except Exception as e:
            self._log_message(f"Error logging service configurations: {str(e)}", level='error')
    
    def _log_chat_history_configuration(self) -> None:
        """Log chat history service configuration."""
        try:
            chat_history_config = self.config.get('chat_history', {})
            chat_history_enabled = is_true_value(chat_history_config.get('enabled', True))
            self._log_message(f"Chat History: {'enabled' if chat_history_enabled else 'disabled'}")

            if chat_history_enabled:
                self._log_message(f"Default message limit: {chat_history_config.get('default_limit', 50)}", indent=2)
                self._log_message(f"Store metadata: {chat_history_config.get('store_metadata', True)}", indent=2)
                self._log_message(f"Retention days: {chat_history_config.get('retention_days', 90)}", indent=2)
                self._log_message(f"Session auto-generate: {chat_history_config.get('session', {}).get('auto_generate', True)}", indent=2)
                self._log_message("Max conversation messages: dynamically calculated based on inference provider context window", indent=2)
        except Exception as e:
            self._log_message(f"Error logging chat history configuration: {str(e)}", level='error')

    def _log_autocomplete_configuration(self) -> None:
        """Log autocomplete service configuration."""
        try:
            autocomplete_config = self.config.get('autocomplete', {})
            autocomplete_enabled = is_true_value(autocomplete_config.get('enabled', True))
            self._log_message(f"🔍 Autocomplete: {'enabled' if autocomplete_enabled else 'disabled'}")

            if autocomplete_enabled:
                self._log_message(f"Min query length: {autocomplete_config.get('min_query_length', 3)} chars", indent=2)
                self._log_message(f"Max suggestions: {autocomplete_config.get('max_suggestions', 5)}", indent=2)

                # Cache configuration
                cache_config = autocomplete_config.get('cache', {})
                use_redis = is_true_value(cache_config.get('use_redis', True))
                cache_ttl = cache_config.get('ttl_seconds', 1800)

                # Check if Redis is actually available when Redis caching is configured
                redis_config = self.config.get('internal_services', {}).get('redis', {}) or {}
                redis_enabled = is_true_value(redis_config.get('enabled', False))

                if use_redis and not redis_enabled:
                    self._log_message(f"Cache: Redis configured but Redis is DISABLED - falling back to Memory (TTL: {cache_ttl}s)", indent=2, level='warning')
                    self._log_message("WARNING: Autocomplete requires Redis for distributed caching", indent=4, level='warning')
                else:
                    self._log_message(f"Cache: {'Redis' if use_redis else 'Memory'} (TTL: {cache_ttl}s)", indent=2)

                # Fuzzy matching configuration
                fuzzy_config = autocomplete_config.get('fuzzy_matching', {})
                fuzzy_enabled = is_true_value(fuzzy_config.get('enabled', False))
                if fuzzy_enabled:
                    algorithm = fuzzy_config.get('algorithm', 'substring')
                    threshold = fuzzy_config.get('threshold', 0.75)
                    self._log_message(f"Fuzzy matching: {algorithm} (threshold: {threshold})", indent=2)
                else:
                    self._log_message("Fuzzy matching: disabled (substring only)", indent=2)
        except Exception as e:
            self._log_message(f"Error logging autocomplete configuration: {str(e)}", level='error')
    
    def _log_backend_configuration(self) -> None:
        """Log backend database configuration."""
        try:
            backend_config = self.config.get('internal_services', {}).get('backend', {})
            backend_type = backend_config.get('type', 'unknown')
            self._log_message(f"Backend: {backend_type.upper()}")
            
            if backend_type == 'sqlite':
                sqlite_config = backend_config.get('sqlite', {})
                database_path = sqlite_config.get('database_path', 'orbit.db')
                self._log_message(f"Database path: {database_path}", indent=2)
            elif backend_type == 'mongodb':
                mongodb_config = self.config.get('internal_services', {}).get('mongodb', {})
                host = mongodb_config.get('host', 'localhost')
                port = mongodb_config.get('port', 27017)
                database = mongodb_config.get('database', 'orbit')
                self._log_message(f"MongoDB host: {host}:{port}", indent=2)
                self._log_message(f"MongoDB database: {database}", indent=2)
        except Exception as e:
            self._log_message(f"Error logging backend configuration: {str(e)}", level='error')
    
    def _log_fault_tolerance_configuration(self) -> None:
        """Log fault tolerance service configuration."""
        try:
            fault_tolerance_config = self.config.get('fault_tolerance', {})
            self._log_message("Fault Tolerance: enabled")
            
            circuit_breaker_config = fault_tolerance_config.get('circuit_breaker', {})
            isolation_config = fault_tolerance_config.get('isolation', {})
            execution_config = fault_tolerance_config.get('execution', {})
            health_monitoring_config = fault_tolerance_config.get('health_monitoring', {})
            
            self._log_message(f"Circuit Breaker - Failure threshold: {circuit_breaker_config.get('failure_threshold', 5)}", indent=2)
            self._log_message(f"Circuit Breaker - Recovery timeout: {circuit_breaker_config.get('recovery_timeout', 30)}s", indent=2)
            self._log_message(f"Circuit Breaker - Operation timeout: {circuit_breaker_config.get('timeout', 30)}s", indent=2)
            self._log_message(f"Execution strategy: {execution_config.get('strategy', 'all')}", indent=2)
            self._log_message(f"Total execution timeout: {execution_config.get('timeout', 35)}s", indent=2)
            self._log_message(f"Max concurrent adapters: {execution_config.get('max_concurrent_adapters', 10)}", indent=2)
            self._log_message(f"Isolation strategy: {isolation_config.get('strategy', 'thread')}", indent=2)
            self._log_message(f"Health monitoring: {'enabled' if health_monitoring_config.get('enabled', True) else 'disabled'}", indent=2)
            
            # Log adapter-specific configurations
            adapters_config = self.config.get('adapters', [])
            if adapters_config:
                # Count enabled and disabled adapters
                enabled_adapters = [adapter for adapter in adapters_config if adapter.get('enabled', True)]
                disabled_adapters = [adapter for adapter in adapters_config if not adapter.get('enabled', True)]
                
                self._log_message(f"Adapters: {len(enabled_adapters)} enabled, {len(disabled_adapters)} disabled", indent=2)
                
                # List enabled adapters
                if enabled_adapters:
                    enabled_names = [adapter['name'] for adapter in enabled_adapters]
                    self._log_message(f"Enabled adapters: {', '.join(enabled_names)}", indent=4)
                
                # List disabled adapters
                if disabled_adapters:
                    disabled_names = [adapter['name'] for adapter in disabled_adapters]
                    self._log_message(f"Disabled adapters: {', '.join(disabled_names)}", indent=4)
                
                # Log adapters with custom fault tolerance
                fault_tolerant_adapters = [
                    adapter['name'] for adapter in enabled_adapters 
                    if adapter.get('fault_tolerance', {}).get('operation_timeout')
                ]
                if fault_tolerant_adapters:
                    self._log_message(f"Adapters with custom fault tolerance: {', '.join(fault_tolerant_adapters)}", indent=4)
        except Exception as e:
            self._log_message(f"Error logging fault tolerance configuration: {str(e)}", level='error')
    
    def _log_api_configurations(self) -> None:
        """Log API and security configuration details."""
        try:
            # Get session ID configuration
            session_config = self.config.get('general', {}).get('session_id', {})
            session_enabled = is_true_value(session_config.get('required', False))
            session_header = session_config.get('header_name', 'X-Session-ID')
            self._log_message(f"Session ID: {'enabled' if session_enabled else 'disabled'} (header: {session_header})")
            
            # Get API key configuration
            api_key_config = self.config.get('api_keys', {})
            api_key_enabled = is_true_value(api_key_config.get('enabled', True))
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
            # Log retriever information if retriever exists
            if hasattr(app.state, 'retriever') and app.state.retriever is not None:
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
    
    def _log_performance_settings(self, app: Optional[FastAPI] = None) -> None:
        """Log performance and threading configuration."""
        try:
            perf_config = self.config.get('performance', {})
            
            if perf_config:
                self._log_message("⚡ Performance Configuration:")
                
                # Uvicorn workers
                workers = perf_config.get('workers', 1)
                self._log_message(f"Uvicorn workers: {workers}", indent=2)
                
                # Keep-alive timeout
                keep_alive = perf_config.get('keep_alive_timeout', 30)
                self._log_message(f"Keep-alive timeout: {keep_alive}s", indent=2)
                
                # Thread pools
                thread_pools = perf_config.get('thread_pools', {})
                if thread_pools:
                    self._log_message("Thread Pools:", indent=2)
                    
                    # Calculate total workers
                    total_workers = 0
                    for pool_name, worker_count in thread_pools.items():
                        pool_display_name = pool_name.replace('_workers', '').upper()
                        self._log_message(f"{pool_display_name}: {worker_count} workers", indent=4)
                        total_workers += worker_count
                    
                    self._log_message(f"Total thread pool capacity: {total_workers} workers", indent=4)
                    
                    # Show current utilization if thread pool manager is available
                    if app and hasattr(app.state, 'thread_pool_manager'):
                        try:
                            stats = app.state.thread_pool_manager.get_pool_stats()
                            active_total = sum(pool['active_threads'] for pool in stats.values() if isinstance(pool['active_threads'], int))
                            utilization = (active_total / total_workers * 100) if total_workers > 0 else 0
                            self._log_message(f"Current utilization: {active_total}/{total_workers} ({utilization:.1f}%)", indent=4)
                        except Exception:
                            # Don't fail if stats aren't available
                            pass
                else:
                    self._log_message("Thread pools: using defaults", indent=2)
            else:
                self._log_message("⚡ Performance: using default configuration")
                
        except Exception as e:
            self._log_message(f"Error logging performance settings: {str(e)}", level='error')
    
    def _log_system_settings(self) -> None:
        """Log system-level settings."""
        try:
            logging_level = logging.getLevelName(self.logger.getEffectiveLevel())
            
            # Check new language_detection configuration structure
            lang_detect_config = self.config.get('language_detection', {})
            language_detection_enabled = is_true_value(lang_detect_config.get('enabled', False))
            
            self._log_message(f"Logging level: {logging_level}")
            self._log_message(f"🌍 Language detection: {'enabled' if language_detection_enabled else 'disabled'}")
            
            if language_detection_enabled:
                self._log_message("Automatic language matching for multilingual responses", indent=2)
                # Log language detection configuration details
                backends = lang_detect_config.get('backends', ['langdetect'])
                self._log_message(f"Backends: {', '.join(backends)}", indent=2)
                self._log_message(f"Min confidence: {lang_detect_config.get('min_confidence', 0.7)}", indent=2)
                self._log_message(f"Fallback language: {lang_detect_config.get('fallback_language', 'en')}", indent=2)
        except Exception as e:
            self._log_message(f"Error logging system settings: {str(e)}", level='error')
    
    def generate_configuration_report(self) -> Dict[str, Any]:
        """
        Generate a structured configuration report for programmatic use.
        
        Returns:
            A dictionary containing structured configuration information
        """
        try:
            report = {
                'server_mode': {
                    'rag_enabled': True
                },
                'providers': {
                    'inference': self.config.get('general', {}).get('inference_provider', 'ollama')
                },
                'services': {
                    'auth': {
                        'enabled': True,  # Authentication is always enabled - no option to disable
                        'session_duration_hours': self.config.get('auth', {}).get('session_duration_hours', 12),
                        'default_admin_username': self.config.get('auth', {}).get('default_admin_username', 'admin'),
                        'pbkdf2_iterations': self.config.get('auth', {}).get('pbkdf2_iterations', 600000),
                        'credential_storage': self.config.get('auth', {}).get('credential_storage', 'keyring')
                    }
                },
                'api': {
                    'session_id_required': is_true_value(self.config.get('general', {}).get('session_id', {}).get('required', False)),
                    'api_key_enabled': is_true_value(self.config.get('api_keys', {}).get('enabled', True))
                },
                'system': {
                    'logging_level': logging.getLevelName(self.logger.getEffectiveLevel()),
                    'language_detection': is_true_value(self.config.get('language_detection', {}).get('enabled', False))
                }
            }

            # Add embedding info
            embedding_config = self.config.get('embedding', {})
            report['providers']['embedding'] = {
                'enabled': is_true_value(embedding_config.get('enabled', True)),
                'provider': embedding_config.get('provider', 'ollama')
            }

            # Add chat history info
            chat_history_config = self.config.get('chat_history', {})
            report['services']['chat_history'] = {
                'enabled': is_true_value(chat_history_config.get('enabled', True)),
                'default_limit': chat_history_config.get('default_limit', 50),
                'retention_days': chat_history_config.get('retention_days', 90)
            }

            return report
        except Exception as e:
            self._log_message(f"Error generating configuration report: {str(e)}", level='error')
            return {
                'error': f"Failed to generate configuration report: {str(e)}",
                'server_mode': {'rag_enabled': True}
            }
    
