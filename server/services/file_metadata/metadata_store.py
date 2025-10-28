"""
File Metadata Store

Manages metadata for uploaded files and their processing status.
Uses SQLite (orbit.db) for persistence.
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
    
    def __init__(self, db_path: str = "orbit.db"):
        """
        Initialize metadata store.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.connection = None
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        self.connection = sqlite3.connect(self.db_path)
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
        
        self.connection.commit()
        logger.info(f"Initialized FileMetadataStore at {self.db_path}")
    
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
            import datetime
            timestamp = datetime.datetime.utcnow().isoformat()
            
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
        collection_name: str = None
    ) -> bool:
        """
        Update file processing status.
        
        Args:
            file_id: File identifier
            status: New status ('pending', 'processing', 'completed', 'failed')
            chunk_count: Number of chunks created
            vector_store: Vector store used
            collection_name: Collection name
            
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
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM uploaded_files WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
        
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
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
    
    async def delete_file(self, file_id: str) -> bool:
        """
        Delete file and all associated chunks.
        
        Args:
            file_id: File identifier
            
        Returns:
            True if successful
        """
        try:
            cursor = self.connection.cursor()
            
            # Delete chunks first
            cursor.execute("DELETE FROM file_chunks WHERE file_id = ?", (file_id,))
            
            # Delete file
            cursor.execute("DELETE FROM uploaded_files WHERE file_id = ?", (file_id,))
            
            self.connection.commit()
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
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
