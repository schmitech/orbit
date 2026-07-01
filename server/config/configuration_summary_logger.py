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
from typing import Any, Dict, Optional

from fastapi import FastAPI
from utils import is_true_value


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

    def log_configuration_summary(self, app: Optional[FastAPI] = None) -> None:
        """
        Log a comprehensive summary of the server configuration.

        Args:
            app: Optional FastAPI application instance for accessing runtime state
        """
        self.logger.info("=" * 50)
        self.logger.info("Server Configuration Summary")
        self.logger.info("=" * 50)

        self._log_server_mode()
        self._log_provider_configurations()
        self._log_security_configurations()
        self._log_service_configurations()
        self._log_api_configurations()
        self._log_model_information()

        if app:
            self._log_runtime_information(app)

        self._log_endpoint_information()
        self._log_performance_settings(app)
        self._log_system_settings()

        self.logger.info("=" * 50)
        self.logger.info("✅ Server is ready and accepting requests")
        self.logger.info("=" * 50)

    def _log_server_mode(self) -> None:
        """Log server mode and operational settings."""
        self.logger.info("Mode: FULL (RAG enabled)")
        self.logger.info("-" * 50)

    def _log_security_configurations(self) -> None:
        """Log security-related configurations."""
        auth_config = self.config.get('auth', {})
        self.logger.info("🔐 Authentication Service: ENABLED (always required)")
        self.logger.info(f"  Session duration: {auth_config.get('session_duration_hours', 12)} hours")
        self.logger.info(f"  Default admin username: {auth_config.get('default_admin_username', 'admin')}")
        self.logger.info(f"  Password hashing iterations: {auth_config.get('pbkdf2_iterations', 600000)}")
        self.logger.info(f"  Credential storage: {auth_config.get('credential_storage', 'keyring')}")

        security_config = self.config.get('security', {})
        cors_config = security_config.get('cors', {})
        if cors_config:
            allowed_origins = cors_config.get('allowed_origins', ['*'])
            has_wildcard = '*' in allowed_origins
            allow_credentials = cors_config.get('allow_credentials', False)

            if has_wildcard:
                self.logger.info("  Allowed origins: * (all origins)")
                self.logger.info("  Allow credentials: DISABLED (required for wildcard)")
            else:
                origin_count = len(allowed_origins)
                self.logger.info(f"  Allowed origins: {origin_count} specific origin(s)")
                for origin in allowed_origins[:5]:
                    self.logger.info(f"      - {origin}")
                if origin_count > 5:
                    self.logger.info(f"      ... and {origin_count - 5} more")
                self.logger.info(f"  Allow credentials: {'ENABLED' if allow_credentials else 'DISABLED'}")

            self.logger.info(f"  Allowed methods: {', '.join(cors_config.get('allowed_methods', []))}")
            self.logger.info(f"  Max age: {cors_config.get('max_age', 600)}s")

        headers_config = security_config.get('headers', {})
        if headers_config.get('enabled', True):
            self.logger.info("🛡️ Security Headers: ENABLED")
            if headers_config.get('content_security_policy'):
                self.logger.info("  Content-Security-Policy: configured")
            if headers_config.get('strict_transport_security'):
                self.logger.info("  Strict-Transport-Security: configured")
            if headers_config.get('x_content_type_options'):
                self.logger.info(f"  X-Content-Type-Options: {headers_config.get('x_content_type_options')}")
            if headers_config.get('x_frame_options'):
                self.logger.info(f"  X-Frame-Options: {headers_config.get('x_frame_options')}")
            if headers_config.get('x_xss_protection'):
                self.logger.info(f"  X-XSS-Protection: {headers_config.get('x_xss_protection')}")
        else:
            self.logger.warning("🛡️ Security Headers: DISABLED")
            self.logger.warning("  WARNING: Security headers are disabled - not recommended for production")

        request_limits = security_config.get('request_limits', {})
        if request_limits:
            max_body_size = request_limits.get('max_body_size_mb', 10)
            self.logger.info(f"📦 Request Limits: max body size {max_body_size}MB")

        safety_config = self.config.get('safety', {})
        safety_enabled = is_true_value(safety_config.get('enabled', False))
        self.logger.info(f"Safety: {'enabled' if safety_enabled else 'disabled'}")

        if safety_enabled:
            self.logger.info(f"  Safety mode: {safety_config.get('mode', 'strict')}")
            safety_moderator = safety_config.get('moderator')
            if safety_moderator:
                self.logger.info(f"  Safety moderator: {safety_moderator}")
                moderators_config = self.config.get('moderators', {}).get(safety_moderator, {})
                if moderators_config:
                    self.logger.info(f"  Moderation model: {moderators_config.get('model', 'unknown')}")
                    if 'temperature' in moderators_config:
                        self.logger.info(f"  Moderation temperature: {moderators_config['temperature']}")
                    if 'max_tokens' in moderators_config:
                        self.logger.info(f"  Moderation max tokens: {moderators_config['max_tokens']}")
                    if 'batch_size' in moderators_config:
                        self.logger.info(f"  Moderation batch size: {moderators_config['batch_size']}")
            else:
                self.logger.info("  Safety moderator: not specified (will use inference provider)")

    def _log_provider_configurations(self) -> None:
        """Log provider configuration details."""
        inference_provider = self.config.get('general', {}).get('inference_provider', 'ollama')
        self.logger.info(f"Inference provider: {inference_provider}")

        embedding_config = self.config.get('embedding', {})
        embedding_enabled = is_true_value(embedding_config.get('enabled', True))
        embedding_provider = embedding_config.get('provider', 'ollama')
        self.logger.info(f"Embedding: {'enabled' if embedding_enabled else 'disabled'}")

        if embedding_enabled:
            self.logger.info(f"Embedding provider: {embedding_provider}")
            if embedding_provider in self.config.get('embeddings', {}):
                embed_model = self.config['embeddings'][embedding_provider].get('model', 'unknown')
                self.logger.info(f"Embedding model: {embed_model}")

    def _log_service_configurations(self) -> None:
        """Log service configuration details."""
        self._log_backend_configuration()
        self._log_chat_history_configuration()
        self._log_autocomplete_configuration()
        self._log_fault_tolerance_configuration()

    def _log_chat_history_configuration(self) -> None:
        """Log chat history service configuration."""
        chat_history_config = self.config.get('chat_history', {})
        chat_history_enabled = is_true_value(chat_history_config.get('enabled', True))
        self.logger.info(f"Chat History: {'enabled' if chat_history_enabled else 'disabled'}")

        if chat_history_enabled:
            self.logger.info(f"  Default message limit: {chat_history_config.get('default_limit', 50)}")
            self.logger.info(f"  Store metadata: {chat_history_config.get('store_metadata', True)}")
            self.logger.info(f"  Retention days: {chat_history_config.get('retention_days', 90)}")
            self.logger.info(
                f"  Session auto-generate: {chat_history_config.get('session', {}).get('auto_generate', True)}"
            )
            self.logger.info(
                "  Max conversation messages: dynamically calculated based on inference provider context window"
            )

    def _log_autocomplete_configuration(self) -> None:
        """Log autocomplete service configuration."""
        autocomplete_config = self.config.get('autocomplete', {})
        autocomplete_enabled = is_true_value(autocomplete_config.get('enabled', True))
        self.logger.info(f"🔍 Autocomplete: {'enabled' if autocomplete_enabled else 'disabled'}")

        if autocomplete_enabled:
            self.logger.info(f"  Min query length: {autocomplete_config.get('min_query_length', 3)} chars")
            self.logger.info(f"  Max suggestions: {autocomplete_config.get('max_suggestions', 5)}")

            cache_config = autocomplete_config.get('cache', {})
            use_redis = is_true_value(cache_config.get('use_redis', True))
            cache_ttl = cache_config.get('ttl_seconds', 1800)

            redis_config = self.config.get('internal_services', {}).get('redis', {}) or {}
            redis_enabled = is_true_value(redis_config.get('enabled', False))

            if use_redis and not redis_enabled:
                self.logger.warning(
                    f"  Cache: Redis configured but Redis is DISABLED - falling back to Memory (TTL: {cache_ttl}s)"
                )
                self.logger.warning("    WARNING: Autocomplete requires Redis for distributed caching")
            else:
                self.logger.info(f"  Cache: {'Redis' if use_redis else 'Memory'} (TTL: {cache_ttl}s)")

            fuzzy_config = autocomplete_config.get('fuzzy_matching', {})
            fuzzy_enabled = is_true_value(fuzzy_config.get('enabled', False))
            if fuzzy_enabled:
                algorithm = fuzzy_config.get('algorithm', 'substring')
                threshold = fuzzy_config.get('threshold', 0.75)
                self.logger.info(f"  Fuzzy matching: {algorithm} (threshold: {threshold})")
            else:
                self.logger.info("  Fuzzy matching: disabled (substring only)")

    def _log_backend_configuration(self) -> None:
        """Log backend database configuration."""
        backend_config = self.config.get('internal_services', {}).get('backend', {})
        backend_type = backend_config.get('type', 'unknown')
        self.logger.info(f"Backend: {backend_type.upper()}")

        if backend_type == 'sqlite':
            sqlite_config = backend_config.get('sqlite', {})
            database_path = sqlite_config.get('database_path', 'orbit.db')
            self.logger.info(f"  Database path: {database_path}")
        elif backend_type == 'mongodb':
            mongodb_config = self.config.get('internal_services', {}).get('mongodb', {})
            host = mongodb_config.get('host', 'localhost')
            port = mongodb_config.get('port', 27017)
            database = mongodb_config.get('database', 'orbit')
            self.logger.info(f"  MongoDB host: {host}:{port}")
            self.logger.info(f"  MongoDB database: {database}")
        elif backend_type == 'postgres':
            postgres_config = backend_config.get('postgres', {})
            host = postgres_config.get('host', 'localhost')
            port = postgres_config.get('port', 5432)
            database = postgres_config.get('database', 'orbit')
            self.logger.info(f"  PostgreSQL host: {host}:{port}")
            self.logger.info(f"  PostgreSQL database: {database}")

    def _log_fault_tolerance_configuration(self) -> None:
        """Log fault tolerance service configuration."""
        fault_tolerance_config = self.config.get('fault_tolerance', {})
        self.logger.info("Fault Tolerance: enabled")

        circuit_breaker_config = fault_tolerance_config.get('circuit_breaker', {})
        isolation_config = fault_tolerance_config.get('isolation', {})
        execution_config = fault_tolerance_config.get('execution', {})
        health_monitoring_config = fault_tolerance_config.get('health_monitoring', {})

        self.logger.info(f"  Circuit Breaker - Failure threshold: {circuit_breaker_config.get('failure_threshold', 5)}")
        self.logger.info(f"  Circuit Breaker - Recovery timeout: {circuit_breaker_config.get('recovery_timeout', 30)}s")
        self.logger.info(f"  Circuit Breaker - Operation timeout: {circuit_breaker_config.get('timeout', 30)}s")
        self.logger.info(f"  Execution strategy: {execution_config.get('strategy', 'all')}")
        self.logger.info(f"  Total execution timeout: {execution_config.get('timeout', 35)}s")
        self.logger.info(f"  Max concurrent adapters: {execution_config.get('max_concurrent_adapters', 10)}")
        self.logger.info(f"  Isolation strategy: {isolation_config.get('strategy', 'thread')}")
        self.logger.info(
            f"  Health monitoring: {'enabled' if health_monitoring_config.get('enabled', True) else 'disabled'}"
        )

        adapters_config = self.config.get('adapters', [])
        if adapters_config:
            enabled_adapters = [adapter for adapter in adapters_config if adapter.get('enabled', True)]
            disabled_adapters = [adapter for adapter in adapters_config if not adapter.get('enabled', True)]

            self.logger.info(f"  Adapters: {len(enabled_adapters)} enabled, {len(disabled_adapters)} disabled")

            if enabled_adapters:
                enabled_names = [adapter['name'] for adapter in enabled_adapters]
                self.logger.info(f"    Enabled adapters: {', '.join(enabled_names)}")

            if disabled_adapters:
                disabled_names = [adapter['name'] for adapter in disabled_adapters]
                self.logger.info(f"    Disabled adapters: {', '.join(disabled_names)}")

            fault_tolerant_adapters = [
                adapter['name']
                for adapter in enabled_adapters
                if adapter.get('fault_tolerance', {}).get('operation_timeout')
            ]
            if fault_tolerant_adapters:
                self.logger.info(f"    Adapters with custom fault tolerance: {', '.join(fault_tolerant_adapters)}")

    def _log_api_configurations(self) -> None:
        """Log API and security configuration details."""
        session_config = self.config.get('general', {}).get('session_id', {})
        session_enabled = is_true_value(session_config.get('required', False))
        session_header = session_config.get('header_name', 'X-Session-ID')
        self.logger.info(f"Session ID: {'enabled' if session_enabled else 'disabled'} (header: {session_header})")

        api_key_config = self.config.get('api_keys', {})
        api_key_enabled = is_true_value(api_key_config.get('enabled', True))
        api_key_header = api_key_config.get('header_name', 'X-API-Key')
        self.logger.info(f"API Key: {'enabled' if api_key_enabled else 'disabled'} (header: {api_key_header})")

    def _log_model_information(self) -> None:
        """Log model configuration details."""
        inference_provider = self.config.get('general', {}).get('inference_provider', 'ollama')
        if inference_provider in self.config.get('inference', {}):
            model_name = self.config['inference'][inference_provider].get('model', 'unknown')
            self.logger.info(f"Server running with {model_name} model")

    def _log_runtime_information(self, app: FastAPI) -> None:
        """Log runtime-specific information when available."""
        retriever = getattr(app.state, 'retriever', None)
        confidence_threshold = getattr(retriever, 'confidence_threshold', None)
        if confidence_threshold is not None:
            self.logger.info(f"Confidence threshold: {confidence_threshold}")

        chat_history_loaded = getattr(app.state, 'chat_history_service', None) is not None
        self.logger.info(f"Chat History Service: {'loaded' if chat_history_loaded else 'not loaded'}")

        auth_service_loaded = getattr(app.state, 'auth_service', None) is not None
        self.logger.info(f"🔐 Authentication Service: {'loaded' if auth_service_loaded else 'not loaded'}")

        moderator_loaded = getattr(app.state, 'moderator_service', None) is not None
        self.logger.info(f"Moderator Service: {'loaded' if moderator_loaded else 'not loaded'}")

    def _log_endpoint_information(self) -> None:
        """Log API endpoint information."""
        self.logger.info("API Endpoints:")
        self.logger.info("    - MCP Completion Endpoint: POST /v1/chat")
        self.logger.info("    - Health check: GET /health")

    def _log_performance_settings(self, app: Optional[FastAPI] = None) -> None:
        """Log performance and threading configuration."""
        perf_config = self.config.get('performance', {})

        if perf_config:
            self.logger.info("⚡ Performance Configuration:")

            workers = perf_config.get('workers', 1)
            self.logger.info(f"  Uvicorn workers: {workers}")

            keep_alive = perf_config.get('keep_alive_timeout', 30)
            self.logger.info(f"  Keep-alive timeout: {keep_alive}s")

            thread_pools = perf_config.get('thread_pools', {})
            if thread_pools:
                self.logger.info("  Thread Pools:")

                total_workers = 0
                for pool_name, worker_count in thread_pools.items():
                    pool_display_name = pool_name.replace('_workers', '').upper()
                    self.logger.info(f"    {pool_display_name}: {worker_count} workers")
                    total_workers += worker_count

                self.logger.info(f"    Total thread pool capacity: {total_workers} workers")

                thread_pool_manager = getattr(app.state, 'thread_pool_manager', None) if app else None
                if thread_pool_manager:
                    stats = thread_pool_manager.get_pool_stats()
                    active_total = sum(
                        pool['active_threads']
                        for pool in stats.values()
                        if isinstance(pool['active_threads'], int)
                    )
                    utilization = (active_total / total_workers * 100) if total_workers > 0 else 0
                    self.logger.info(f"    Current utilization: {active_total}/{total_workers} ({utilization:.1f}%)")
            else:
                self.logger.info("  Thread pools: using defaults")
        else:
            self.logger.info("⚡ Performance: using default configuration")

    def _log_system_settings(self) -> None:
        """Log system-level settings."""
        logging_level = logging.getLevelName(self.logger.getEffectiveLevel())

        lang_detect_config = self.config.get('language_detection', {})
        language_detection_enabled = is_true_value(lang_detect_config.get('enabled', False))

        self.logger.info(f"Logging level: {logging_level}")
        self.logger.info(f"🌍 Language detection: {'enabled' if language_detection_enabled else 'disabled'}")

        if language_detection_enabled:
            self.logger.info("  Automatic language matching for multilingual responses")
            backends = lang_detect_config.get('backends', ['langdetect'])
            self.logger.info(f"  Backends: {', '.join(backends)}")
            self.logger.info(f"  Min confidence: {lang_detect_config.get('min_confidence', 0.7)}")
            self.logger.info(f"  Fallback language: {lang_detect_config.get('fallback_language', 'en')}")

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
                        'enabled': True,
                        'session_duration_hours': self.config.get('auth', {}).get('session_duration_hours', 12),
                        'default_admin_username': self.config.get('auth', {}).get('default_admin_username', 'admin'),
                        'pbkdf2_iterations': self.config.get('auth', {}).get('pbkdf2_iterations', 600000),
                        'credential_storage': self.config.get('auth', {}).get('credential_storage', 'keyring')
                    }
                },
                'api': {
                    'session_id_required': is_true_value(
                        self.config.get('general', {}).get('session_id', {}).get('required', False)
                    ),
                    'api_key_enabled': is_true_value(self.config.get('api_keys', {}).get('enabled', True))
                },
                'system': {
                    'logging_level': logging.getLevelName(self.logger.getEffectiveLevel()),
                    'language_detection': is_true_value(self.config.get('language_detection', {}).get('enabled', False))
                }
            }

            embedding_config = self.config.get('embedding', {})
            report['providers']['embedding'] = {
                'enabled': is_true_value(embedding_config.get('enabled', True)),
                'provider': embedding_config.get('provider', 'ollama')
            }

            chat_history_config = self.config.get('chat_history', {})
            report['services']['chat_history'] = {
                'enabled': is_true_value(chat_history_config.get('enabled', True)),
                'default_limit': chat_history_config.get('default_limit', 50),
                'retention_days': chat_history_config.get('retention_days', 90)
            }

            return report
        except Exception as e:
            self.logger.error(f"Error generating configuration report: {str(e)}")
            return {
                'error': f"Failed to generate configuration report: {str(e)}",
                'server_mode': {'rag_enabled': True}
            }
