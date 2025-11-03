"""
File Metadata Store

Manages metadata for uploaded files and their processing status.
Uses SQLite (files.db by default, configurable via config.yaml) for persistence.
"""

import logging
import json
import sqlite3
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FileMetadataStore:
    """
    SQLite-based metadata store for file uploads and chunks.
    
    Tracks:
    - Uploaded files metadata
    - Processing status
    - Chunk references
    - Vector store mappings
    """
    
    def __init__(self, db_path: str = None, config: Dict[str, Any] = None):
        """
        Initialize metadata store.

        Args:
            db_path: Path to SQLite database (optional, will use config if not provided)
            config: Configuration dictionary (optional, used to get db_path if not provided)
        """
        # Get db_path from config if not provided
        if db_path is None:
            if config:
                db_path = config.get('files', {}).get('metadata_db_path', 'files.db')
            else:
                # Fallback to loading config if not provided
                try:
                    from config.config_manager import load_config
                    config = load_config()
                    db_path = config.get('files', {}).get('metadata_db_path', 'files.db')
                except Exception:
                    db_path = 'files.db'

        # Get verbose setting from config
        if config:
            self.verbose = config.get('general', {}).get('verbose', False)
        else:
            try:
                from config.config_manager import load_config
                loaded_config = load_config()
                self.verbose = loaded_config.get('general', {}).get('verbose', False)
            except Exception:
                self.verbose = False

        self.db_path = db_path
        self.connection = None
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        # Allow cross-thread usage since FastAPI uses async/await with multiple threads
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        
        cursor = self.connection.cursor()
        
        # Create uploaded_files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_files (
                file_id TEXT PRIMARY KEY,
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
                metadata TEXT,
                embedding_provider TEXT,
                embedding_dimensions INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create file_chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_chunks (
                chunk_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                chunk_index INTEGER,
                vector_store_id TEXT,
                collection_name TEXT,
                chunk_metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES uploaded_files(file_id)
            )
        """)
        
        # Create index on file_id for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id 
            ON file_chunks(file_id)
        """)
        
        # Create index on api_key for filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_uploaded_files_api_key
            ON uploaded_files(api_key)
        """)

        # Run migrations to add new columns if they don't exist
        self._run_migrations(cursor)

        self.connection.commit()
        if self.verbose:
            logger.info(f"Initialized FileMetadataStore at {self.db_path}")

    def _run_migrations(self, cursor):
        """Run database migrations to add new columns if they don't exist."""
        try:
            # Check if embedding_provider column exists
            cursor.execute("PRAGMA table_info(uploaded_files)")
            columns = [row[1] for row in cursor.fetchall()]

            # Add embedding_provider column if it doesn't exist
            if 'embedding_provider' not in columns:
                logger.info("Adding 'embedding_provider' column to uploaded_files table")
                cursor.execute("""
                    ALTER TABLE uploaded_files
                    ADD COLUMN embedding_provider TEXT
                """)

            # Add embedding_dimensions column if it doesn't exist
            if 'embedding_dimensions' not in columns:
                logger.info("Adding 'embedding_dimensions' column to uploaded_files table")
                cursor.execute("""
                    ALTER TABLE uploaded_files
                    ADD COLUMN embedding_dimensions INTEGER
                """)

            if self.verbose:
                logger.info("Database migrations completed successfully")

        except Exception as e:
            logger.error(f"Error running database migrations: {e}")
            # Don't fail initialization if migrations fail
            pass
    
    async def record_file_upload(
        self,
        file_id: str,
        api_key: str,
        filename: str,
        mime_type: str,
        file_size: int,
        storage_key: str,
        storage_type: str = 'vector',
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Record a new file upload.
        
        Args:
            file_id: Unique file identifier
            api_key: API key of uploader
            filename: Original filename
            mime_type: MIME type
            file_size: File size in bytes
            storage_key: Storage backend key
            storage_type: 'vector' or 'duckdb'
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
        try:
            from datetime import datetime, UTC
            timestamp = datetime.now(UTC).isoformat()
            
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO uploaded_files 
                (file_id, api_key, filename, mime_type, file_size, 
                 upload_timestamp, processing_status, storage_key, storage_type, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,
                api_key,
                filename,
                mime_type,
                file_size,
                timestamp,
                'pending',
                storage_key,
                storage_type,
                json.dumps(metadata or {}),
            ))
            
            self.connection.commit()
            logger.debug(f"Recorded file upload: {file_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error recording file upload: {e}")
            return False
    
    async def update_processing_status(
        self,
        file_id: str,
        status: str,
        chunk_count: int = None,
        vector_store: str = None,
        collection_name: str = None,
        embedding_provider: str = None,
        embedding_dimensions: int = None
    ) -> bool:
        """
        Update file processing status.

        Args:
            file_id: File identifier
            status: New status ('pending', 'processing', 'completed', 'failed')
            chunk_count: Number of chunks created
            vector_store: Vector store used
            collection_name: Collection name
            embedding_provider: Embedding provider used (e.g., 'openai', 'ollama')
            embedding_dimensions: Embedding vector dimensions (e.g., 768, 1536)

        Returns:
            True if successful
        """
        try:
            cursor = self.connection.cursor()

            updates = ['processing_status = ?']
            params = [status]

            if chunk_count is not None:
                updates.append('chunk_count = ?')
                params.append(chunk_count)

            if vector_store:
                updates.append('vector_store = ?')
                params.append(vector_store)

            if collection_name:
                updates.append('collection_name = ?')
                params.append(collection_name)

            if embedding_provider:
                updates.append('embedding_provider = ?')
                params.append(embedding_provider)

            if embedding_dimensions is not None:
                updates.append('embedding_dimensions = ?')
                params.append(embedding_dimensions)

            params.append(file_id)

            cursor.execute(f"""
                UPDATE uploaded_files
                SET {', '.join(updates)}
                WHERE file_id = ?
            """, params)

            self.connection.commit()
            logger.debug(f"Updated file {file_id} status to {status}")
            return True
        
        except Exception as e:
            logger.error(f"Error updating processing status: {e}")
            return False
    
    async def record_chunk(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        vector_store_id: str = None,
        collection_name: str = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Record a file chunk.
        
        Args:
            chunk_id: Unique chunk identifier
            file_id: Source file identifier
            chunk_index: Chunk position in file
            vector_store_id: Vector store entry ID
            collection_name: Collection name
            metadata: Chunk metadata
            
        Returns:
            True if successful
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO file_chunks 
                (chunk_id, file_id, chunk_index, vector_store_id, collection_name, chunk_metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                chunk_id,
                file_id,
                chunk_index,
                vector_store_id,
                collection_name,
                json.dumps(metadata or {}),
            ))
            
            self.connection.commit()
            logger.debug(f"Recorded chunk {chunk_id} for file {file_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error recording chunk: {e}")
            return False
    
    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file information.
        
        Args:
            file_id: File identifier
            
        Returns:
            File metadata dictionary or None
        """
        try:
            # Ensure connection is available (may need to reconnect if closed)
            if not self.connection:
                self._init_schema()
            
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM uploaded_files WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            
            if row:
                file_info = dict(row)
                # Ensure file_size is an integer (handle None case)
                if file_info.get('file_size') is None:
                    file_info['file_size'] = 0
                return file_info
            return None
        
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            # Try to reconnect on error
            try:
                self._init_schema()
            except:
                pass
            return None
    
    async def list_files(self, api_key: str) -> List[Dict[str, Any]]:
        """
        List all files for an API key.
        
        Args:
            api_key: API key to filter by
            
        Returns:
            List of file metadata dictionaries
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT * FROM uploaded_files 
                WHERE api_key = ? 
                ORDER BY upload_timestamp DESC
            """, (api_key,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    async def delete_file(self, file_id: str, skip_chunks: bool = False) -> bool:
        """
        Delete file and all associated chunks.
        
        Args:
            file_id: File identifier
            skip_chunks: If True, skip deleting chunks (useful if already deleted)
            
        Returns:
            True if successful
        """
        try:
            cursor = self.connection.cursor()
            
            # Delete chunks first (unless already deleted)
            if not skip_chunks:
                cursor.execute("DELETE FROM file_chunks WHERE file_id = ?", (file_id,))
            
            # Delete file
            cursor.execute("DELETE FROM uploaded_files WHERE file_id = ?", (file_id,))

            self.connection.commit()
            if self.verbose:
                logger.info(f"Deleted file {file_id} and chunks")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False
    
    async def get_file_chunks(self, file_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a file.
        
        Args:
            file_id: File identifier
            
        Returns:
            List of chunk metadata dictionaries
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT * FROM file_chunks 
                WHERE file_id = ? 
                ORDER BY chunk_index
            """, (file_id,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Error getting file chunks: {e}")
            return []
    
    async def get_chunk_info(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get chunk information by chunk_id.
        
        Args:
            chunk_id: Chunk identifier
            
        Returns:
            Chunk metadata dictionary or None
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM file_chunks WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            
            if row:
                chunk_info = dict(row)
                # Parse JSON metadata if present
                if 'chunk_metadata' in chunk_info and chunk_info['chunk_metadata']:
                    try:
                        chunk_info['chunk_metadata'] = json.loads(chunk_info['chunk_metadata'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                return chunk_info
            return None
        
        except Exception as e:
            logger.error(f"Error getting chunk info: {e}")
            return None
    
    async def delete_file_chunks(self, file_id: str) -> bool:
        """
        Delete all chunks for a file.
        
        Args:
            file_id: File identifier
            
        Returns:
            True if successful
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM file_chunks WHERE file_id = ?", (file_id,))
            self.connection.commit()
            logger.debug(f"Deleted chunks for file {file_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting file chunks: {e}")
            return False
    
    async def vacuum(self) -> bool:
        """
        Reclaim space in SQLite database after deletions.
        
        VACUUM rebuilds the database file, reclaiming space occupied by deleted records.
        This should be called periodically after bulk deletions to prevent database file growth.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("VACUUM")
            self.connection.commit()
            logger.info(f"Vacuumed database {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"Error vacuuming database: {e}")
            return False
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the database.
        
        Returns:
            Dictionary with database statistics including size and record counts
        """
        try:
            import os
            stats = {}
            
            # Get database file size
            if os.path.exists(self.db_path):
                stats['file_size_bytes'] = os.path.getsize(self.db_path)
                stats['file_size_mb'] = round(stats['file_size_bytes'] / (1024 * 1024), 2)
            
            cursor = self.connection.cursor()
            
            # Count files
            cursor.execute("SELECT COUNT(*) FROM uploaded_files")
            stats['file_count'] = cursor.fetchone()[0]
            
            # Count chunks
            cursor.execute("SELECT COUNT(*) FROM file_chunks")
            stats['chunk_count'] = cursor.fetchone()[0]
            
            # Get database page info
            cursor.execute("PRAGMA page_count")
            stats['page_count'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA page_size")
            stats['page_size'] = cursor.fetchone()[0]
            
            # Calculate used space
            stats['estimated_used_bytes'] = stats['page_count'] * stats['page_size']
            
            # Get free pages (space that can be reclaimed with VACUUM)
            cursor.execute("PRAGMA freelist_count")
            stats['free_pages'] = cursor.fetchone()[0]
            stats['estimated_free_bytes'] = stats['free_pages'] * stats['page_size']
            
            return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
