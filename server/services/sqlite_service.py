"""
SQLite Service
==============

This service provides a SQLite-based database implementation that follows the
DatabaseService interface. It uses the standard sqlite3 library with a ThreadPoolExecutor
for async operations, providing compatibility with the existing async service architecture.

Implements singleton pattern to share SQLite connections across services.
"""

import sqlite3
import json
import logging
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List, Union, Tuple, Callable, Awaitable
from datetime import datetime
from pathlib import Path

from services.database_service import DatabaseService
from utils.id_utils import generate_id, ensure_id, id_to_string

logger = logging.getLogger(__name__)


def _make_json_serializable(obj: Any) -> Any:
    """
    Convert non-JSON-serializable objects to serializable format.

    Handles:
    - Elasticsearch ObjectApiResponse objects
    - datetime objects
    - Custom objects with __dict__
    - Other special types
    """
    # Handle Elasticsearch ObjectApiResponse
    if hasattr(obj, '__class__') and 'ObjectApiResponse' in obj.__class__.__name__:
        # Convert to dict or list based on structure
        if hasattr(obj, 'body'):
            return obj.body
        elif hasattr(obj, '__dict__'):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        else:
            return str(obj)

    # Handle datetime
    if isinstance(obj, datetime):
        return obj.isoformat()

    # Handle dict recursively
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}

    # Handle list/tuple recursively
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]

    # Handle objects with __dict__
    if hasattr(obj, '__dict__') and not isinstance(obj, type):
        return {k: _make_json_serializable(v) for k, v in obj.__dict__.items() if not k.startswith('_')}

    # Return as-is for basic types
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj

    # Last resort: convert to string
    return str(obj)


class SQLiteService(DatabaseService):
    """Service for handling SQLite database operations with singleton pattern"""

    _instances: Dict[str, 'SQLiteService'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any]):
        """
        Implement singleton pattern for SQLite service.
        Returns existing instance if configuration matches.
        """
        # Create cache key based on SQLite configuration
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                logger.debug(f"Creating new SQLite service instance for key: {cache_key}")
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
            else:
                logger.debug(f"Reusing cached SQLite service instance for key: {cache_key}")

            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        """Create a cache key based on SQLite configuration."""
        sqlite_config = config.get('internal_services', {}).get('backend', {}).get('sqlite', {})

        # Use database path to create unique key
        database_path = sqlite_config.get('database_path', 'orbit.db')

        return f"sqlite:{database_path}"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the SQLite service with configuration"""
        # Prevent re-initialization of singleton instances
        if hasattr(self, '_initialized') and self._initialized:
            return

        super().__init__(config)

        # Get SQLite configuration
        sqlite_config = config.get('internal_services', {}).get('backend', {}).get('sqlite', {})
        self.database_path = sqlite_config.get('database_path', 'orbit.db')

        # Initialize connection and executor
        self.connection = None
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix='sqlite_')
        self._collections = {}
        
        # Lock for thread-safe database operations (SQLite doesn't handle concurrent writes well)
        self._db_lock = threading.Lock()

        # Track pending indexes for tables that don't exist yet
        self._pending_indexes = {}

        # Schema definitions
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
                    system_prompt_id TEXT
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES uploaded_files(id)
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
            'uploaded_files': [
                'CREATE INDEX IF NOT EXISTS idx_uploaded_files_api_key ON uploaded_files(api_key)',
                'CREATE INDEX IF NOT EXISTS idx_uploaded_files_processing_status ON uploaded_files(processing_status)',
            ],
            'file_chunks': [
                'CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id ON file_chunks(file_id)',
            ],
        }

    async def initialize(self) -> None:
        """Initialize connection to SQLite database and create tables"""
        if self._initialized:
            return

        try:
            # Log SQLite configuration
            logger.debug(f"Initializing SQLite connection to: {self.database_path}")

            # Ensure parent directory exists
            db_path = Path(self.database_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Connect to SQLite database in a thread
            loop = asyncio.get_event_loop()
            self.connection = await loop.run_in_executor(
                self.executor,
                self._connect_db
            )

            # Create tables and indexes
            await self._create_tables()
            await self._create_indexes()

            logger.debug("SQLite Service initialized successfully")

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize SQLite Service: {str(e)}")
            raise

    def _connect_db(self) -> sqlite3.Connection:
        """Connect to SQLite database (runs in thread)"""
        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def _create_tables(self) -> None:
        """Create database tables"""
        loop = asyncio.get_event_loop()
        for table_name, schema in self._schema.items():
            await loop.run_in_executor(
                self.executor,
                self._execute_sql,
                schema,
                ()
            )
            logger.debug(f"Created table: {table_name}")

    async def _create_indexes(self) -> None:
        """Create database indexes"""
        loop = asyncio.get_event_loop()
        for table_name, indexes in self._indexes.items():
            for index_sql in indexes:
                await loop.run_in_executor(
                    self.executor,
                    self._execute_sql,
                    index_sql,
                    ()
                )

    def _execute_sql(self, sql: str, params: tuple) -> sqlite3.Cursor:
        """Execute SQL statement (runs in thread) - thread-safe"""
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
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
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
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
        # Base columns that all tables should have (use "id" not "_id")
        columns = ['"id" TEXT PRIMARY KEY']

        # Add columns based on document structure
        for key, value in document.items():
            if key in ['_id', 'id']:  # Skip ID fields as they're already added
                continue

            # Quote column names to handle reserved keywords
            quoted_key = f'"{key}"'

            # Infer SQL type from Python type
            if isinstance(value, bool):
                columns.append(f"{quoted_key} INTEGER")  # SQLite uses INTEGER for boolean
            elif isinstance(value, int):
                columns.append(f"{quoted_key} INTEGER")
            elif isinstance(value, float):
                columns.append(f"{quoted_key} REAL")
            elif isinstance(value, (datetime, str)):
                columns.append(f"{quoted_key} TEXT")  # Store datetime as ISO string
            elif isinstance(value, (dict, list)):
                columns.append(f"{quoted_key} TEXT")  # Store JSON as TEXT
            else:
                columns.append(f"{quoted_key} TEXT")  # Default to TEXT

        # Create the table
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)})"
        with self._db_lock:
            cursor = self.connection.cursor()
            cursor.execute(sql)
            self.connection.commit()

        logger.debug(f"Auto-created table: {table_name}")

    async def _ensure_table_exists(self, table_name: str, document: Dict[str, Any]) -> None:
        """Ensure a table exists, create it if not"""
        loop = asyncio.get_event_loop()

        # Check if table exists
        exists = await loop.run_in_executor(
            self.executor,
            self._table_exists,
            table_name
        )

        # Create table if it doesn't exist
        if not exists:
            await loop.run_in_executor(
                self.executor,
                self._create_table_from_document,
                table_name,
                document
            )

            # Apply any pending indexes for this table
            if table_name in self._pending_indexes:
                for index_def in self._pending_indexes[table_name]:
                    # Build index SQL
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

                # Clear pending indexes for this table
                del self._pending_indexes[table_name]

    def get_collection(self, collection_name: str):
        """
        Get a collection/table by name

        Args:
            collection_name: Name of the table

        Returns:
            The table name (for SQLite, we just return the name)
        """
        if not self._initialized:
            raise ValueError("SQLite Service not initialized. Call initialize() first.")

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
            sparse: Whether the index should be sparse (not applicable to SQLite)
            ttl_seconds: TTL in seconds (not applicable to SQLite, ignored)

        Returns:
            Name of the created index
        """
        if not self._initialized:
            await self.initialize()

        loop = asyncio.get_event_loop()

        # Check if table exists first
        table_exists = await loop.run_in_executor(
            self.executor,
            self._table_exists,
            collection_name
        )

        if not table_exists:
            # Table doesn't exist yet - store as pending index
            if collection_name not in self._pending_indexes:
                self._pending_indexes[collection_name] = []

            # Generate index name
            if isinstance(field_name, list):
                field_str = '_'.join([f[0] for f in field_name])
            else:
                field_str = field_name
            index_name = f"idx_{collection_name}_{field_str}"

            # Store index definition
            self._pending_indexes[collection_name].append({
                'name': index_name,
                'field_name': field_name,
                'unique': unique
            })

            logger.debug(f"Queued index {index_name} for table {collection_name} (will be created when table is created)")

            return index_name

        # Generate index name
        if isinstance(field_name, list):
            field_str = '_'.join([f[0] for f in field_name])
        else:
            field_str = field_name

        index_name = f"idx_{collection_name}_{field_str}"

        # Build index SQL (quote column names to handle reserved keywords)
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
                # Convert _id to id (quote to handle reserved keywords)
                conditions.append('"id" = ?')
                params.append(id_to_string(value))
            elif isinstance(value, dict):
                # Quote column name to handle reserved keywords
                quoted_key = f'"{key}"'
                # Handle operators
                for op, op_value in value.items():
                    if op == '$lt':
                        conditions.append(f"{quoted_key} < ?")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$lte':
                        conditions.append(f"{quoted_key} <= ?")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$gt':
                        conditions.append(f"{quoted_key} > ?")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$gte':
                        conditions.append(f"{quoted_key} >= ?")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$ne':
                        conditions.append(f"{quoted_key} != ?")
                        params.append(self._convert_value_for_sql(op_value))
                    elif op == '$in':
                        placeholders = ','.join(['?' for _ in op_value])
                        conditions.append(f"{quoted_key} IN ({placeholders})")
                        params.extend([self._convert_value_for_sql(v) for v in op_value])
                    elif op == '$regex':
                        conditions.append(f"{quoted_key} LIKE ?")
                        # Convert regex to SQL LIKE pattern
                        pattern = op_value.replace('.*', '%').replace('.', '_')
                        params.append(f"%{pattern}%")
            else:
                # Quote column name to handle reserved keywords
                quoted_key = f'"{key}"'
                # Simple equality
                conditions.append(f"{quoted_key} = ?")
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
        # Generate ID if not provided
        if '_id' not in document and 'id' not in document:
            document['id'] = generate_id('sqlite')
        elif '_id' in document:
            document['id'] = id_to_string(document.pop('_id'))

        # Handle metadata field for chat_history
        if collection_name == 'chat_history' and 'metadata' in document:
            # Sanitize metadata to handle non-serializable objects (e.g., Elasticsearch ObjectApiResponse)
            metadata = document.pop('metadata')
            sanitized_metadata = _make_json_serializable(metadata)
            document['metadata_json'] = json.dumps(sanitized_metadata)

        # Convert datetime objects to ISO strings
        for key, value in document.items():
            if isinstance(value, datetime):
                document[key] = value.isoformat()
            elif isinstance(value, bool):
                document[key] = 1 if value else 0

        # Quote column names to handle reserved keywords
        columns = ', '.join([f'"{key}"' for key in document.keys()])
        placeholders = ', '.join(['?' for _ in document.keys()])
        values = tuple(document.values())

        return columns, placeholders, values

    async def find_one(
        self,
        collection_name: str,
        query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single record in a table

        Args:
            collection_name: Name of the table
            query: Query criteria

        Returns:
            The record if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            where_clause, params = self._convert_query_to_sql(collection_name, query)

            if where_clause:
                sql = f"SELECT * FROM {collection_name} WHERE {where_clause} LIMIT 1"
            else:
                sql = f"SELECT * FROM {collection_name} LIMIT 1"

            loop = asyncio.get_event_loop()
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
        """
        Find multiple records in a table

        Args:
            collection_name: Name of the table
            query: Query criteria
            limit: Maximum number of records to return
            sort: List of (field, direction) tuples for sorting (1=asc, -1=desc)
            skip: Number of records to skip

        Returns:
            List of matching records
        """
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
                    # Quote column names to handle reserved keywords
                    order_parts.append(f'"{field}" {"ASC" if direction == 1 else "DESC"}')
                sql += f" ORDER BY {', '.join(order_parts)}"

            sql += f" LIMIT {limit} OFFSET {skip}"

            loop = asyncio.get_event_loop()
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
        """
        Insert a record into a table

        Args:
            collection_name: Name of the table
            document: Record to insert

        Returns:
            ID of the inserted record, or None if insertion failed
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Make a copy to avoid modifying the original
            doc_copy = document.copy()

            # Ensure table exists before inserting
            await self._ensure_table_exists(collection_name, doc_copy)

            columns, placeholders, values = self._convert_document_for_insert(collection_name, doc_copy)

            sql = f"INSERT INTO {collection_name} ({columns}) VALUES ({placeholders})"

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.executor,
                self._execute_sql,
                sql,
                values
            )

            # Return the generated ID
            return doc_copy['id']

        except sqlite3.IntegrityError as e:
            # Handle duplicate key errors
            if "UNIQUE constraint failed" in str(e):
                logger.warning(f"Duplicate key error inserting into {collection_name}: {str(e)}")
                raise  # Re-raise for deduplication handling
            logger.error(f"Integrity error inserting document into {collection_name}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inserting document into {collection_name}: {str(e)}")
            return None

    async def update_one(
        self,
        collection_name: str,
        query: Dict[str, Any],
        update: Dict[str, Any]
    ) -> bool:
        """
        Update a record in a table

        Args:
            collection_name: Name of the table
            query: Query criteria to find the record
            update: Update operation (MongoDB-style $set, etc.)

        Returns:
            True if a record was updated, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Extract $set operation
            if '$set' not in update:
                logger.warning(f"Update operation without $set: {update}")
                return False

            set_data = update['$set']

            # Convert datetime objects to ISO strings and sanitize complex objects
            for key, value in set_data.items():
                if isinstance(value, datetime):
                    set_data[key] = value.isoformat()
                elif isinstance(value, bool):
                    set_data[key] = 1 if value else 0
                # Sanitize complex objects (e.g., Elasticsearch ObjectApiResponse)
                elif hasattr(value, '__class__') and 'ObjectApiResponse' in value.__class__.__name__:
                    set_data[key] = _make_json_serializable(value)
                elif isinstance(value, (dict, list)) and key == 'metadata_json':
                    # If updating metadata_json, ensure it's serializable
                    set_data[key] = json.dumps(_make_json_serializable(value))

            # Build SET clause (quote column names to handle reserved keywords)
            set_parts = [f'"{key}" = ?' for key in set_data.keys()]
            set_clause = ', '.join(set_parts)
            set_values = list(set_data.values())

            # Build WHERE clause
            where_clause, where_params = self._convert_query_to_sql(collection_name, query)

            if not where_clause:
                logger.warning("Update operation without WHERE clause")
                return False

            sql = f"UPDATE {collection_name} SET {set_clause} WHERE {where_clause}"
            params = tuple(set_values + list(where_params))

            loop = asyncio.get_event_loop()
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
        """
        Delete a record from a table

        Args:
            collection_name: Name of the table
            query: Query criteria to find the record

        Returns:
            True if a record was deleted, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            where_clause, params = self._convert_query_to_sql(collection_name, query)

            if not where_clause:
                logger.warning("Delete operation without WHERE clause")
                return False

            # SQLite doesn't support LIMIT in DELETE without ORDER BY
            # Instead, use a subquery to find the first matching row
            sql = f"""DELETE FROM {collection_name}
                     WHERE rowid = (SELECT rowid FROM {collection_name} WHERE {where_clause} LIMIT 1)"""

            loop = asyncio.get_event_loop()
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
        """
        Delete multiple records from a table

        Args:
            collection_name: Name of the table
            query: Query criteria to find the records

        Returns:
            Number of records deleted
        """
        if not self._initialized:
            await self.initialize()

        try:
            where_clause, params = self._convert_query_to_sql(collection_name, query)

            if not where_clause:
                logger.warning("Delete operation without WHERE clause")
                return 0

            sql = f"DELETE FROM {collection_name} WHERE {where_clause}"

            loop = asyncio.get_event_loop()
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

    async def execute_transaction(
        self,
        operations: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """
        Execute operations within a transaction

        Args:
            operations: Async function that performs operations

        Returns:
            Result of the operations

        Note:
            For SQLite, transactions are implicit. We just execute the operations.
        """
        if not self._initialized:
            await self.initialize()

        # SQLite transactions are handled automatically
        # Just execute the operations
        return await operations(None)

    async def ensure_id_is_object_id(self, id_value: Union[str, Any]) -> str:
        """
        Ensure that an ID is in the correct format for SQLite (UUID string)

        Args:
            id_value: ID value, either as string or other type

        Returns:
            The ID as a string
        """
        return ensure_id(id_value, 'sqlite')

    def _convert_row_to_document(
        self,
        collection_name: str,
        row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert a SQLite row to a document (MongoDB-style)

        Args:
            collection_name: Name of the table
            row: SQLite row

        Returns:
            Document with _id field
        """
        doc = dict(row)

        # Convert 'id' to '_id'
        if 'id' in doc:
            doc['_id'] = doc.pop('id')

        # Convert metadata_json back to metadata
        if collection_name == 'chat_history' and 'metadata_json' in doc:
            if doc['metadata_json']:
                try:
                    doc['metadata'] = json.loads(doc['metadata_json'])
                except json.JSONDecodeError:
                    doc['metadata'] = {}
            doc.pop('metadata_json', None)

        # Convert ISO strings back to datetime objects where appropriate
        datetime_fields = ['created_at', 'updated_at', 'last_login', 'expires', 'timestamp']
        for field in datetime_fields:
            if field in doc and doc[field]:
                try:
                    doc[field] = datetime.fromisoformat(doc[field])
                except (ValueError, TypeError):
                    pass

        # Convert integer booleans back to booleans
        # Common boolean field names across the application
        bool_fields = ['active', 'verified', 'enabled', 'disabled', 'is_admin',
                       'is_active', 'is_verified', 'success', 'failed']
        for field in bool_fields:
            if field in doc and isinstance(doc[field], int) and doc[field] in (0, 1):
                # Convert to actual boolean (not just truthy/falsy)
                doc[field] = True if doc[field] == 1 else False

        return doc

    def close(self) -> None:
        """Close the SQLite connection"""
        if self.connection:
            self.connection.close()
            self._initialized = False
            self._collections = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached SQLite service instances. Useful for testing or reloading."""
        with cls._lock:
            # Close all cached instances
            for instance in cls._instances.values():
                try:
                    if hasattr(instance, 'close') and instance.connection:
                        instance.connection.close()
                except Exception as e:
                    logger.warning(f"Error closing SQLite connection: {e}")

            cls._instances.clear()
            logger.debug("Cleared all SQLite service instances from cache")

    @classmethod
    def get_cached_instances(cls) -> Dict[str, 'SQLiteService']:
        """Get all currently cached SQLite service instances. Useful for debugging."""
        with cls._lock:
            return cls._instances.copy()

    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached SQLite services."""
        with cls._lock:
            return {
                "total_cached_instances": len(cls._instances),
                "cached_connections": list(cls._instances.keys()),
                "memory_info": f"{len(cls._instances)} SQLite service instances cached"
            }
