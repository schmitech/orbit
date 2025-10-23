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
    --index         Elasticsearch index name (default: logs-app-demo)
    --use-ai        Use AI to generate realistic log messages (default: False)
    --provider      Inference provider for AI generation (default: openai)
    --days-back     Generate logs spanning this many days back (default: 7)
    --error-rate    Percentage of error logs (default: 10)

EXAMPLES:
    # Generate 1000 logs with default settings
    python utils/elasticsearch-intent-template/generate_sample_data.py

    # Generate 5000 logs with AI-generated messages
    python utils/elasticsearch-intent-template/generate_sample_data.py \
        --count 5000 \
        --use-ai \
        --provider anthropic

    # Generate logs for 30 days with higher error rate
    python utils/elasticsearch-intent-template/generate_sample_data.py \
        --count 10000 \
        --days-back 30 \
        --error-rate 20
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
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from faker import Faker

print("✅ Basic imports complete", flush=True)

from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

print("✅ Path configured", flush=True)

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

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
        "Unhandled exception in {service}: {error}"
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
        "Unusual traffic pattern detected from IP {ip}"
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
        "API endpoint {endpoint} called by user {user_id}"
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
        "Building SQL query: {query}"
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

# API endpoints
API_ENDPOINTS = [
    "/api/v1/users", "/api/v1/orders", "/api/v1/payments", "/api/v1/products",
    "/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/search",
    "/api/v1/notifications", "/api/v1/analytics", "/api/v1/inventory"
]


class SampleDataGenerator:
    """Generates realistic application log data"""

    def __init__(self, config_path: str = "../../config/config.yaml",
                 use_ai: bool = False, provider: str = None):
        """Initialize the generator

        Args:
            config_path: Path to configuration file
            use_ai: Whether to use AI for message generation
            provider: Inference provider for AI generation
        """
        self.config = self._load_config(config_path)
        self.use_ai = use_ai
        self.provider = provider or 'openai'
        self.inference_client = None
        self.fake = Faker()
        self.es_datasource = None
        self.es_client = None

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Process imports
        config = self._process_imports(config, config_file.parent)

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

    async def initialize(self):
        """Initialize Elasticsearch connection and optionally AI client"""
        logger.info("🔧 Initializing connections...")

        # Initialize Elasticsearch datasource
        from datasources.registry import get_registry

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

        try:
            response = await self.inference_client.generate(prompt)
            # Clean up the response
            message = response.strip().strip('"').strip("'")
            return message
        except Exception as e:
            logger.warning(f"AI generation failed: {e}, using template")
            return self._generate_template_message(level, context)

    def _generate_template_message(self, level: str, context: Dict[str, Any]) -> str:
        """Generate message from templates"""
        template = random.choice(LOG_TEMPLATES[level])

        # Fill in placeholders
        replacements = {
            'error': random.choice(EXCEPTION_TYPES),
            'user_id': context.get('user_id', self.fake.uuid4()[:8]),
            'service': random.choice(SERVICES),
            'timeout': random.randint(1000, 30000),
            'duration': random.randint(50, 5000),
            'percent': random.randint(60, 95),
            'query': f"SELECT * FROM {self.fake.word()}",
            'endpoint': random.choice(API_ENDPOINTS),
            'operation': random.choice(['database_query', 'api_call', 'cache_update']),
            'attempt': random.randint(1, 5),
            'rate': random.randint(50, 90),
            'latency': random.randint(500, 3000),
            'depth': random.randint(100, 1000),
            'days': random.randint(1, 30),
            'ip': self.fake.ipv4(),
            'order_id': f"ORD-{self.fake.uuid4()[:8]}",
            'amount': f"{random.randint(10, 1000):.2f}",
            'entity': random.choice(['users', 'products', 'orders']),
            'job_name': f"{random.choice(['sync', 'backup', 'cleanup'])}_job",
            'function': f"{self.fake.word()}Handler",
            'params': json.dumps({'page': 1, 'limit': 20}),
            'key': self.fake.uuid4(),
            'count': random.randint(1, 100)
        }

        try:
            return template.format(**replacements)
        except KeyError:
            # If some placeholder is missing, return template as is
            return template

    async def generate_log_record(self, timestamp: datetime,
                                  error_rate: float = 0.1) -> Dict[str, Any]:
        """Generate a single log record

        Args:
            timestamp: Timestamp for the log
            error_rate: Probability of generating an error log (0.0 to 1.0)

        Returns:
            Log record dictionary
        """
        # Determine log level based on error rate
        rand = random.random()
        if rand < error_rate:
            level = "ERROR"
        elif rand < error_rate + 0.1:
            level = "WARN"
        elif rand < error_rate + 0.3:
            level = "DEBUG"
        else:
            level = "INFO"

        # Basic context
        service_name = random.choice(SERVICES)
        user_id = f"user-{self.fake.uuid4()[:8]}" if random.random() > 0.3 else None
        environment = random.choices(
            ["production", "staging", "development"],
            weights=[0.7, 0.2, 0.1]
        )[0]

        context = {
            'service_name': service_name,
            'user_id': user_id,
            'environment': environment
        }

        # Generate message
        if self.use_ai and random.random() > 0.5:  # Use AI 50% of the time
            message = await self.generate_ai_message(level, context)
        else:
            message = self._generate_template_message(level, context)

        # Base record
        record = {
            "timestamp": timestamp.isoformat(),
            "level": level,
            "message": message,
            "logger": f"{service_name}.{self.fake.word()}Logger",
            "service_name": service_name,
            "environment": environment,
            "host": f"{service_name}-{random.randint(1, 10)}.{environment}.local",
            "request_id": self.fake.uuid4()
        }

        # Add user_id if present
        if user_id:
            record["user_id"] = user_id

        # Add response time and status code for API-related logs
        if any(keyword in message.lower() for keyword in ['api', 'request', 'endpoint', 'call']):
            if level == "ERROR":
                record["response_time"] = random.randint(5000, 30000)
                record["status_code"] = random.choice(STATUS_CODES["ERROR"])
            elif level == "WARN":
                record["response_time"] = random.randint(2000, 10000)
                record["status_code"] = random.choice(STATUS_CODES["WARN"])
            else:
                record["response_time"] = random.randint(10, 2000)
                record["status_code"] = random.choice(STATUS_CODES["INFO"])

            record["endpoint"] = random.choice(API_ENDPOINTS)

        # Add exception details for errors
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
        now = datetime.utcnow()

        for i in range(count):
            # Distribute logs across the time range
            seconds_back = random.randint(0, days_back * 24 * 3600)
            timestamp = now - timedelta(seconds=seconds_back)

            record = await self.generate_log_record(timestamp, error_rate)
            records.append(record)

            if (i + 1) % 100 == 0:
                logger.info(f"   Generated {i + 1}/{count} records...")

        logger.info(f"✅ Generated {count} records")
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
                    "service_name": {"type": "keyword"},
                    "environment": {"type": "keyword"},
                    "host": {"type": "keyword"},
                    "request_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "response_time": {"type": "integer"},
                    "status_code": {"type": "integer"},
                    "endpoint": {"type": "keyword"},
                    "exception": {
                        "properties": {
                            "type": {"type": "keyword"},
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
        indexed = 0
        async for ok, result in async_bulk(
            self.es_client,
            actions,
            chunk_size=batch_size,
            raise_on_error=False
        ):
            indexed += 1
            if indexed % 500 == 0:
                logger.info(f"   Indexed {indexed}/{len(records)} records...")

        # Refresh index
        await self.es_client.indices.refresh(index=index_name)

        logger.info(f"✅ Indexed {indexed} records successfully")

    async def cleanup(self):
        """Cleanup connections"""
        if self.es_datasource:
            await self.es_datasource.close()


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Generate and index sample application log data into Elasticsearch'
    )
    parser.add_argument('--config', default='../../config/config.yaml',
                       help='Path to main config file')
    parser.add_argument('--count', type=int, default=1000,
                       help='Number of log records to generate')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for bulk indexing')
    parser.add_argument('--index', default='logs-app-demo',
                       help='Elasticsearch index name')
    parser.add_argument('--use-ai', action='store_true',
                       help='Use AI to generate realistic log messages')
    parser.add_argument('--provider', default='openai',
                       help='Inference provider for AI generation')
    parser.add_argument('--days-back', type=int, default=7,
                       help='Generate logs spanning this many days back')
    parser.add_argument('--error-rate', type=float, default=10.0,
                       help='Percentage of error logs (0-100)')

    args = parser.parse_args()

    # Convert error rate to 0-1 range
    error_rate = args.error_rate / 100.0

    logger.info("🚀 Elasticsearch Sample Data Generator")
    logger.info("=" * 60)

    # Create generator
    generator = SampleDataGenerator(
        config_path=args.config,
        use_ai=args.use_ai,
        provider=args.provider
    )

    try:
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

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await generator.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
