"""
File Management API Routes

Provides endpoints for uploading, querying, and managing files.
"""

import logging
import mimetypes
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime

from services.file_processing.file_processing_service import FileProcessingService
from services.file_storage.filesystem_storage import FilesystemStorage
from services.file_metadata.metadata_store import FileMetadataStore
from retrievers.implementations.file.file_retriever import FileVectorRetriever

logger = logging.getLogger(__name__)


def get_processing_service(request: Request) -> FileProcessingService:
    """
    Get file processing service from app state.
    
    Args:
        request: The incoming request
        
    Returns:
        FileProcessingService instance
        
    Raises:
        HTTPException: If service is not available
    """
    processing_service = getattr(request.app.state, 'file_processing_service', None)
    if not processing_service:
        raise HTTPException(status_code=503, detail="File processing service not available")
    return processing_service


# Request/Response Models
class UploadResponse(BaseModel):
    """Response model for file upload."""
    file_id: str
    filename: str
    mime_type: str
    file_size: int
    status: str
    chunk_count: int
    message: str


class FileInfoResponse(BaseModel):
    """Response model for file info."""
    file_id: str
    filename: str
    mime_type: str
    file_size: int
    upload_timestamp: str
    processing_status: str
    chunk_count: int
    storage_type: str


class QueryRequest(BaseModel):
    """Request model for file query."""
    query: str
    max_results: Optional[int] = 10


class QueryResponse(BaseModel):
    """Response model for query results."""
    file_id: str
    filename: str
    results: List[Dict[str, Any]]


def create_file_router() -> APIRouter:
    """
    Create file management router with all endpoints.
    
    Returns:
        APIRouter configured with file management endpoints
    """
    router = APIRouter(tags=["files"])
    
    @router.post("/api/files/upload", response_model=UploadResponse)
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        processing_service: FileProcessingService = Depends(get_processing_service)
    ):
        """
        Upload and process a file.
        
        Supports multiple file formats: PDF, DOCX, TXT, CSV, JSON, HTML, Markdown.
        
        Args:
            file: The uploaded file
            request: The incoming request
            x_api_key: API key for authentication
            processing_service: File processing service
            
        Returns:
            Upload response with file_id and processing status
            
        Raises:
            HTTPException: If upload or processing fails
        """
        try:
            # Validate API key
            if not x_api_key:
                raise HTTPException(status_code=401, detail="API key required")
            
            # Validate API key against API key service if available
            api_key_service = getattr(request.app.state, 'api_key_service', None)
            if api_key_service:
                try:
                    is_valid, _, _ = await api_key_service.validate_api_key(x_api_key)
                    if not is_valid:
                        logger.warning(f"Invalid API key attempted for file upload: {x_api_key[:8]}...")
                        raise HTTPException(status_code=401, detail="Invalid API key")
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error validating API key: {e}")
                    raise HTTPException(status_code=401, detail="API key validation failed")
            
            # Read file data
            file_data = await file.read()
            
            # Determine MIME type
            # First try the provided content_type
            mime_type = file.content_type
            
            # If content_type is missing or generic, try to detect from filename
            if not mime_type or mime_type == 'application/octet-stream':
                if file.filename:
                    guessed_type, _ = mimetypes.guess_type(file.filename)
                    if guessed_type:
                        mime_type = guessed_type
                    else:
                        # Fallback for common file extensions
                        ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
                        extension_map = {
                            'md': 'text/markdown',
                            'txt': 'text/plain',
                            'csv': 'text/csv',
                            'json': 'application/json',
                            'html': 'text/html',
                            'htm': 'text/html',
                            'pdf': 'application/pdf',
                            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            'doc': 'application/msword',
                        }
                        mime_type = extension_map.get(ext, 'application/octet-stream')
                else:
                    mime_type = 'application/octet-stream'
            
            # Log MIME type detection for debugging
            if mime_type == 'application/octet-stream':
                logger.warning(f"Could not determine MIME type for file: {file.filename}")
            
            # Process file
            result = await processing_service.process_file(
                file_data=file_data,
                filename=file.filename,
                mime_type=mime_type,
                api_key=x_api_key
            )
            
            logger.info(f"File uploaded successfully: {result['file_id']}")
            
            return UploadResponse(
                file_id=result['file_id'],
                filename=result['filename'],
                mime_type=result['mime_type'],
                file_size=result['file_size'],
                status=result['status'],
                chunk_count=result['chunk_count'],
                message="File uploaded and processed successfully"
            )
        
        except HTTPException:
            # Re-raise HTTP exceptions (like 401 for invalid API key)
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")
    
    
    @router.get("/api/files/{file_id}", response_model=FileInfoResponse)
    async def get_file_info(
        file_id: str,
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        processing_service: FileProcessingService = Depends(get_processing_service)
    ):
        """
        Get file metadata and processing status.
        
        Args:
            file_id: File identifier
            x_api_key: API key for authentication
            processing_service: File processing service
            
        Returns:
            File information
            
        Raises:
            HTTPException: If file not found or access denied
        """
        try:
            if not x_api_key:
                raise HTTPException(status_code=401, detail="API key required")
            
            # Get file metadata
            config = getattr(request.app.state, 'config', None)
            metadata_store = FileMetadataStore(config=config)
            
            file_info = await metadata_store.get_file_info(file_id)
            
            if not file_info:
                raise HTTPException(status_code=404, detail="File not found")
            
            # Check API key matches
            if file_info['api_key'] != x_api_key:
                raise HTTPException(status_code=403, detail="Access denied")
            
            return FileInfoResponse(
                file_id=file_info['file_id'],
                filename=file_info['filename'],
                mime_type=file_info['mime_type'],
                file_size=file_info['file_size'],
                upload_timestamp=file_info['upload_timestamp'],
                processing_status=file_info['processing_status'],
                chunk_count=file_info['chunk_count'],
                storage_type=file_info['storage_type']
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            raise HTTPException(status_code=500, detail=f"Error retrieving file info: {str(e)}")
    
    
    @router.get("/api/files", response_model=List[FileInfoResponse])
    async def list_files(
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        processing_service: FileProcessingService = Depends(get_processing_service)
    ):
        """
        List all files for an API key.
        
        Args:
            x_api_key: API key for authentication
            processing_service: File processing service
            
        Returns:
            List of file information
            
        Raises:
            HTTPException: If API key is invalid
        """
        try:
            if not x_api_key:
                raise HTTPException(status_code=401, detail="API key required")
            
            # Get config from request
            config = getattr(request.app.state, 'config', None) if 'request' in locals() else None
            if config is None:
                try:
                    from config.config_manager import load_config
                    config = load_config()
                except Exception:
                    config = None
            metadata_store = FileMetadataStore(config=config)
            
            files = await metadata_store.list_files(x_api_key)
            
            return [
                FileInfoResponse(
                    file_id=file['file_id'],
                    filename=file['filename'],
                    mime_type=file['mime_type'],
                    file_size=file['file_size'],
                    upload_timestamp=file['upload_timestamp'],
                    processing_status=file['processing_status'],
                    chunk_count=file['chunk_count'],
                    storage_type=file['storage_type']
                )
                for file in files
            ]
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")
    
    
    @router.delete("/api/files")
    async def delete_all_files(
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        processing_service: FileProcessingService = Depends(get_processing_service)
    ):
        """
        Delete all files for an API key.
        
        Args:
            x_api_key: API key for authentication
            processing_service: File processing service
            
        Returns:
            Success message with count of deleted files
        """
        try:
            if not x_api_key:
                raise HTTPException(status_code=401, detail="API key required")
            
            # Get config from request
            config = getattr(request.app.state, 'config', None)
            if config is None:
                try:
                    from config.config_manager import load_config
                    config = load_config()
                except Exception:
                    config = None
            metadata_store = FileMetadataStore(config=config)
            
            # List all files for this API key
            files = await metadata_store.list_files(x_api_key)
            
            # Delete each file
            deleted_count = 0
            errors = []
            
            for file in files:
                try:
                    success = await processing_service.delete_file(file['file_id'], x_api_key)
                    if success:
                        deleted_count += 1
                    else:
                        errors.append(file['file_id'])
                except Exception as e:
                    logger.error(f"Error deleting file {file['file_id']}: {e}")
                    errors.append(file['file_id'])
            
            logger.info(f"Deleted {deleted_count} files for API key {x_api_key}")
            
            return JSONResponse(
                content={
                    "message": f"Deleted {deleted_count} file(s)",
                    "deleted_count": deleted_count,
                    "errors": errors if errors else None
                }
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting all files: {e}")
            raise HTTPException(status_code=500, detail=f"Error deleting all files: {str(e)}")
    
    
    @router.delete("/api/files/{file_id}")
    async def delete_file(
        file_id: str,
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        processing_service: FileProcessingService = Depends(get_processing_service)
    ):
        """
        Delete a file and all associated chunks.
        
        Args:
            file_id: File identifier
            x_api_key: API key for authentication
            processing_service: File processing service
            
        Returns:
            Success message
            
        Raises:
            HTTPException: If file not found or access denied
        """
        try:
            if not x_api_key:
                raise HTTPException(status_code=401, detail="API key required")
            
            # Check file exists and API key matches
            # Get config from request
            config = getattr(request.app.state, 'config', None)
            metadata_store = FileMetadataStore(config=config)
            
            file_info = await metadata_store.get_file_info(file_id)
            if not file_info:
                raise HTTPException(status_code=404, detail="File not found")
            
            if file_info['api_key'] != x_api_key:
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Delete file
            success = await processing_service.delete_file(file_id, x_api_key)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete file")
            
            logger.info(f"File deleted: {file_id}")
            
            return JSONResponse(
                content={"message": "File deleted successfully", "file_id": file_id}
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")
    
    
    @router.post("/api/files/{file_id}/query", response_model=QueryResponse)
    async def query_file(
        file_id: str,
        query_request: QueryRequest,
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        processing_service: FileProcessingService = Depends(get_processing_service)
    ):
        """
        Query a specific file using semantic search.
        
        Args:
            file_id: File identifier
            query_request: Query request with search text
            x_api_key: API key for authentication
            processing_service: File processing service
            
        Returns:
            Query results from file content
            
        Raises:
            HTTPException: If file not found or query fails
        """
        try:
            if not x_api_key:
                raise HTTPException(status_code=401, detail="API key required")
            
            # Get file info
            # Get config from request
            config = getattr(request.app.state, 'config', None)
            metadata_store = FileMetadataStore(config=config)
            
            file_info = await metadata_store.get_file_info(file_id)
            if not file_info:
                raise HTTPException(status_code=404, detail="File not found")
            
            if file_info['api_key'] != x_api_key:
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Initialize retriever and query
            from retrievers.implementations.file.file_retriever import FileVectorRetriever
            
            retriever = FileVectorRetriever(config=config)
            await retriever.initialize()
            
            # Get collection name from file info
            collection_name = file_info.get('collection_name')
            if not collection_name:
                raise HTTPException(
                    status_code=400,
                    detail="File not indexed in vector store. Please re-upload the file."
                )
            
            # Query the vector store
            max_results = query_request.max_results or 10
            results = await retriever.get_relevant_context(
                query=query_request.query,
                api_key=x_api_key,
                file_id=file_id,
                collection_name=collection_name,
                limit=max_results
            )
            
            # Results are already formatted by FileVectorRetriever._format_results()
            # They have the structure: {'content': '...', 'metadata': {'chunk_id': '...', ...}}
            # Just ensure file_id is set correctly in metadata
            for result in results:
                if 'metadata' in result:
                    result['metadata']['file_id'] = result['metadata'].get('file_id', file_id)
            
            return QueryResponse(
                file_id=file_id,
                filename=file_info['filename'],
                results=results  # Already formatted correctly
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error querying file: {e}")
            raise HTTPException(status_code=500, detail=f"Error querying file: {str(e)}")
    
    return router

