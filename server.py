"""
ORBIT Server
==================

A modular MCP-compliant FastAPI server that provides a chat completion endpoint.

Architecture Overview:
    - FastAPI-based web server with async support
    - Modular design with separate services for different functionalities
    - Support for multiple LLM providers (Ollama, HuggingFace, etc.)
    - SQL and Vector database integration for RAG capabilities
    - API key management and authentication
    - Session management
    - Logging and Health monitoring
"""

import os
import asyncio
import aiohttp
import logging

# Import the InferenceServer class from the new file
from inference_server import InferenceServer

# Configure MongoDB logging
from utils.mongodb_utils import configure_mongodb_logging
configure_mongodb_logging()

# Global registry to track aiohttp client sessions
_AIOHTTP_SESSIONS = set()

def register_aiohttp_session(session):
    """
    Register an aiohttp ClientSession for tracking and cleanup.
    
    This function is used to keep track of all aiohttp client sessions
    created by the application to ensure proper cleanup during shutdown.
    
    Args:
        session: The aiohttp ClientSession to register
        
    Returns:
        The registered session
    """
    global _AIOHTTP_SESSIONS
    _AIOHTTP_SESSIONS.add(session)
    return session

async def close_all_aiohttp_sessions():
    """
    Close all tracked aiohttp ClientSessions.
    
    This function is called during server shutdown to ensure all
    aiohttp client sessions are properly closed to prevent resource leaks.
    """
    global _AIOHTTP_SESSIONS
    if not _AIOHTTP_SESSIONS:
        return
    
    logger = logging.getLogger(__name__)
    logger.info(f"Closing {len(_AIOHTTP_SESSIONS)} aiohttp sessions")
    
    close_tasks = []
    for session in list(_AIOHTTP_SESSIONS):
        if not session.closed:
            close_tasks.append(session.close())
    
    if close_tasks:
        await asyncio.gather(*close_tasks, return_exceptions=True)
    
    _AIOHTTP_SESSIONS.clear()
    logger.info("All aiohttp sessions closed")

# Monkey patch aiohttp.ClientSession to track all created sessions
original_init = aiohttp.ClientSession.__init__

def patched_init(self, *args, **kwargs):
    """
    Patched initialization for aiohttp.ClientSession to automatically register sessions.
    
    This patch ensures all aiohttp client sessions are tracked for proper cleanup.
    """
    original_init(self, *args, **kwargs)
    register_aiohttp_session(self)

aiohttp.ClientSession.__init__ = patched_init

# Create a global app instance for direct use by uvicorn in development mode
from fastapi import FastAPI
app = FastAPI(
    title="ORBIT Open Inference Server",
    description="MCP inference server with RAG capabilities",
    version="1.0.0"
)

# Factory function for creating app instances in multi-worker mode
def create_app() -> FastAPI:
    """
    Factory function to create a FastAPI application instance.
    
    This function is used by uvicorn's multiple worker mode to create
    separate application instances for each worker process.
    
    The configuration path is read from the OIS_CONFIG_PATH environment variable.
    If not set, the default configuration will be used.
    
    Returns:
        A configured FastAPI application instance
    """
    config_path = os.environ.get('OIS_CONFIG_PATH')
    
    # Create server instance
    server = InferenceServer(config_path=config_path)
    
    # Return just the FastAPI app instance
    return server.app