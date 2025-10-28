"""
File Management API Routes

Provides endpoints for uploading, querying, and managing files.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime

from services.file_processing.file_processing_service import FileProcessingService
from services.file_processing.file_processing_service import FileProcessingService as ProcessingService
from services.file_storage.filesystem_storage import FilesystemStorage
from services.file_metadata.metadata_store import FileMetadataStore
from retrievers.implementations.file.file_retriever import FileVectorRetriever

logger = logging.getLogger(__name__)

# Create router
files_router = APIRouter(tags=["files"])

# Global services (will be initialized in configure_files_routes)
_processing_service: Optional[FileProcessingService] = None
_retriever: Optional[FileVectorRetriever] = None


def configure_files_routes(app_config: Dict[str, Any]):
    """
    Configure file routes and initialize services.
    
    Args:
        app_config: Application configuration
    """
    global _processing_service, _retriever
    
    # Initialize processing service
    file_config = {
        'storage_root': app_config.get('file_storage', {}).get('root', './uploads'),
        'chunking_strategy': app_config.get('file_storage', {}).get('chunking_strategy', 'semantic'),
        'chunk_size': app_config.get('file_storage', {}).get('chunk_size', 1000),
        'chunk_overlap': app_config.get('file_storage', {}).get('chunk_overlap', 200),
        'max_file_size': app_config.get('file_storage', {}).get('max_file_size', 52428800),
        'supported_types': app_config.get('file_storage', {}).get('supported_types', [
            'application/pdf',
            'text/plain',
            'text/markdown',
            'text/csv',
            'application/json',
            'text/html',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        ]),
    }
    
    _processing_service = FileProcessingService(file_config)
    logger.info("File routes configured")


async def get_processing_service() -> FileProcessingService:
    """Get file processing service."""
    if _processing_service is None:
        raise HTTPException(status_code=500, detail="File service not initialized")
    return _processing_service


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


# API Endpoints

@files_router.post("/api/files/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    processing_service: FileProcessingService = Depends(get_processing_service)
):
    """
    Upload and process a file.
    
    Supports multiple file formats: PDF, DOCX, TXT, CSV, JSON, HTML, Markdown.
    
    Args:
        file: The uploaded file
        x_api_key: API key for authentication
        processing_service: File processing service
        
    Returns:
        Upload response with file_id and processing status
        
    Raises:
        HTTPException: If upload or processing fails
    """
    try:
        # Validate API key (simple for now)
        if not x_api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # Read file data
        file_data = await file.read()
        
        # Determine MIME type
        mime_type = file.content_type or 'application/octet-stream'
        
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
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


@files_router.get("/api/files/{file_id}", response_model=FileInfoResponse)
async def get_file_info(
    file_id: str,
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
        from services.file_metadata.metadata_store import FileMetadataStore
        metadata_store = FileMetadataStore()
        
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


@files_router.get("/api/files", response_model=List[FileInfoResponse])
async def list_files(
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
        
        from services.file_metadata.metadata_store import FileMetadataStore
        metadata_store = FileMetadataStore()
        
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


@files_router.delete("/api/files/{file_id}")
async def delete_file(
    file_id: str,
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
        from services.file_metadata.metadata_store import FileMetadataStore
        metadata_store = FileMetadataStore()
        
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


@files_router.post("/api/files/{file_id}/query", response_model=QueryResponse)
async def query_file(
    file_id: str,
    query_request: QueryRequest,
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
        from services.file_metadata.metadata_store import FileMetadataStore
        metadata_store = FileMetadataStore()
        
        file_info = await metadata_store.get_file_info(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        if file_info['api_key'] != x_api_key:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # TODO: Initialize retriever and query
        # For now, return placeholder
        return QueryResponse(
            file_id=file_id,
            filename=file_info['filename'],
            results=[]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying file: {e}")
        raise HTTPException(status_code=500, detail=f"Error querying file: {str(e)}")
