#!/usr/bin/env python3
"""
Elasticsearch Sample Data Generator

Generates realistic synthetic application log data and indexes it into Elasticsearch.
Uses Faker for data generation and optionally uses AI for realistic log messages.

USAGE:
    python utils/elasticsearch-intent-template/generate_sample_data.py [options]

REQUIRED SETUP:
    1. Set environment variables:
       export DATASOURCE_ELASTICSEARCH_USERNAME=elastic
       export DATASOURCE_ELASTICSEARCH_PASSWORD=your-password

    2. Configure Elasticsearch node in config/datasources.yaml

OPTIONAL ARGUMENTS:
    --config        Path to main config file (default: ../../config/config.yaml)
    --count         Number of log records to generate (default: 1000)
    --batch-size    Batch size for bulk indexing (default: 100)
    --index         Elasticsearch index name (default: application-logs-demo)
    --use-ai        Use AI to generate realistic log messages (default: False)
    --provider      Inference provider for AI generation (default: openai)
    --ai-usage-rate Percentage of records to generate with AI (default: 50)
    --days-back     Generate logs spanning this many days back (default: 7)
    --error-rate    Percentage of error logs (default: 30)

DATA PATTERNS:
    The generator creates realistic patterns for testing:
    - Error spikes at 1-3h, 10-14h, and 44-52h ago (for spike detection testing)
    - Errors distributed across services (payment-service & api-gateway have most)
    - Log level distribution: ERROR (30%), WARN (15%), INFO (50%), DEBUG (5%)
    - Response times: 70% of logs have response_time field
      * ERROR logs: 5-30 seconds (always slow)
      * WARN logs: 1-10 seconds (moderately slow)
      * INFO logs: Varies by endpoint performance profile
    - Endpoint performance profiles (for "slow request" queries):
      * Slow endpoints: /payments, /reports/generate, /export/data, /batch/process
      * Medium endpoints: /search, /analytics, /orders
      * Fast endpoints: /auth/login, /users, /products, /notifications

BUSINESS VALUE FEATURES:
    - Correlated request traces: ~10% of logs are multi-service traces with same request_id
      (demonstrates distributed tracing capability for debugging)
    - Realistic user pool: 20 consistent users with 4 "power users" who generate more activity
      (enables meaningful "most active users" and "user activity" queries)
    - Named loggers: 13 realistic logger names (activityLogger, securityLogger, etc.)
      (enables component-level debugging queries)
    - Scheduled jobs: 10 realistic job names (sync_job, backup_job, report_generation_job)
      (enables job monitoring and failure tracking queries)
    - Order lifecycle: Order IDs (ORD-xxx) with creation, payment, shipping, and failure events
      (enables business transaction tracking)
    - Service health patterns: Error distribution weighted by service type
      (demonstrates service health monitoring capabilities)

EXAMPLES:
    # Generate 1000 logs with default settings
    python utils/elasticsearch-intent-template/generate_sample_data.py

    # Generate 5000 logs with AI-generated messages
    python utils/elasticsearch-intent-template/generate_sample_data.py \
        --count 5000 \
        --use-ai \
        --provider ollama

    # Generate logs for 30 days with higher error rate
    python utils/elasticsearch-intent-template/generate_sample_data.py \
        --count 10000 \
        --days-back 30 \
        --error-rate 20

    # Generate logs with AI but reduce AI usage to avoid rate limits
    python utils/elasticsearch-intent-template/generate_sample_data.py \
        --count 5000 \
        --use-ai \
        --provider ollama_cloud \
        --ai-usage-rate 25
"""

print("🔄 Starting Elasticsearch sample data generator...", flush=True)

import asyncio
import json
import yaml
import random
import logging
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from faker import Faker

print("✅ Basic imports complete", flush=True)

from dotenv import load_dotenv

# Add project root to path for imports, following template_generator.py
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

print("✅ Path configured", flush=True)

# Load environment variables from project root
load_dotenv(dotenv_path=project_root / ".env")

print("✅ Environment loaded", flush=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Service names for realistic data
SERVICES = [
    "auth-service", "user-service", "order-service", "payment-service",
    "inventory-service", "notification-service", "api-gateway", "data-pipeline",
    "search-service", "recommendation-service", "analytics-service"
]

# Realistic user pool for consistent user activity tracking
# Using a fixed pool allows queries like "show user activity" to return meaningful results
USER_POOL = [
    "user-admin001", "user-john42", "user-sarah99", "user-mike123", "user-emma456",
    "user-david789", "user-lisa321", "user-chris654", "user-anna987", "user-tom111",
    "user-jane222", "user-bob333", "user-kate444", "user-alex555", "user-mary666",
    "user-james777", "user-linda888", "user-robert999", "user-patricia000", "user-michael101"
]

# Power users who generate more activity (for "most active users" queries)
POWER_USERS = ["user-admin001", "user-john42", "user-sarah99", "user-mike123"]

# Scheduled job names for job-related queries
SCHEDULED_JOBS = [
    "sync_job", "backup_job", "cleanup_job", "report_generation_job",
    "email_digest_job", "cache_warmup_job", "metrics_aggregation_job",
    "inventory_sync_job", "order_reconciliation_job", "user_export_job"
]

# Logger names for component-level queries
LOGGER_NAMES = [
    "activityLogger", "northLogger", "southLogger", "eastLogger", "westLogger",
    "scientistLogger", "engineerLogger", "managerLogger", "analystLogger",
    "securityLogger", "performanceLogger", "auditLogger", "transactionLogger"
]

# Common log message templates by level
LOG_TEMPLATES = {
    "ERROR": [
        "Failed to process request: {error}",
        "Database connection failed: {error}",
        "Authentication failed for user {user_id}",
        "API call to {service} timed out after {timeout}ms",
        "Invalid request payload: {error}",
        "Rate limit exceeded for user {user_id}",
        "Failed to send notification: {error}",
        "Cache miss followed by database error: {error}",
        "Payment processing failed: {error}",
        "Unhandled exception in {service}: {error}",
        "Order {order_id} failed: insufficient inventory",
        "Order {order_id} payment declined: {error}",
        "Scheduled job {job_name} failed: {error}",
        "Database transaction rolled back: {error}",
        "External API {service} returned error: {error}",
        "File upload failed for user {user_id}: {error}",
        "Session expired for user {user_id}",
        "Invalid credentials for user {user_id} from IP {ip}",
        "Circuit breaker opened for {service}",
        "Message queue connection lost: {error}"
    ],
    "WARN": [
        "Slow query detected: {query} took {duration}ms",
        "High memory usage: {percent}%",
        "Connection pool exhausted, waiting for connection",
        "Deprecated API endpoint called: {endpoint}",
        "Retry attempt {attempt} for {operation}",
        "Cache eviction rate high: {rate}%",
        "API response time degraded: {latency}ms",
        "Queue depth exceeding threshold: {depth}",
        "Certificate expiring in {days} days",
        "Unusual traffic pattern detected from IP {ip}",
        "Order {order_id} taking longer than expected",
        "Scheduled job {job_name} running longer than threshold",
        "User {user_id} approaching rate limit",
        "Database connection pool at {percent}% capacity",
        "Disk space usage at {percent}% on {host}",
        "Response time SLA breach for {endpoint}: {latency}ms",
        "Inventory low for product {product_id}",
        "Payment retry scheduled for order {order_id}",
        "Background job queue backlog: {depth} items",
        "External service {service} response degraded"
    ],
    "INFO": [
        "Request processed successfully in {duration}ms",
        "User {user_id} logged in from {ip}",
        "Order {order_id} created successfully",
        "Payment of ${amount} processed for order {order_id}",
        "Notification sent to user {user_id}",
        "Cache warmed for {entity}",
        "Health check passed",
        "Configuration reloaded successfully",
        "Scheduled job {job_name} completed",
        "API endpoint {endpoint} called by user {user_id}",
        "Order {order_id} shipped to customer",
        "Order {order_id} status changed to {status}",
        "User {user_id} updated profile",
        "User {user_id} changed password",
        "Inventory updated for product {product_id}: {count} units",
        "Report generated for user {user_id}: {report_type}",
        "Email sent to user {user_id}: {email_type}",
        "Scheduled job {job_name} started",
        "Database backup completed successfully",
        "Service {service} health check: all systems operational",
        "User {user_id} logged out",
        "New user registered: {user_id}",
        "Order {order_id} refund processed: ${amount}",
        "Webhook delivered successfully to {endpoint}",
        "Cache invalidated for {entity}"
    ],
    "DEBUG": [
        "Entering function: {function}",
        "Query parameters: {params}",
        "Cache hit for key: {key}",
        "Validating request payload",
        "Retrieved {count} records from database",
        "Serializing response data",
        "Applying rate limit check",
        "Session created for user {user_id}",
        "Parsing request headers",
        "Building SQL query: {query}",
        "Request body: {params}",
        "Response headers set: Content-Type=application/json",
        "Database query executed in {duration}ms",
        "Cache key generated: {key}",
        "JWT token validated for user {user_id}",
        "Rate limit check passed for user {user_id}",
        "Request correlation ID: {request_id}",
        "Loading configuration from {config_file}",
        "Middleware chain executed in {duration}ms",
        "Connection acquired from pool in {duration}ms"
    ]
}

# Exception types for error logs
EXCEPTION_TYPES = [
    "ConnectionError", "TimeoutError", "ValidationError", "AuthenticationError",
    "DatabaseError", "APIError", "RateLimitError", "PaymentError",
    "NullPointerException", "IndexOutOfBoundsException", "ValueError",
    "KeyError", "RuntimeError", "IOError"
]

# HTTP status codes
STATUS_CODES = {
    "ERROR": [400, 401, 403, 404, 500, 502, 503, 504],
    "WARN": [429, 408],
    "INFO": [200, 201, 204],
    "DEBUG": [200]
}

# API endpoints with performance characteristics
# Format: (endpoint, typical_response_time_category)
# Categories: "slow" (usually >2000ms), "medium" (500-2000ms), "fast" (<500ms)
API_ENDPOINTS = [
    "/api/v1/users", "/api/v1/orders", "/api/v1/payments", "/api/v1/products",
    "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/search",
    "/api/v1/notifications", "/api/v1/analytics", "/api/v1/inventory",
    "/api/v1/reports/generate", "/api/v1/export/data", "/api/v1/batch/process"
]

# Endpoint performance profiles (probability of being slow)
ENDPOINT_PERFORMANCE = {
    "/api/v1/payments": "slow",           # Payment processing is often slow
    "/api/v1/reports/generate": "slow",   # Report generation is slow
    "/api/v1/export/data": "slow",        # Data export is slow
    "/api/v1/batch/process": "slow",      # Batch processing is slow
    "/api/v1/search": "medium",           # Search can be slow
    "/api/v1/analytics": "medium",        # Analytics queries are medium
    "/api/v1/orders": "medium",           # Order processing is medium
    "/api/v1/auth/login": "fast",         # Auth should be fast
    "/api/v1/auth/logout": "fast",        # Logout is fast
    "/api/v1/users": "fast",              # User lookups are fast
    "/api/v1/products": "fast",           # Product lookups are fast
    "/api/v1/notifications": "fast",      # Notifications are fast
    "/api/v1/inventory": "fast"           # Inventory lookups are fast
}


class SampleDataGenerator:
    """Generates realistic application log data"""

    def __init__(self, config_path: str = "../../../../config/config.yaml",
                 use_ai: bool = False, provider: str = None, ai_usage_rate: float = 50.0):
        """Initialize the generator

        Args:
            config_path: Path to configuration file
            use_ai: Whether to use AI for message generation
            provider: Inference provider for AI generation
            ai_usage_rate: Percentage of records to generate with AI (0-100)
        """
        self.config = self._load_config(config_path)
        self.use_ai = use_ai
        self.provider = provider or 'openai'
        self.ai_usage_rate = ai_usage_rate / 100.0  # Convert to 0-1 range
        self.inference_client = None
        self.fake = Faker()
        self.es_datasource = None
        self.es_client = None

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.is_absolute():
            # Resolve relative paths from the script's location, not the CWD
            script_dir = Path(__file__).parent
            config_file = (script_dir / config_file).resolve()

        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Process imports
        config = self._process_imports(config, config_file.parent)

        # Process environment variables (${VAR_NAME} syntax)
        config = self._process_env_vars(config)

        return config

    def _process_imports(self, config: Dict[str, Any], config_dir: Path) -> Dict[str, Any]:
        """Process import statements in config"""
        if not isinstance(config, dict):
            return config

        import_files = []
        keys_to_remove = []

        for key, value in config.items():
            if key == 'import':
                if isinstance(value, str):
                    import_files.append(value)
                elif isinstance(value, list):
                    import_files.extend(value)
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del config[key]

        for import_file in import_files:
            import_path = config_dir / import_file
            try:
                with open(import_path, 'r') as f:
                    imported_config = yaml.safe_load(f)
                    imported_config = self._process_imports(imported_config, config_dir)
                    config = self._merge_configs(config, imported_config)
            except Exception as e:
                logger.warning(f"Error loading import file {import_path}: {e}")

        return config

    def _merge_configs(self, main_config: Dict[str, Any],
                      imported_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge imported config into main config"""
        result = main_config.copy()
        for key, value in imported_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            elif key not in result:
                result[key] = value
        return result

    def _process_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process environment variables in config values (format: ${ENV_VAR_NAME})"""
        def replace_env_vars(value):
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                env_var_name = value[2:-1]
                env_value = os.environ.get(env_var_name)
                if env_value is not None:
                    return env_value
                else:
                    logger.warning(f"Environment variable {env_var_name} not found")
                    return ""
            return value

        def process_dict(d):
            result = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    result[k] = process_dict(v)
                elif isinstance(v, list):
                    result[k] = [process_dict(item) if isinstance(item, dict) else replace_env_vars(item) for item in v]
                else:
                    result[k] = replace_env_vars(v)
            return result

        return process_dict(config)

    async def initialize(self):
        """Initialize Elasticsearch connection and optionally AI client"""
        logger.info("🔧 Initializing connections...")

        # Initialize Elasticsearch datasource
        from server.datasources.registry import get_registry

        registry = get_registry()
        self.es_datasource = registry.get_or_create_datasource(
            datasource_name="elasticsearch",
            config=self.config,
            logger_instance=logger
        )

        if not self.es_datasource:
            raise RuntimeError("Failed to initialize Elasticsearch datasource")

        # Initialize datasource if needed
        if not self.es_datasource.is_initialized:
            await self.es_datasource.initialize()

        # Get Elasticsearch client
        self.es_client = self.es_datasource.client

        logger.info("✅ Elasticsearch client initialized")

        # Initialize AI client if requested
        if self.use_ai:
            logger.info(f"🤖 Initializing AI provider: {self.provider}")
            from server.inference.pipeline.providers.unified_provider_factory import UnifiedProviderFactory

            self.inference_client = UnifiedProviderFactory.create_provider_by_name(
                self.provider, self.config
            )
            await self.inference_client.initialize()
            logger.info("✅ AI client initialized")

    async def generate_ai_message(self, level: str, context: Dict[str, Any]) -> str:
        """Generate realistic log message using AI

        Args:
            level: Log level (ERROR, WARN, INFO, DEBUG)
            context: Context information for the log

        Returns:
            Generated log message
        """
        prompt = f"""Generate a realistic application log message for a {level} level log.

Context:
- Service: {context.get('service_name', 'unknown')}
- User ID: {context.get('user_id', 'N/A')}
- Environment: {context.get('environment', 'production')}

Requirements:
- Write only the log message text (no quotes, no prefix)
- Be specific and technical
- Include relevant details like IDs, durations, or error codes
- Make it sound like a real production system log

Examples of good {level} messages:
{chr(10).join(f'- {msg}' for msg in random.sample(LOG_TEMPLATES[level], min(3, len(LOG_TEMPLATES[level]))))}

Generate one log message:"""

        # Add rate limiting and retry logic
        max_retries = 3
        response = None
        timeout_seconds = 60  # 1 minute timeout per request

        for attempt in range(max_retries):
            try:
                # Add random delay to avoid rate limiting (0.5-2 seconds)
                delay = random.uniform(0.5, 2.0)
                await asyncio.sleep(delay)

                # Add timeout to prevent infinite hangs
                try:
                    response = await asyncio.wait_for(
                        self.inference_client.generate(prompt),
                        timeout=timeout_seconds
                    )
                    break  # Success, exit retry loop
                except asyncio.TimeoutError:
                    raise Exception(f"Request timed out after {timeout_seconds} seconds")

            except Exception as e:
                error_msg = str(e)
                is_rate_limit_error = '500' in error_msg or 'Internal Server Error' in error_msg or 'rate limit' in error_msg.lower()
                is_timeout = 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower()

                if (is_rate_limit_error or is_timeout) and attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    error_type = "Rate limited" if is_rate_limit_error else "Timeout"
                    logger.warning(f"   ⚠️  {error_type} (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                else:
                    # Either not a recoverable error, or we've exhausted retries
                    logger.warning(f"   ❌ AI generation failed after {attempt + 1} attempts: {error_msg}")
                    return self._generate_template_message(level, context)

        if response:
            # Clean up the response
            message = response.strip().strip('"').strip("'")
            return message
        else:
            logger.warning("AI generation failed: no response, using template")
            return self._generate_template_message(level, context)

    def _generate_template_message(self, level: str, context: Dict[str, Any]) -> str:
        """Generate message from templates"""
        template = random.choice(LOG_TEMPLATES[level])

        # Fill in placeholders with realistic values
        replacements = {
            'error': random.choice(EXCEPTION_TYPES),
            'user_id': context.get('user_id') or random.choice(USER_POOL),
            'service': random.choice(SERVICES),
            'timeout': random.randint(1000, 30000),
            'duration': random.randint(50, 5000),
            'percent': random.randint(60, 95),
            'query': f"SELECT * FROM {random.choice(['users', 'orders', 'products', 'inventory', 'payments'])}",
            'endpoint': random.choice(API_ENDPOINTS),
            'operation': random.choice(['database_query', 'api_call', 'cache_update', 'file_upload', 'email_send']),
            'attempt': random.randint(1, 5),
            'rate': random.randint(50, 90),
            'latency': random.randint(500, 3000),
            'depth': random.randint(100, 1000),
            'days': random.randint(1, 30),
            'ip': self.fake.ipv4(),
            'order_id': f"ORD-{self.fake.uuid4()[:8]}",
            'amount': f"{random.randint(10, 1000):.2f}",
            'entity': random.choice(['users', 'products', 'orders', 'inventory', 'sessions']),
            'job_name': random.choice(SCHEDULED_JOBS),
            'function': f"{self.fake.word()}Handler",
            'params': json.dumps({'page': random.randint(1, 10), 'limit': random.choice([10, 20, 50, 100])}),
            'key': self.fake.uuid4(),
            'count': random.randint(1, 100),
            'product_id': f"PROD-{self.fake.uuid4()[:6]}",
            'status': random.choice(['pending', 'processing', 'shipped', 'delivered', 'cancelled']),
            'report_type': random.choice(['sales_summary', 'inventory_report', 'user_activity', 'performance_metrics']),
            'email_type': random.choice(['order_confirmation', 'shipping_notification', 'password_reset', 'welcome_email']),
            'host': context.get('host', f"{random.choice(SERVICES)}-{random.randint(1, 10)}"),
            'request_id': self.fake.uuid4(),
            'config_file': random.choice(['application.yaml', 'database.yaml', 'services.yaml', 'security.yaml'])
        }

        try:
            return template.format(**replacements)
        except KeyError:
            # If some placeholder is missing, return template as is
            return template

    def _adjust_error_rate_for_spike(self, timestamp: datetime,
                                     base_error_rate: float) -> float:
        """Adjust error rate to create realistic spikes

        Args:
            timestamp: Timestamp of the log
            base_error_rate: Base error rate

        Returns:
            Adjusted error rate for this timestamp
        """
        # Create error spikes at certain times to make spike detection work
        # Spike 1: 2 hours ago (high spike)
        # Spike 2: 12 hours ago (medium spike)
        # Spike 3: 2 days ago (low spike)

        now = datetime.now(timezone.utc)
        hours_ago = (now - timestamp).total_seconds() / 3600

        # Recent spike (1-3 hours ago): 3x error rate
        if 1 <= hours_ago <= 3:
            return min(base_error_rate * 3, 0.6)  # Cap at 60%
        # Medium spike (10-14 hours ago): 2x error rate
        elif 10 <= hours_ago <= 14:
            return min(base_error_rate * 2, 0.4)  # Cap at 40%
        # Old spike (44-52 hours ago): 1.5x error rate
        elif 44 <= hours_ago <= 52:
            return min(base_error_rate * 1.5, 0.35)  # Cap at 35%

        return base_error_rate

    async def generate_log_record(self, timestamp: datetime,
                                  error_rate: float = 0.1) -> Dict[str, Any]:
        """Generate a single log record

        Args:
            timestamp: Timestamp for the log
            error_rate: Probability of generating an error log (0.0 to 1.0)

        Returns:
            Log record dictionary
        """
        # Adjust error rate to create spikes for realistic spike detection
        adjusted_error_rate = self._adjust_error_rate_for_spike(timestamp, error_rate)
        # Determine log level based on error rate
        # Ensure good distribution: ERROR, WARN, INFO, DEBUG
        # If error_rate = 0.25, distribution: 25% ERROR, 15% WARN, 50% INFO, 10% DEBUG
        rand = random.random()
        if rand < adjusted_error_rate:
            level = "ERROR"
        elif rand < adjusted_error_rate + (adjusted_error_rate * 0.6):  # 60% of error_rate for WARN
            level = "WARN"
        elif rand < adjusted_error_rate + (adjusted_error_rate * 0.6) + 0.1:  # 10% DEBUG
            level = "DEBUG"
        else:
            level = "INFO"

        # Basic context
        # For ERROR logs, use weighted selection to create realistic error distribution
        # Some services are more error-prone than others
        if level == "ERROR":
            # payment-service, auth-service, and api-gateway have more errors
            service_name = random.choices(
                SERVICES,
                weights=[15, 10, 10, 20, 8, 12, 15, 5, 3, 2, 0],  # payment-service and api-gateway weighted higher
                k=1
            )[0]
        else:
            service_name = random.choice(SERVICES)

        # Use realistic user pool - power users are more likely to appear
        # 70% of logs have a user_id, 30% are system/anonymous operations
        if random.random() > 0.3:
            # Power users appear 3x more often for realistic "most active users" queries
            if random.random() < 0.4:  # 40% chance of power user
                user_id = random.choice(POWER_USERS)
            else:
                user_id = random.choice(USER_POOL)
        else:
            user_id = None

        environment = random.choices(
            ["production", "staging", "development"],
            weights=[0.7, 0.2, 0.1]
        )[0]

        # Use realistic logger names
        logger_name = random.choice(LOGGER_NAMES)

        context = {
            'service_name': service_name,
            'user_id': user_id,
            'environment': environment,
            'logger_name': logger_name
        }

        # Generate message
        if self.use_ai and random.random() < self.ai_usage_rate:  # Use AI based on configurable rate
            message = await self.generate_ai_message(level, context)
        else:
            message = self._generate_template_message(level, context)
        
        # Add small delay between records to reduce AI call rate
        if self.use_ai:
            await asyncio.sleep(random.uniform(0.1, 0.3))

        # Base record
        record = {
            "timestamp": timestamp.isoformat().replace('+00:00', 'Z'),
            "level": level,
            "message": message,
            "logger": f"{service_name}.{logger_name}",
            "service_name": service_name,
            "environment": environment,
            "host": f"{service_name}-{random.randint(1, 10)}.{environment}.local",
            "request_id": self.fake.uuid4()
        }

        # Add user_id if present
        if user_id:
            record["user_id"] = user_id

        # Add response time and status code for most logs (70% of logs)
        # This ensures "search_slow_requests" queries return results
        # ERROR logs ALWAYS have response_time for aggregation queries
        if level == "ERROR" or random.random() < 0.7:  # 70% of logs have response time, ERROR logs always do
            # Select endpoint first
            endpoint = random.choice(API_ENDPOINTS)
            endpoint_profile = ENDPOINT_PERFORMANCE.get(endpoint, "fast")

            # Base response time on log level
            if level == "ERROR":
                # Errors have slow response times (5-30 seconds)
                base_response_time = random.randint(5000, 30000)
                record["status_code"] = random.choice(STATUS_CODES["ERROR"])
            elif level == "WARN":
                # Warnings have moderately slow response times (1-10 seconds)
                base_response_time = random.randint(1000, 10000)
                record["status_code"] = random.choice(STATUS_CODES["WARN"])
            else:
                # INFO/DEBUG logs - response time depends on endpoint profile
                if endpoint_profile == "slow":
                    # Slow endpoints: 70% are slow, 30% medium
                    if random.random() < 0.7:
                        base_response_time = random.randint(2000, 8000)  # Slow
                    else:
                        base_response_time = random.randint(500, 2000)   # Medium
                elif endpoint_profile == "medium":
                    # Medium endpoints: 50% medium, 30% slow, 20% fast
                    rand = random.random()
                    if rand < 0.5:
                        base_response_time = random.randint(500, 2000)   # Medium
                    elif rand < 0.8:
                        base_response_time = random.randint(2000, 5000)  # Slow
                    else:
                        base_response_time = random.randint(50, 500)     # Fast
                else:  # "fast"
                    # Fast endpoints: 80% fast, 15% medium, 5% slow
                    rand = random.random()
                    if rand < 0.80:
                        base_response_time = random.randint(10, 500)     # Fast
                    elif rand < 0.95:
                        base_response_time = random.randint(500, 2000)   # Medium
                    else:
                        base_response_time = random.randint(2000, 5000)  # Occasionally slow

                record["status_code"] = random.choice(STATUS_CODES.get(level, STATUS_CODES["INFO"]))

            record["response_time"] = base_response_time
            record["endpoint"] = endpoint

        # Add exception details for errors (REQUIRED for aggregation queries)
        if level == "ERROR":
            exception_type = random.choice(EXCEPTION_TYPES)
            record["exception"] = {
                "type": exception_type,
                "message": f"{exception_type}: {self.fake.sentence()}",
                "stacktrace": self._generate_stacktrace(service_name)
            }

        return record

    def _generate_stacktrace(self, service_name: str) -> str:
        """Generate realistic stack trace"""
        lines = []
        depth = random.randint(5, 15)

        for i in range(depth):
            class_name = f"{self.fake.word().title()}Handler"
            method = f"{self.fake.word()}Method"
            file_name = f"{self.fake.word()}.py"
            line_num = random.randint(10, 500)
            lines.append(f'  File "{service_name}/{file_name}", line {line_num}, in {method}')
            lines.append(f'    {class_name}.{method}()')

        return '\n'.join(lines)

    def _generate_correlated_trace(self, base_timestamp: datetime,
                                     user_id: Optional[str],
                                     environment: str) -> List[Dict[str, Any]]:
        """Generate a correlated request trace across multiple services

        This creates realistic distributed traces where a single request
        flows through multiple services with the same request_id.

        Args:
            base_timestamp: Starting timestamp for the trace
            user_id: User ID if authenticated request
            environment: Environment (production, staging, development)

        Returns:
            List of correlated log records
        """
        request_id = self.fake.uuid4()
        records = []

        # Define realistic request flows
        TRACE_FLOWS = [
            # E-commerce order flow
            [
                ("api-gateway", "INFO", "Incoming request to {endpoint}", 50),
                ("auth-service", "INFO", "JWT token validated for user {user_id}", 30),
                ("order-service", "INFO", "Order {order_id} created successfully", 200),
                ("payment-service", "INFO", "Payment of ${amount} processed for order {order_id}", 500),
                ("inventory-service", "INFO", "Inventory updated for product {product_id}: {count} units", 100),
                ("notification-service", "INFO", "Email sent to user {user_id}: order_confirmation", 150),
            ],
            # Failed payment flow
            [
                ("api-gateway", "INFO", "Incoming request to {endpoint}", 50),
                ("auth-service", "INFO", "JWT token validated for user {user_id}", 30),
                ("order-service", "INFO", "Order {order_id} created successfully", 200),
                ("payment-service", "ERROR", "Payment processing failed: {error}", 2000),
                ("order-service", "WARN", "Order {order_id} taking longer than expected", 100),
            ],
            # User login flow
            [
                ("api-gateway", "INFO", "Incoming request to {endpoint}", 30),
                ("auth-service", "DEBUG", "Validating request payload", 10),
                ("auth-service", "INFO", "User {user_id} logged in from {ip}", 150),
                ("user-service", "INFO", "Request processed successfully in {duration}ms", 50),
            ],
            # Search flow
            [
                ("api-gateway", "INFO", "Incoming request to {endpoint}", 40),
                ("search-service", "DEBUG", "Query parameters: {params}", 10),
                ("search-service", "DEBUG", "Database query executed in {duration}ms", 300),
                ("search-service", "INFO", "Request processed successfully in {duration}ms", 50),
            ],
            # Report generation flow
            [
                ("api-gateway", "INFO", "Incoming request to {endpoint}", 50),
                ("auth-service", "INFO", "JWT token validated for user {user_id}", 30),
                ("analytics-service", "INFO", "Report generated for user {user_id}: sales_summary", 3000),
                ("notification-service", "INFO", "Email sent to user {user_id}: report_ready", 100),
            ],
        ]

        flow = random.choice(TRACE_FLOWS)
        current_time = base_timestamp
        order_id = f"ORD-{self.fake.uuid4()[:8]}"

        for service_name, level, message_template, duration_ms in flow:
            logger_name = random.choice(LOGGER_NAMES)

            # Generate message with context
            context = {
                'user_id': user_id,
                'service_name': service_name,
                'environment': environment,
                'host': f"{service_name}-{random.randint(1, 5)}.{environment}.local"
            }

            # Fill in message template
            replacements = {
                'endpoint': random.choice(API_ENDPOINTS),
                'user_id': user_id or random.choice(USER_POOL),
                'order_id': order_id,
                'amount': f"{random.randint(10, 500):.2f}",
                'product_id': f"PROD-{self.fake.uuid4()[:6]}",
                'count': random.randint(1, 50),
                'error': random.choice(EXCEPTION_TYPES),
                'ip': self.fake.ipv4(),
                'duration': duration_ms + random.randint(-20, 50),
                'params': json.dumps({'q': self.fake.word(), 'limit': 20}),
            }

            try:
                message = message_template.format(**replacements)
            except KeyError:
                message = message_template

            record = {
                "timestamp": current_time.isoformat().replace('+00:00', 'Z'),
                "level": level,
                "message": message,
                "logger": f"{service_name}.{logger_name}",
                "service_name": service_name,
                "environment": environment,
                "host": context['host'],
                "request_id": request_id,
                "response_time": duration_ms + random.randint(-10, 30),
                "endpoint": random.choice(API_ENDPOINTS),
                "status_code": 500 if level == "ERROR" else 200,
            }

            if user_id:
                record["user_id"] = user_id

            # Add exception for errors
            if level == "ERROR":
                exception_type = random.choice(EXCEPTION_TYPES)
                record["exception"] = {
                    "type": exception_type,
                    "message": f"{exception_type}: {self.fake.sentence()}",
                    "stacktrace": self._generate_stacktrace(service_name)
                }

            records.append(record)

            # Advance time
            current_time = current_time + timedelta(milliseconds=duration_ms + random.randint(5, 50))

        return records

    async def generate_records(self, count: int, days_back: int = 7,
                               error_rate: float = 0.1) -> List[Dict[str, Any]]:
        """Generate multiple log records

        Args:
            count: Number of records to generate
            days_back: Generate logs spanning this many days back
            error_rate: Percentage of error logs (0.0 to 1.0)

        Returns:
            List of log records
        """
        logger.info(f"📝 Generating {count} log records...")

        records = []
        now = datetime.now(timezone.utc)

        # Generate ~10% of logs as correlated traces for realistic request tracing
        trace_count = int(count * 0.1)
        single_count = count - (trace_count * 5)  # Avg 5 records per trace

        logger.info(f"   Generating {trace_count} correlated traces...")
        for i in range(trace_count):
            seconds_back = random.randint(0, days_back * 24 * 3600)
            timestamp = now - timedelta(seconds=seconds_back)

            # Select user (power users more likely)
            if random.random() < 0.4:
                user_id = random.choice(POWER_USERS)
            else:
                user_id = random.choice(USER_POOL) if random.random() > 0.2 else None

            environment = random.choices(
                ["production", "staging", "development"],
                weights=[0.7, 0.2, 0.1]
            )[0]

            trace_records = self._generate_correlated_trace(timestamp, user_id, environment)
            records.extend(trace_records)

            if (i + 1) % 50 == 0:
                logger.info(f"   Generated {i + 1}/{trace_count} traces...")

        logger.info(f"   Generating {single_count} individual records...")
        for i in range(single_count):
            # Distribute logs across the time range
            seconds_back = random.randint(0, days_back * 24 * 3600)
            timestamp = now - timedelta(seconds=seconds_back)

            record = await self.generate_log_record(timestamp, error_rate)
            records.append(record)

            if (i + 1) % 100 == 0:
                logger.info(f"   Generated {i + 1}/{single_count} individual records...")

        # Sort by timestamp for realistic ordering
        records.sort(key=lambda x: x['timestamp'])

        logger.info(f"✅ Generated {len(records)} total records ({trace_count} traces + {single_count} individual)")
        return records

    async def create_index(self, index_name: str):
        """Create Elasticsearch index with proper mapping

        Args:
            index_name: Name of the index to create
        """
        logger.info(f"📋 Creating index: {index_name}")

        # Check if index exists
        exists = await self.es_client.indices.exists(index=index_name)

        if exists:
            logger.info(f"   Index {index_name} already exists")
            return

        # Create index with mapping
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "5s"
            },
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "level": {"type": "keyword"},
                    "message": {"type": "text", "analyzer": "standard"},
                    "logger": {"type": "keyword"},
                    "service_name": {
                        "type": "text",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "ignore_above": 256
                            }
                        }
                    },
                    "environment": {"type": "keyword"},
                    "host": {"type": "keyword"},
                    "request_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "response_time": {"type": "integer"},
                    "status_code": {"type": "integer"},
                    "endpoint": {"type": "keyword"},
                    "exception": {
                        "properties": {
                            "type": {
                                "type": "text",
                                "fields": {
                                    "keyword": {
                                        "type": "keyword",
                                        "ignore_above": 256
                                    }
                                }
                            },
                            "message": {"type": "text"},
                            "stacktrace": {"type": "text"}
                        }
                    }
                }
            }
        }

        await self.es_client.indices.create(index=index_name, body=mapping)
        logger.info(f"✅ Index {index_name} created")

    async def index_records(self, records: List[Dict[str, Any]],
                           index_name: str, batch_size: int = 100):
        """Index records into Elasticsearch using bulk API

        Args:
            records: List of records to index
            index_name: Target index name
            batch_size: Number of records per bulk request
        """
        logger.info(f"📤 Indexing {len(records)} records into {index_name}...")

        from elasticsearch.helpers import async_bulk

        # Prepare bulk actions
        actions = []
        for record in records:
            action = {
                "_index": index_name,
                "_source": record
            }
            actions.append(action)

        # Bulk index with progress tracking
        success_count = 0
        error_count = 0
        
        # Process in batches
        for i in range(0, len(actions), batch_size):
            batch = actions[i:i + batch_size]
            
            try:
                # Use the bulk helper - it returns (success_count, failed_items)
                success_count_batch, failed_items = await async_bulk(
                    self.es_client,
                    batch,
                    chunk_size=batch_size,
                    raise_on_error=False
                )
                
                success_count += success_count_batch
                error_count += len(failed_items) if failed_items else 0
                
                # Log any failed items for debugging
                if failed_items:
                    logger.warning(f"   Batch {i//batch_size + 1}: {len(failed_items)} items failed")
                    for item in failed_items[:3]:  # Show first 3 errors
                        logger.warning(f"     Error: {item}")
                
                if (i + batch_size) % 500 == 0 or i + batch_size >= len(actions):
                    logger.info(f"   Processed {i + len(batch)}/{len(records)} records...")
                    
            except Exception as e:
                logger.error(f"   Error indexing batch {i//batch_size + 1}: {e}")
                error_count += len(batch)

        # Refresh index
        await self.es_client.indices.refresh(index=index_name)

        logger.info(f"✅ Indexed {success_count} records successfully ({error_count} errors)")

    async def cleanup(self):
        """Cleanup connections"""
        if self.es_datasource:
            await self.es_datasource.close()


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Generate and index sample application log data into Elasticsearch'
    )
    parser.add_argument('--config', default='../../../../config/config.yaml',
                       help='Path to main config file')
    parser.add_argument('--count', type=int, default=1000,
                       help='Number of log records to generate')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for bulk indexing')
    parser.add_argument('--index', default='application-logs-demo',
                       help='Elasticsearch index name')
    parser.add_argument('--use-ai', action='store_true',
                       help='Use AI to generate realistic log messages')
    parser.add_argument('--provider', default='openai',
                       help='Inference provider for AI generation')
    parser.add_argument('--days-back', type=int, default=7,
                       help='Generate logs spanning this many days back')
    parser.add_argument('--error-rate', type=float, default=30.0,
                       help='Percentage of error logs (0-100)')
    parser.add_argument('--ai-usage-rate', type=float, default=50.0,
                       help='Percentage of records to generate with AI (0-100, default: 50)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Generate data without connecting to Elasticsearch')

    args = parser.parse_args()

    # Convert error rate to 0-1 range
    error_rate = args.error_rate / 100.0

    logger.info("🚀 Elasticsearch Sample Data Generator")
    logger.info("=" * 60)

    # Create generator
    generator = SampleDataGenerator(
        config_path=args.config,
        use_ai=args.use_ai,
        provider=args.provider,
        ai_usage_rate=args.ai_usage_rate
    )

    try:
        if not args.dry_run:
            # Initialize
            await generator.initialize()

            # Create index
            await generator.create_index(args.index)

        # Generate records
        records = await generator.generate_records(
            count=args.count,
            days_back=args.days_back,
            error_rate=error_rate
        )

        if not args.dry_run:
            # Index records
            await generator.index_records(
                records=records,
                index_name=args.index,
                batch_size=args.batch_size
            )

            logger.info("=" * 60)
            logger.info("🎉 Sample data generation complete!")
            logger.info(f"📊 Indexed {len(records)} records into {args.index}")
            logger.info(f"📅 Time range: {args.days_back} days")
            logger.info(f"⚠️  Error rate: {args.error_rate}%")
        else:
            logger.info("=" * 60)
            logger.info("🎉 Sample data generation complete! (Dry run)")
            logger.info(f"📊 Generated {len(records)} records")
            logger.info(f"📅 Time range: {args.days_back} days")
            logger.info(f"⚠️  Error rate: {args.error_rate}%")
            logger.info("💡 Use without --dry-run to index into Elasticsearch")

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await generator.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
