"""
File upload routes for the inference server
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, File, UploadFile, Form, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from config.config_manager import _is_true_value

logger = logging.getLogger(__name__)

# Create the file router
file_router = APIRouter(prefix="/files", tags=["files"])

def get_file_service(request: Request):
    """Get the file service from app state"""
    # Check if file upload is enabled
    if not _is_true_value(request.app.state.config.get('file_upload', {}).get('enabled', True)):
        raise HTTPException(status_code=403, detail="File upload service is disabled")

    # Check for API key
    header_name = request.app.state.config.get('api_keys', {}).get('header_name', 'X-API-Key')
    api_key = request.headers.get(header_name)
    
    # Check if we're in inference-only mode
    inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
    
    if not inference_only and not api_key:
        raise HTTPException(status_code=401, detail="API key required for file operations")

    if not hasattr(request.app.state, 'file_service'):
        from services.file_service import FileService
        # Get retriever service if available
        retriever_service = getattr(request.app.state, 'retriever', None)
        request.app.state.file_service = FileService(
            request.app.state.config,
            retriever_service
        )
    return request.app.state.file_service

@file_router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    collection_name: Optional[str] = Form("default"),
    metadata_title: Optional[str] = Form(None),
    metadata_description: Optional[str] = Form(None),
    metadata_tags: Optional[str] = Form(None),
    file_service = Depends(get_file_service)
):
    """
    Upload a file and extract its text content.
    
    This endpoint accepts various file types and:
    - Validates file size and type
    - Extracts text content from the file
    - Optionally stores the content in the vector database
    - Returns processing results and metadata
    
    Supported file types:
    - Text files (.txt, .md, .json)
    - PDF files (.pdf)
    - Word documents (.docx, .doc)
    - Excel files (.xlsx, .xls)
    - CSV files (.csv)
    
    Args:
        file: The uploaded file
        collection_name: Collection to store the document in (optional)
        metadata_title: Optional title for the document
        metadata_description: Optional description
        metadata_tags: Optional comma-separated tags
        
    Returns:
        JSON response with upload results
    """
    try:
        # Read file content
        file_content = await file.read()
        
        # Prepare metadata
        metadata = {}
        if metadata_title:
            metadata['title'] = metadata_title
        if metadata_description:
            metadata['description'] = metadata_description
        if metadata_tags:
            metadata['tags'] = [tag.strip() for tag in metadata_tags.split(',') if tag.strip()]
        
        # Log upload attempt
        if _is_true_value(request.app.state.config.get('general', {}).get('verbose', False)):
            logger.info(f"File upload attempt: {file.filename} ({len(file_content)} bytes)")
        
        # Process the file
        result = await file_service.process_file_upload(
            file_content=file_content,
            filename=file.filename or "unnamed_file",
            collection_name=collection_name or "default",
            metadata=metadata
        )
        
        if result['success']:
            logger.info(f"File upload successful: {result['file_id']}")
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "File uploaded and processed successfully",
                    "data": {
                        "file_id": result['file_id'],
                        "filename": result['filename'],
                        "file_size": result['file_size'],
                        "mime_type": result['mime_type'],
                        "text_length": result['text_length'],
                        "text_preview": result['text_preview'],
                        "collection_name": collection_name,
                        "storage_results": result.get('storage_results', [])
                    }
                }
            )
        else:
            logger.error(f"File upload failed: {result['error']}")
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": result['error'],
                    "file_id": result.get('file_id')
                }
            )
            
    except Exception as e:
        logger.error(f"File upload endpoint error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Internal server error: {str(e)}"
            }
        )

@file_router.post("/upload/batch")
async def upload_multiple_files(
    request: Request,
    files: List[UploadFile] = File(...),
    collection_name: Optional[str] = Form("default"),
    file_service = Depends(get_file_service)
):
    """
    Upload multiple files at once.
    
    This endpoint processes multiple files in parallel and returns
    results for each file individually.
    
    Args:
        files: List of uploaded files
        collection_name: Collection to store documents in
        
    Returns:
        JSON response with results for each file
    """
    try:
        results = []
        
        # Check file count limit
        max_files = request.app.state.config.get('file_upload', {}).get('max_files_per_batch', 10)
        if len(files) > max_files:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Too many files. Maximum {max_files} files allowed per batch."
                }
            )
        
        for file in files:
            try:
                file_content = await file.read()
                
                result = await file_service.process_file_upload(
                    file_content=file_content,
                    filename=file.filename or "unnamed_file",
                    collection_name=collection_name or "default"
                )
                
                results.append({
                    "filename": file.filename,
                    "result": result
                })
                
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {str(e)}")
                results.append({
                    "filename": file.filename,
                    "result": {
                        "success": False,
                        "error": f"Processing error: {str(e)}"
                    }
                })
        
        # Count successes and failures
        successful = sum(1 for r in results if r['result']['success'])
        failed = len(results) - successful
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Batch upload completed: {successful} successful, {failed} failed",
                "data": {
                    "total_files": len(results),
                    "successful": successful,
                    "failed": failed,
                    "results": results
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Batch upload error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Batch upload failed: {str(e)}"
            }
        )

@file_router.get("/info/{file_id}")
async def get_file_info(
    file_id: str,
    request: Request,
    file_service = Depends(get_file_service)
):
    """
    Get information about an uploaded file.
    
    Args:
        file_id: The unique file identifier
        
    Returns:
        JSON response with file information
    """
    try:
        file_info = await file_service.get_file_info(file_id)
        
        if file_info:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": file_info
                }
            )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "File not found"
                }
            )
            
    except Exception as e:
        logger.error(f"Get file info error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Failed to get file info: {str(e)}"
            }
        )

@file_router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    request: Request,
    file_service = Depends(get_file_service)
):
    """
    Delete an uploaded file.
    
    Args:
        file_id: The unique file identifier
        
    Returns:
        JSON response with deletion result
    """
    try:
        success = await file_service.delete_file(file_id)
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "File deleted successfully"
                }
            )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "File not found"
                }
            )
            
    except Exception as e:
        logger.error(f"Delete file error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Failed to delete file: {str(e)}"
            }
        )

@file_router.get("/status")
async def get_upload_status(
    request: Request,
    file_service = Depends(get_file_service)
):
    """
    Get file upload service status and configuration.
    
    Returns:
        JSON response with service status
    """
    try:
        config = request.app.state.config.get('file_upload', {})
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "service_available": True,
                    "max_file_size_mb": config.get('max_size_mb', 10),
                    "allowed_extensions": list(config.get('allowed_extensions', [])),
                    "auto_store_in_vector_db": config.get('auto_store_in_vector_db', True),
                    "chunk_size": config.get('chunk_size', 1000),
                    "supported_libraries": {
                        "pdf": "PyPDF2" if file_service.__class__.__module__.find('HAS_PDF') else "Not available",
                        "docx": "python-docx" if file_service.__class__.__module__.find('HAS_DOCX') else "Not available",
                        "excel": "openpyxl" if file_service.__class__.__module__.find('HAS_EXCEL') else "Not available",
                        "magic": "python-magic" if file_service.__class__.__module__.find('HAS_MAGIC') else "Not available"
                    }
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Get upload status error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Failed to get status: {str(e)}"
            }
        ) 