"""
Filesystem Storage Backend

Local filesystem implementation of FileStorageBackend.
Stores files in organized directory structure with metadata sidecars.
"""

import logging
import json
import os
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List
from .base_storage import FileStorageBackend

logger = logging.getLogger(__name__)


class FilesystemStorage(FileStorageBackend):
    """
    Filesystem storage backend for local file storage.
    
    Directory structure:
    {storage_root}/
      {api_key}/
        {file_id}/
          {filename}          # Actual file
          {filename}.metadata.json  # Metadata sidecar
    """
    
    def __init__(self, storage_root: str = "./uploads"):
        """
        Initialize filesystem storage backend.
        
        Args:
            storage_root: Root directory for storing files
        """
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized FilesystemStorage at {self.storage_root}")
    
    def _get_file_path(self, key: str) -> Path:
        """Convert storage key to filesystem path."""
        return self.storage_root / key
    
    def _get_metadata_path(self, key: str) -> Path:
        """Get path to metadata sidecar file."""
        file_path = self._get_file_path(key)
        return file_path.parent / f"{file_path.name}.metadata.json"
    
    async def put_file(self, file_data: bytes, key: str, metadata: Dict[str, Any]) -> str:
        """
        Store a file with metadata atomically.
        
        Uses temp file + atomic move to ensure consistency.
        """
        file_path = self._get_file_path(key)
        metadata_path = self._get_metadata_path(key)
        
        # Create parent directory
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file first (atomic operation)
        with tempfile.NamedTemporaryFile(
            dir=file_path.parent,
            delete=False,
            prefix=file_path.name + "."
        ) as temp_file:
            temp_file.write(file_data)
            temp_file_path = Path(temp_file.name)
        
        try:
            # Atomically move temp file to final location
            temp_file_path.replace(file_path)
            
            # Write metadata sidecar
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            
            logger.debug(f"Stored file at {file_path} ({len(file_data)} bytes)")
            return key
            
        except Exception as e:
            # Clean up temp file on error
            if temp_file_path.exists():
                temp_file_path.unlink()
            logger.error(f"Error storing file {key}: {e}")
            raise
    
    async def get_file(self, key: str) -> bytes:
        """Retrieve file contents."""
        file_path = self._get_file_path(key)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        
        return file_path.read_bytes()
    
    async def delete_file(self, key: str) -> bool:
        """Delete file and metadata sidecar, and clean up empty directories."""
        file_path = self._get_file_path(key)
        metadata_path = self._get_metadata_path(key)
        
        deleted = False
        
        if file_path.exists():
            file_path.unlink()
            deleted = True
            logger.debug(f"Deleted file {file_path}")
        
        if metadata_path.exists():
            metadata_path.unlink()
            logger.debug(f"Deleted metadata {metadata_path}")
        
        # Clean up empty directories
        # Directory structure: {storage_root}/{api_key}/{file_id}/
        # After deleting file, remove empty {file_id} and {api_key} directories
        try:
            # Start from the file's parent directory (file_id level)
            current_dir = file_path.parent
            
            # Remove file_id directory if empty
            if current_dir.exists() and current_dir.is_dir():
                try:
                    # Check if directory is completely empty (no files, no subdirectories)
                    try:
                        remaining_items = list(current_dir.iterdir())
                        if not remaining_items:
                            # Directory is empty, safe to remove
                            current_dir.rmdir()
                            logger.debug(f"Removed empty directory {current_dir}")
                            
                            # Try to remove parent directory (api_key level) if empty
                            parent_dir = current_dir.parent
                            if parent_dir.exists() and parent_dir.is_dir():
                                try:
                                    remaining_items_in_parent = list(parent_dir.iterdir())
                                    if not remaining_items_in_parent:
                                        parent_dir.rmdir()
                                        logger.debug(f"Removed empty directory {parent_dir}")
                                except OSError as parent_err:
                                    # Directory not empty or can't be removed - that's okay
                                    logger.debug(f"Could not remove parent directory {parent_dir}: {parent_err}")
                                    pass
                        else:
                            # Directory has remaining items, don't remove
                            logger.debug(f"Directory {current_dir} not empty, contains {len(remaining_items)} item(s)")
                    except OSError as iter_err:
                        # Can't read directory - skip cleanup
                        logger.debug(f"Could not read directory {current_dir}: {iter_err}")
                        pass
                except OSError as rmdir_err:
                    # Directory not empty or can't be removed - that's okay
                    logger.debug(f"Could not remove directory {current_dir}: {rmdir_err}")
                    pass
        except Exception as e:
            # Log but don't fail deletion if directory cleanup fails
            logger.debug(f"Could not clean up empty directories for {key}: {e}")
        
        return deleted
    
    async def list_files(self, prefix: str) -> List[str]:
        """List files with given prefix."""
        prefix_path = self._get_file_path(prefix)
        
        if not prefix_path.exists():
            return []
        
        files = []
        for file_path in prefix_path.rglob("*"):
            # Skip metadata files and directories
            if file_path.is_file() and not file_path.name.endswith(".metadata.json"):
                # Convert back to storage key format
                relative_path = file_path.relative_to(self.storage_root)
                files.append(str(relative_path).replace(os.sep, "/"))
        
        logger.debug(f"Listed {len(files)} files with prefix {prefix}")
        return files
    
    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from sidecar."""
        metadata_path = self._get_metadata_path(key)
        
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found for: {key}")
        
        with open(metadata_path, 'r') as f:
            return json.load(f)
    
    async def file_exists(self, key: str) -> bool:
        """Check if file exists."""
        file_path = self._get_file_path(key)
        return file_path.exists()
    
    async def get_file_size(self, key: str) -> int:
        """Get file size in bytes."""
        file_path = self._get_file_path(key)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        
        return file_path.stat().st_size
