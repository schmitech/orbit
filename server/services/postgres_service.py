"""
PostgreSQL Service
==================

This service provides a PostgreSQL-based database implementation that follows the
DatabaseService interface. It uses psycopg (psycopg3) with a single connection guarded
by a lock and a ThreadPoolExecutor for async operations, mirroring SQLiteService's
architecture since the internal-services database has modest throughput needs and a
single connection makes execute_transaction trivially correct.

Implements singleton pattern to share PostgreSQL connections across services.
"""

import contextlib
import json
import logging
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List, Union, Tuple, Callable, Awaitable
from datetime import datetime

from services.database_service import DatabaseService
from services.sqlite_service import _make_json_serializable
from utils.id_utils import generate_id, ensure_id, id_to_string

logger = logging.getLogger(__name__)


class PostgresService(DatabaseService):
    """Service for handling PostgreSQL database operations with singleton pattern"""

    _instances: Dict[str, 'PostgresService'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any]):
        """
        Implement singleton pattern for Postgres service.
        Returns existing instance if configuration matches.
        """
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                logger.debug(f"Creating new Postgres service instance for key: {cache_key}")
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
            else:
                logger.debug(f"Reusing cached Postgres service instance for key: {cache_key}")

            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        """Create a cache key based on Postgres connection configuration."""
        postgres_config = config.get('internal_services', {}).get('backend', {}).get('postgres', {})

        host = postgres_config.get('host', 'localhost')
        port = postgres_config.get('port', 5432)
        database = postgres_config.get('database', 'orbit')

        return f"postgres:{host}:{port}:{database}"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Postgres service with configuration"""
        # Prevent re-initialization of singleton instances
        if hasattr(self, '_initialized') and self._initialized:
            return

        super().__init__(config)

        # Get Postgres configuration
        postgres_config = config.get('internal_services', {}).get('backend', {}).get('postgres', {})
        self.host = postgres_config.get('host', 'localhost')
        self.port = postgres_config.get('port', 5432)
        self.database = postgres_config.get('database', 'orbit')
        self.username = postgres_config.get('username', 'postgres')
        self.password = postgres_config.get('password', '')
        self.sslmode = postgres_config.get('sslmode', 'prefer')

        # Initialize connection and executor
        self.connection = None
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix='postgres_')
        self._collections = {}

        # Lock for thread-safe database operations (single connection, like SQLiteService)
        self._db_lock = threading.Lock()

        # When True, _execute_sql defers committing to execute_transaction's own
        # commit/rollback instead of auto-committing each statement.
        self._in_transaction = False
        # The asyncio task currently running inside execute_transaction, if any.
        self._transaction_task: Optional[asyncio.Task] = None
        # Serializes writes against the single shared connection so a concurrent
        # caller can never be silently swept into another caller's transaction
        # (or have its auto-commit suppressed by someone else's _in_transaction).
        self._operation_lock = asyncio.Lock()

        # Track pending indexes for tables that don't exist yet
        self._pending_indexes = {}

        # Schema definitions (logical schema matches SQLiteService - see docs/sqlite-schema.md)
        self._schema = {
            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                )
            ''',
            'sessions': '''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    expires TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''',
            'api_keys': '''
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    api_key TEXT UNIQUE NOT NULL,
                    client_name TEXT NOT NULL,
                    notes TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    adapter_name TEXT,
                    system_prompt_id TEXT,
                    quota_daily_limit INTEGER,
                    quota_monthly_limit INTEGER,
                    quota_throttle_enabled INTEGER,
                    quota_throttle_priority INTEGER
                )
            ''',
            'system_prompts': '''
                CREATE TABLE IF NOT EXISTS system_prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    prompt TEXT NOT NULL,
                    version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''',
            'chat_history': '''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    api_key TEXT,
                    metadata_json TEXT,
                    message_hash TEXT,
                    token_count INTEGER
                )
            ''',
            'conversation_threads': '''
                CREATE TABLE IF NOT EXISTS conversation_threads (
                    id TEXT PRIMARY KEY,
                    parent_message_id TEXT NOT NULL,
                    parent_session_id TEXT NOT NULL,
                    thread_session_id TEXT NOT NULL,
                    adapter_name TEXT NOT NULL,
                    query_context TEXT NOT NULL,
                    dataset_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    metadata_json TEXT
                )
            ''',
            'thread_datasets': '''
                CREATE TABLE IF NOT EXISTS thread_datasets (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    dataset_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''',
            'uploaded_files': '''
                CREATE TABLE IF NOT EXISTS uploaded_files (
                    id TEXT PRIMARY KEY,
                    api_key TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    mime_type TEXT,
                    file_size INTEGER,
                    upload_timestamp TEXT,
                    processing_status TEXT,
                    storage_key TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    vector_store TEXT,
                    collection_name TEXT,
                    storage_type TEXT DEFAULT 'vector',
                    metadata_json TEXT,
                    embedding_provider TEXT,
                    embedding_dimensions INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP::TEXT
                )
            ''',
            'file_chunks': '''
                CREATE TABLE IF NOT EXISTS file_chunks (
                    id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    chunk_index INTEGER,
                    vector_store_id TEXT,
                    collection_name TEXT,
                    chunk_metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP::TEXT,
                    FOREIGN KEY (file_id) REFERENCES uploaded_files(id)
                )
            ''',
            'audit_logs': '''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    query TEXT NOT NULL,
                    response TEXT NOT NULL,
                    response_compressed INTEGER NOT NULL DEFAULT 0,
                    provider TEXT,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    ip TEXT,
                    ip_type TEXT,
                    ip_is_local INTEGER DEFAULT 0,
                    ip_source TEXT,
                    ip_original_value TEXT,
                    api_key_value TEXT,
                    api_key_timestamp TEXT,
                    session_id TEXT,
                    user_id TEXT,
                    adapter_name TEXT,
                    model TEXT
                )
            ''',
            'feedback': '''
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT,
                    feedback_type TEXT NOT NULL,
                    adapter_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''',
            'audit_admin_logs': '''
                CREATE TABLE IF NOT EXISTS audit_admin_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT,
                    actor_type TEXT NOT NULL,
                    actor_id TEXT,
                    actor_username TEXT,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    success INTEGER NOT NULL DEFAULT 0,
                    ip TEXT,
                    ip_type TEXT,
                    ip_is_local INTEGER DEFAULT 0,
                    ip_source TEXT,
                    ip_original_value TEXT,
                    user_agent TEXT,
                    error_message TEXT,
                    request_summary TEXT
                )
            '''
        }

        # Index definitions
        self._indexes = {
            'users': [
                'CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)',
            ],
            'sessions': [
                'CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)',
                'CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires)',
            ],
            'api_keys': [
                'CREATE INDEX IF NOT EXISTS idx_api_keys_api_key ON api_keys(api_key)',
            ],
            'system_prompts': [
                'CREATE INDEX IF NOT EXISTS idx_system_prompts_name ON system_prompts(name)',
            ],
            'chat_history': [
                'CREATE INDEX IF NOT EXISTS idx_chat_history_session ON chat_history(session_id, timestamp)',
                'CREATE INDEX IF NOT EXISTS idx_chat_history_user ON chat_history(user_id, timestamp)',
                'CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)',
                'CREATE INDEX IF NOT EXISTS idx_chat_history_api_key ON chat_history(api_key)',
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_history_hash ON chat_history(session_id, message_hash)',
            ],
            'conversation_threads': [
                'CREATE INDEX IF NOT EXISTS idx_conversation_threads_parent_message ON conversation_threads(parent_message_id)',
                'CREATE INDEX IF NOT EXISTS idx_conversation_threads_parent_session ON conversation_threads(parent_session_id)',
                'CREATE INDEX IF NOT EXISTS idx_conversation_threads_thread_session ON conversation_threads(thread_session_id)',
                'CREATE INDEX IF NOT EXISTS idx_conversation_threads_expires_at ON conversation_threads(expires_at)',
            ],
            'thread_datasets': [
                'CREATE INDEX IF NOT EXISTS idx_thread_datasets_thread_id ON thread_datasets(thread_id)',
                'CREATE INDEX IF NOT EXISTS idx_thread_datasets_expires_at ON thread_datasets(expires_at)',
            ],
            'uploaded_files': [
                'CREATE INDEX IF NOT EXISTS idx_uploaded_files_api_key ON uploaded_files(api_key)',
                'CREATE INDEX IF NOT EXISTS idx_uploaded_files_processing_status ON uploaded_files(processing_status)',
            ],
            'file_chunks': [
                'CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id ON file_chunks(file_id)',
            ],
            'audit_logs': [
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)',
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_session_id ON audit_logs(session_id)',
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)',
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_blocked ON audit_logs(blocked)',
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_provider ON audit_logs(provider)',
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_adapter_name ON audit_logs(adapter_name)',
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_model ON audit_logs(model)',
            ],
            'feedback': [
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_message_session ON feedback(message_id, session_id)',
                'CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id)',
                'CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type)',
                'CREATE INDEX IF NOT EXISTS idx_feedback_adapter ON feedback(adapter_name)',
            ],
            'audit_admin_logs': [
                'CREATE INDEX IF NOT EXISTS idx_audit_admin_logs_timestamp ON audit_admin_logs(timestamp)',
                'CREATE INDEX IF NOT EXISTS idx_audit_admin_logs_actor_id ON audit_admin_logs(actor_id)',
                'CREATE INDEX IF NOT EXISTS idx_audit_admin_logs_event_type ON audit_admin_logs(event_type)',
                'CREATE INDEX IF NOT EXISTS idx_audit_admin_logs_resource_type ON audit_admin_logs(resource_type)',
                'CREATE INDEX IF NOT EXISTS idx_audit_admin_logs_success ON audit_admin_logs(success)',
            ],
        }

    async def initialize(self) -> None:
        """Initialize connection to PostgreSQL database and create tables"""
        if self._initialized:
            return

        try:
            logger.debug(f"Initializing PostgreSQL connection to: {self.host}:{self.port}/{self.database}")

            loop = asyncio.get_running_loop()
            self.connection = await loop.run_in_executor(
                self.executor,
                self._connect_db
            )

            # Create tables and indexes
            await self._create_tables()
            await self._create_indexes()

            logger.debug("Postgres Service initialized successfully")

            self._initialized = True

        except Exception as e:
            if hasattr(self, 'connection') and self.connection:
                try:
                    self.connection.close()
                except Exception:
                    pass
            logger.error(f"Failed to initialize Postgres Service: {str(e)}")
            raise

    def _connect_db(self):
        """Connect to PostgreSQL database (runs in thread)"""
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.username,
            password=self.password,
            sslmode=self.sslmode,
            row_factory=dict_row,
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        cursor.close()
        conn.commit()

        if version:
            logger.debug(f"PostgreSQL connection successful: {version['version']}")

        return conn

    async def _create_tables(self) -> None:
        """Create database tables and ensure all columns exist"""
        loop = asyncio.get_running_loop()
        for table_name, schema in self._schema.items():
            await loop.run_in_executor(
                self.executor,
                self._execute_sql,
                schema,
                ()
            )
            logger.debug(f"Created table: {table_name}")

            await loop.run_in_executor(
                self.executor,
                self._migrate_table_schema,
                table_name,
                schema
            )

    def _migrate_table_schema(self, table_name: str, schema_sql: str) -> None:
        """Ensure any columns added to the schema after initial release exist on the table.

        Postgres supports `ADD COLUMN IF NOT EXISTS`, so unlike SQLite this doesn't need
        to pre-check existing columns - the statement is naturally idempotent.
        """
        first_paren = schema_sql.find('(')
        last_paren = schema_sql.rfind(')')
        if first_paren == -1 or last_paren == -1:
            return

        columns_part = schema_sql[first_paren + 1:last_paren]
        lines = [line.strip() for line in columns_part.split('\n')]
        for line in lines:
            if not line or line.startswith('FOREIGN KEY') or line.startswith('PRIMARY KEY') or line.startswith('UNIQUE'):
                continue

            parts = line.split(None, 2)
            if not parts:
                continue

            column_name = parts[0].strip('",`')
            if not column_name:
                continue

            col_def = line[line.find(parts[0]) + len(parts[0]):].strip()
            if col_def.endswith(','):
                col_def = col_def[:-1].strip()

            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {col_def}"
            try:
                with self._db_lock:
                    cursor = self.connection.cursor()
                    cursor.execute(alter_sql)
                    self.connection.commit()
            except Exception as e:
                logger.error(f"Failed to ensure column '{column_name}' on table '{table_name}': {e}")
                self.connection.rollback()

    async def _create_indexes(self) -> None:
        """Create database indexes"""
        loop = asyncio.get_running_loop()
        for table_name, indexes in self._indexes.items():
            for index_sql in indexes:
                await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    index_sql,
                    ()
                )

    def _operation_scope(self):
        """Async context manager serializing writes against the single shared connection.

        Returns a no-op scope when called from within the task that owns the currently
        active transaction (so execute_transaction's nested insert_one/update_one/etc.
        calls don't deadlock on a lock they already hold). Any other concurrent caller
        blocks until the transaction completes, instead of being silently swept into it
        (or having its own auto-commit suppressed by someone else's _in_transaction).
        """
        if self._in_transaction and self._transaction_task is asyncio.current_task():
            return contextlib.AsyncExitStack()
        return self._operation_lock

    def _execute_sql(self, sql: str, params: tuple):
        """Execute SQL statement (runs in thread) - thread-safe.

        Skips the per-statement commit while inside execute_transaction so that a
        rollback there actually undoes statements run earlier in the transaction.
        """
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            if not self._in_transaction:
                self.connection.commit()
            return cursor

    def _execute_sql_fetchone(self, sql: str, params: tuple) -> Optional[Dict[str, Any]]:
        """Execute SQL and fetch one result (runs in thread) - thread-safe"""
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def _execute_sql_fetchall(self, sql: str, params: tuple) -> List[Dict[str, Any]]:
        """Execute SQL and fetch all results (runs in thread) - thread-safe"""
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists (runs in thread) - thread-safe"""
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table_name,)
            )
            return cursor.fetchone() is not None

    def _create_table_from_document(self, table_name: str, document: Dict[str, Any]) -> None:
        """
        Dynamically create a table based on the document structure (runs in thread)

        Args:
            table_name: Name of the table to create
            document: Sample document to infer schema from
        """
        columns = ['"id" TEXT PRIMARY KEY']

        for key, value in document.items():
            if key in ['_id', 'id']:
                continue

            quoted_key = f'"{key}"'

            if isinstance(value, bool):
                columns.append(f"{quoted_key} INTEGER")
            elif isinstance(value, int):
                columns.append(f"{quoted_key} INTEGER")
            elif isinstance(value, float):
                columns.append(f"{quoted_key} REAL")
            elif isinstance(value, (datetime, str)):
                columns.append(f"{quoted_key} TEXT")
            elif isinstance(value, (dict, list)):
                columns.append(f"{quoted_key} TEXT")
            else:
                columns.append(f"{quoted_key} TEXT")

        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(sql)
            if not self._in_transaction:
                self.connection.commit()

        logger.debug(f"Auto-created table: {table_name}")

    async def _ensure_table_exists(self, table_name: str, document: Dict[str, Any]) -> None:
        """Ensure a table exists, create it if not"""
        loop = asyncio.get_running_loop()

        exists = await loop.run_in_executor(
            self.executor,
            self._table_exists,
            table_name
        )

        if not exists:
            await loop.run_in_executor(
                self.executor,
                self._create_table_from_document,
                table_name,
                document
            )

            if table_name in self._pending_indexes:
                for index_def in self._pending_indexes[table_name]:
                    unique_str = "UNIQUE " if index_def['unique'] else ""
                    field_name = index_def['field_name']

                    if isinstance(field_name, list):
                        fields_str = ', '.join([f'"{f[0]}"' for f in field_name])
                    else:
                        fields_str = f'"{field_name}"'

                    index_sql = f"CREATE {unique_str}INDEX IF NOT EXISTS {index_def['name']} ON {table_name}({fields_str})"

                    await loop.run_in_executor(
                        self.executor,
                        self._execute_sql,
                        index_sql,
                        ()
                    )

                    logger.debug(f"Applied pending index {index_def['name']} on table {table_name}")

                del self._pending_indexes[table_name]

    def get_collection(self, collection_name: str):
        """
        Get a collection/table by name

        Args:
            collection_name: Name of the table

        Returns:
            The table name (for Postgres, we just return the name)
        """
        if not self._initialized:
            raise ValueError("Postgres Service not initialized. Call initialize() first.")

        return collection_name

    async def create_index(
        self,
        collection_name: str,
        field_name: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        sparse: bool = False,
        ttl_seconds: Optional[int] = None
    ) -> str:
        """
        Create an index on a table field

        Args:
            collection_name: Name of the table
            field_name: Field to index (string) or list of (field, direction) tuples
            unique: Whether the index should enforce uniqueness
            sparse: Whether the index should be sparse (not applicable to Postgres)
            ttl_seconds: TTL in seconds (not applicable to Postgres, ignored)

        Returns:
            Name of the created index
        """
        if not self._initialized:
            await self.initialize()

        async with self._operation_scope():
            loop = asyncio.get_running_loop()

            table_exists = await loop.run_in_executor(
                self.executor,
                self._table_exists,
                collection_name
            )

            if isinstance(field_name, list):
                field_str = '_'.join([f[0] for f in field_name])
            else:
                field_str = field_name
            index_name = f"idx_{collection_name}_{field_str}"

            if not table_exists:
                if collection_name not in self._pending_indexes:
                    self._pending_indexes[collection_name] = []

                self._pending_indexes[collection_name].append({
                    'name': index_name,
                    'field_name': field_name,
                    'unique': unique
                })

                logger.debug(f"Queued index {index_name} for table {collection_name} (will be created when table is created)")

                return index_name

            unique_str = "UNIQUE " if unique else ""

            if isinstance(field_name, list):
                fields_str = ', '.join([f'"{f[0]}"' for f in field_name])
            else:
                fields_str = f'"{field_name}"'

            index_sql = f"CREATE {unique_str}INDEX IF NOT EXISTS {index_name} ON {collection_name}({fields_str})"

            await loop.run_in_executor(
                self.executor,
                self._execute_sql,
                index_sql,
                ()
            )

            logger.debug(f"Created index on {collection_name}.{field_name}")

            return index_name

    def _convert_query_to_sql(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> Tuple[str, tuple]:
        """
        Convert MongoDB-style query to SQL WHERE clause

        Args:
            collection_name: Name of the table
            query: MongoDB-style query

        Returns:
            Tuple of (WHERE clause, parameters)
        """
        if not query:
            return "", ()

        conditions = []
        params = []

        for key, value in query.items():
            if key == '_id':
                conditions.append('"id" = %s')
                params.append(id_to_string(value))
            elif isinstance(value, dict):
                quoted_key = f'"{key}"'
                for op, op_value in value.items():
                    if op == '$lt':
                        conditions.append(f"{quoted_key} < %s")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$lte':
                        conditions.append(f"{quoted_key} <= %s")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$gt':
                        conditions.append(f"{quoted_key} > %s")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$gte':
                        conditions.append(f"{quoted_key} >= %s")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$ne':
                        conditions.append(f"{quoted_key} != %s")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$in':
                        placeholders = ','.join(['%s' for _ in op_value])
                        conditions.append(f"{quoted_key} IN ({placeholders})")
                        params.extend([self._convert_value_for_sql(v) for v in op_value])
                    elif op == '$regex':
                        # ILIKE preserves SQLite's default case-insensitive LIKE behavior
                        conditions.append(f"{quoted_key} ILIKE %s")
                        pattern = op_value.replace('.*', '%').replace('.', '_')
                        params.append(f"%{pattern}%")
            elif value is None:
                quoted_key = f'"{key}"'
                conditions.append(f"{quoted_key} IS NULL")
            else:
                quoted_key = f'"{key}"'
                conditions.append(f"{quoted_key} = %s")
                params.append(self._convert_value_for_sql(value))

        where_clause = " AND ".join(conditions)
        return where_clause, tuple(params)

    def _convert_value_for_sql(self, value: Any) -> Any:
        """Convert a value to SQL-compatible format"""
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, bool):
            return 1 if value else 0
        else:
            return id_to_string(value) if hasattr(value, '__str__') and not isinstance(value, (str, int, float)) else value

    def _convert_document_for_insert(
        self,
        collection_name: str,
        document: Dict[str, Any]
    ) -> Tuple[str, str, tuple]:
        """
        Convert a document for SQL INSERT

        Args:
            collection_name: Name of the table
            document: Document to insert

        Returns:
            Tuple of (columns, placeholders, values)
        """
        if '_id' not in document and 'id' not in document:
            document['id'] = generate_id('postgres')
        elif '_id' in document:
            document['id'] = id_to_string(document.pop('_id'))

        if collection_name == 'chat_history' and 'metadata' in document:
            metadata = document.pop('metadata')
            sanitized_metadata = _make_json_serializable(metadata)
            document['metadata_json'] = json.dumps(sanitized_metadata)

        for key, value in document.items():
            if isinstance(value, datetime):
                document[key] = value.isoformat()
            elif isinstance(value, bool):
                document[key] = 1 if value else 0

        columns = ', '.join([f'"{key}"' for key in document.keys()])
        placeholders = ', '.join(['%s' for _ in document.keys()])
        values = tuple(document.values())

        return columns, placeholders, values

    async def find_one(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find a single record in a table"""
        if not self._initialized:
            await self.initialize()

        try:
            where_clause, params = self._convert_query_to_sql(collection_name, query)

            if where_clause:
                sql = f"SELECT * FROM {collection_name} WHERE {where_clause} LIMIT 1"
            else:
                sql = f"SELECT * FROM {collection_name} LIMIT 1"

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._execute_sql_fetchone,
                sql,
                params
            )

            if result:
                return self._convert_row_to_document(collection_name, result)

            return None

        except Exception as e:
            logger.error(f"Error finding document in {collection_name}: {str(e)}")
            return None

    async def find_many(
        self,
        collection_name: str,
        query: Dict[str, Any],
        limit: int = 100,
        sort: Optional[List[Tuple[str, int]]] = None,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """Find multiple records in a table"""
        if not self._initialized:
            await self.initialize()

        try:
            where_clause, params = self._convert_query_to_sql(collection_name, query)

            sql = f"SELECT * FROM {collection_name}"

            if where_clause:
                sql += f" WHERE {where_clause}"

            if sort:
                order_parts = []
                for field, direction in sort:
                    order_parts.append(f'"{field}" {"ASC" if direction == 1 else "DESC"}')
                sql += f" ORDER BY {', '.join(order_parts)}"

            sql += f" LIMIT {limit} OFFSET {skip}"

            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                self.executor,
                self._execute_sql_fetchall,
                sql,
                params
            )

            return [self._convert_row_to_document(collection_name, row) for row in results]

        except Exception as e:
            logger.error(f"Error finding documents in {collection_name}: {str(e)}")
            return []

    async def insert_one(
        self,
        collection_name: str,
        document: Dict[str, Any]
    ) -> Optional[str]:
        """Insert a record into a table"""
        if not self._initialized:
            await self.initialize()

        import psycopg

        async with self._operation_scope():
            try:
                doc_copy = document.copy()

                await self._ensure_table_exists(collection_name, doc_copy)

                columns, placeholders, values = self._convert_document_for_insert(collection_name, doc_copy)

                sql = f"INSERT INTO {collection_name} ({columns}) VALUES ({placeholders})"

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    sql,
                    values
                )

                return doc_copy['id']

            except psycopg.errors.UniqueViolation as e:
                logger.warning(f"Duplicate key error inserting into {collection_name}: {str(e)}")
                self.connection.rollback()
                raise
            except Exception as e:
                logger.error(f"Error inserting document into {collection_name}: {str(e)}")
                try:
                    self.connection.rollback()
                except Exception:
                    pass
                return None

    async def update_one(
        self,
        collection_name: str,
        query: Dict[str, Any],
        update: Dict[str, Any]
    ) -> bool:
        """Update a record in a table"""
        if not self._initialized:
            await self.initialize()

        async with self._operation_scope():
            try:
                if '$set' not in update:
                    logger.warning(f"Update operation without $set: {update}")
                    return False

                set_data = update['$set']

                for key, value in set_data.items():
                    if isinstance(value, datetime):
                        set_data[key] = value.isoformat()
                    elif isinstance(value, bool):
                        set_data[key] = 1 if value else 0
                    elif hasattr(value, '__class__') and 'ObjectApiResponse' in value.__class__.__name__:
                        set_data[key] = _make_json_serializable(value)
                    elif isinstance(value, (dict, list)) and key == 'metadata_json':
                        set_data[key] = json.dumps(_make_json_serializable(value))

                set_parts = [f'"{key}" = %s' for key in set_data.keys()]
                set_clause = ', '.join(set_parts)
                set_values = list(set_data.values())

                where_clause, where_params = self._convert_query_to_sql(collection_name, query)

                if not where_clause:
                    logger.warning("Update operation without WHERE clause")
                    return False

                sql = f"UPDATE {collection_name} SET {set_clause} WHERE {where_clause}"
                params = tuple(set_values + list(where_params))

                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    sql,
                    params
                )

                return cursor.rowcount > 0

            except Exception as e:
                logger.error(f"Error updating document in {collection_name}: {str(e)}")
                return False

    async def delete_one(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> bool:
        """Delete a record from a table"""
        if not self._initialized:
            await self.initialize()

        async with self._operation_scope():
            try:
                where_clause, params = self._convert_query_to_sql(collection_name, query)

                if not where_clause:
                    logger.warning("Delete operation without WHERE clause")
                    return False

                # Postgres has no native "LIMIT 1" on DELETE; use ctid (the row's physical
                # location), the Postgres analogue of SQLite's rowid, to delete a single match.
                sql = f"""DELETE FROM {collection_name}
                         WHERE ctid = (SELECT ctid FROM {collection_name} WHERE {where_clause} LIMIT 1)"""

                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    sql,
                    params
                )

                return cursor.rowcount > 0

            except Exception as e:
                logger.error(f"Error deleting document from {collection_name}: {str(e)}")
                return False

    async def delete_many(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> int:
        """Delete multiple records from a table"""
        if not self._initialized:
            await self.initialize()

        async with self._operation_scope():
            try:
                where_clause, params = self._convert_query_to_sql(collection_name, query)

                if not where_clause:
                    logger.warning("Delete operation without WHERE clause")
                    return 0

                sql = f"DELETE FROM {collection_name} WHERE {where_clause}"

                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    sql,
                    params
                )

                return cursor.rowcount

            except Exception as e:
                logger.error(f"Error deleting documents from {collection_name}: {str(e)}")
                return 0

    async def count(self, collection_name: str, query: Dict[str, Any]) -> int:
        """Count records matching a query."""
        if not self._initialized:
            await self.initialize()

        try:
            where_clause, params = self._convert_query_to_sql(collection_name, query)

            sql = f"SELECT COUNT(*) as cnt FROM {collection_name}"
            if where_clause:
                sql += f" WHERE {where_clause}"

            loop = asyncio.get_running_loop()
            row = await loop.run_in_executor(
                self.executor,
                self._execute_sql_fetchone,
                sql,
                params
            )
            return row["cnt"] if row else 0

        except Exception as e:
            logger.error(f"Error counting records in {collection_name}: {str(e)}")
            return 0

    async def clear_collection(self, collection_name: str) -> int:
        """
        Delete ALL records from a table.

        This is an explicit method for clearing entire tables, bypassing
        the safety guard in delete_many that prevents deletion without WHERE clause.

        Args:
            collection_name: Name of the table to clear

        Returns:
            Number of records deleted
        """
        if not self._initialized:
            await self.initialize()

        async with self._operation_scope():
            try:
                sql = f"DELETE FROM {collection_name}"

                loop = asyncio.get_running_loop()
                cursor = await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    sql,
                    ()
                )

                deleted_count = cursor.rowcount
                logger.info(f"Cleared {deleted_count} records from table '{collection_name}'")
                return deleted_count

            except Exception as e:
                logger.error(f"Error clearing table {collection_name}: {str(e)}")
                return 0

    async def execute_transaction(
        self,
        operations: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """
        Execute operations within a PostgreSQL transaction.

        Uses the single shared connection (autocommit disabled), so the first statement
        implicitly opens a transaction. Commits on success, rolls back on failure.

        While the transaction is active, _execute_sql (used by insert_one/update_one/etc.)
        skips its usual per-statement commit so a rollback here actually undoes them. The
        operation lock is held for the whole transaction so a concurrent caller on this
        same service instance blocks until it completes, rather than being silently swept
        into it (nested calls from operations() itself - same asyncio task - pass through
        via _operation_scope()).

        Args:
            operations: Async function that performs operations

        Returns:
            Result of the operations
        """
        if not self._initialized:
            await self.initialize()

        loop = asyncio.get_running_loop()
        await self._operation_lock.acquire()
        self._in_transaction = True
        self._transaction_task = asyncio.current_task()
        try:
            result = await operations(None)
            await loop.run_in_executor(
                self.executor,
                self.connection.commit
            )
            return result
        except Exception:
            await loop.run_in_executor(
                self.executor,
                self.connection.rollback
            )
            raise
        finally:
            self._in_transaction = False
            self._transaction_task = None
            self._operation_lock.release()

    async def ensure_id_is_object_id(self, id_value: Union[str, Any]) -> str:
        """
        Ensure that an ID is in the correct format for Postgres (UUID string)

        Args:
            id_value: ID value, either as string or other type

        Returns:
            The ID as a string
        """
        return ensure_id(id_value, 'postgres')

    def _convert_row_to_document(
        self,
        collection_name: str,
        row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert a Postgres row to a document (MongoDB-style)

        Args:
            collection_name: Name of the table
            row: Postgres row

        Returns:
            Document with _id field
        """
        doc = dict(row)

        if 'id' in doc:
            doc['_id'] = doc.pop('id')

        if collection_name == 'chat_history' and 'metadata_json' in doc:
            if doc['metadata_json']:
                try:
                    doc['metadata'] = json.loads(doc['metadata_json'])
                except json.JSONDecodeError:
                    doc['metadata'] = {}
            doc.pop('metadata_json', None)

        datetime_fields = ['created_at', 'updated_at', 'last_login', 'expires', 'timestamp']
        for field in datetime_fields:
            if field in doc and doc[field]:
                try:
                    doc[field] = datetime.fromisoformat(doc[field])
                except (ValueError, TypeError):
                    pass

        bool_fields = ['active', 'verified', 'enabled', 'disabled', 'is_admin',
                       'is_active', 'is_verified', 'success', 'failed']
        for field in bool_fields:
            if field in doc and isinstance(doc[field], int) and doc[field] in (0, 1):
                doc[field] = True if doc[field] == 1 else False

        return doc

    def close(self) -> None:
        """Close the Postgres connection and shut down the executor"""
        if self.connection:
            self.connection.close()
            self.connection = None
            self._initialized = False
            self._collections = {}
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=False)
            self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix='postgres_')

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached Postgres service instances. Useful for testing or reloading."""
        with cls._lock:
            for instance in cls._instances.values():
                try:
                    if hasattr(instance, 'close'):
                        instance.close()
                except Exception as e:
                    logger.warning(f"Error closing Postgres instance: {e}")

            cls._instances.clear()
            logger.debug("Cleared all Postgres service instances from cache")

    @classmethod
    def get_cached_instances(cls) -> Dict[str, 'PostgresService']:
        """Get all currently cached Postgres service instances. Useful for debugging."""
        with cls._lock:
            return cls._instances.copy()

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached Postgres services."""
        with cls._lock:
            return {
                "total_cached_instances": len(cls._instances),
                "cached_connections": list(cls._instances.keys()),
                "memory_info": f"{len(cls._instances)} Postgres service instances cached"
            }
