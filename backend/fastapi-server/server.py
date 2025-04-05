"""
FastAPI Chat Server
==================

A minimalistic FastAPI server that provides a chat endpoint with Ollama LLM integration
and Chroma vector database for retrieval augmented generation.

Usage:
    uvicorn server:app --reload

Features:
    - Chat endpoint with context-aware responses
    - Health check endpoint
    - ChromaDB integration for document retrieval
    - Ollama integration for embeddings and LLM responses
    - Safety check for user queries
"""

import os
import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import chromadb
from langchain_ollama import OllamaEmbeddings

# Import local modules
from config import load_config, _is_true_value
from models import ChatMessage, HealthStatus
from clients import ChromaRetriever, OllamaClient
from services import ChatService, HealthService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Thread pool for blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)


# ----- Application Startup and Shutdown -----

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up FastAPI application")
    logger.info("Looking for configuration file...")
    
    # Show search paths before loading config
    config_paths = [
        os.path.abspath('../config/config.yaml'),
        os.path.abspath('../../backend/config/config.yaml'),
        os.path.abspath('config.yaml')
    ]
    logger.info(f"Config search paths (in order of preference):")
    for i, path in enumerate(config_paths, 1):
        logger.info(f"  {i}. {path}")
    
    # Load configuration
    app.state.config = load_config()
    
    # Initialize ChromaDB client
    logger.info(f"Connecting to ChromaDB at {app.state.config['chroma']['host']}:{app.state.config['chroma']['port']}...")
    app.state.chroma_client = chromadb.HttpClient(
        host=app.state.config['chroma']['host'],
        port=int(app.state.config['chroma']['port'])
    )
    
    # Initialize Ollama embeddings
    app.state.embeddings = OllamaEmbeddings(
        model=app.state.config['ollama']['embed_model'],
        base_url=app.state.config['ollama']['base_url']
    )
    
    # Initialize Chroma collection
    try:
        collection = app.state.chroma_client.get_collection(
            name=app.state.config['chroma']['collection']
        )
        logger.info(f"Successfully connected to Chroma collection: {app.state.config['chroma']['collection']}")
    except Exception as e:
        logger.error(f"Failed to get Chroma collection: {str(e)}")
        raise
    
    # Initialize retriever
    app.state.retriever = ChromaRetriever(collection, app.state.embeddings, app.state.config)
    
    # Initialize LLM client
    try:
        app.state.llm_client = OllamaClient(app.state.config, app.state.retriever)
        await app.state.llm_client.initialize()
    except RuntimeError as e:
        logger.error(f"Failed to initialize OllamaClient: {str(e)}")
        raise
    
    # Verify LLM connection
    if not await app.state.llm_client.verify_connection():
        logger.error("Failed to connect to Ollama. Exiting...")
        raise Exception("Failed to connect to Ollama")
    
    # Initialize services
    app.state.health_service = HealthService(
        app.state.config,
        app.state.chroma_client,
        app.state.llm_client
    )
    
    app.state.chat_service = ChatService(
        app.state.config,
        app.state.llm_client
    )
    
    # Log ready message with key config details
    logger.info("=" * 50)
    logger.info("Server initialization complete. Configuration summary:")
    logger.info(f"Server running with {app.state.config['ollama']['model']} model")
    logger.info(f"Using ChromaDB collection: {app.state.config['chroma']['collection']}")
    logger.info(f"Confidence threshold: {app.state.config['chroma'].get('confidence_threshold', 0.85)}")
    logger.info(f"Relevance threshold: {app.state.retriever.relevance_threshold}")
    logger.info(f"Verbose mode: {_is_true_value(app.state.config['general'].get('verbose', False))}")
    
    # Note service configuration without exposing sensitive info
    auth_services = []
    if 'eleven_labs' in app.state.config and app.state.config['eleven_labs'].get('api_key'):
        auth_services.append("ElevenLabs")
    if _is_true_value(app.state.config.get('elasticsearch', {}).get('enabled', False)) and app.state.config['elasticsearch'].get('auth', {}).get('username'):
        auth_services.append("Elasticsearch")
    
    if auth_services:
        logger.info(f"Authenticated services: {', '.join(auth_services)}")
    
    logger.info("=" * 50)
    
    logger.info("Startup complete")
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI application")
    # Close aiohttp session
    await app.state.llm_client.close()
    # Shutdown thread pool
    thread_pool.shutdown(wait=False)
    logger.info("Shutdown complete")


# ----- FastAPI App Creation -----

app = FastAPI(
    title="FastAPI Chat Server",
    description="A minimalistic FastAPI server with chat endpoint",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# ----- Dependency Injection -----

async def get_chat_service():
    return app.state.chat_service


async def get_health_service():
    return app.state.health_service


# ----- API Routes -----

@app.post("/chat")
async def chat_endpoint(
    request: Request,
    chat_message: ChatMessage,
    chat_service=Depends(get_chat_service)
):
    """Process a chat message and return a response"""
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    forwarded_ip = request.headers.get("X-Forwarded-For", client_ip)
    
    # Check if client wants streaming response
    # This is determined both by the Accept header and the stream field in the request
    stream = (request.headers.get("Accept") == "text/event-stream") or chat_message.stream
    
    if stream:
        return StreamingResponse(
            chat_service.process_chat_stream(
                chat_message.message,
                chat_message.voiceEnabled,
                forwarded_ip
            ),
            media_type="text/event-stream"
        )
    else:
        # Process chat normally
        result = await chat_service.process_chat(
            chat_message.message,
            chat_message.voiceEnabled,
            forwarded_ip
        )
        return result


@app.get("/health", response_model=HealthStatus)
async def health_check(health_service=Depends(get_health_service)):
    """Check the health of the application and its dependencies"""
    health = await health_service.get_health_status()
    return health


# Run the application if script is executed directly
if __name__ == "__main__":
    import uvicorn
    
    # Load configuration
    config = load_config()
    
    # Get server settings from config
    port = int(config.get('general', {}).get('port', 3000))
    host = config.get('general', {}).get('host', '0.0.0.0')
    
    # Use https if enabled in config
    https_enabled = _is_true_value(config.get('general', {}).get('https', {}).get('enabled', False))
    if https_enabled:
        ssl_keyfile = config['general']['https']['key_file']
        ssl_certfile = config['general']['https']['cert_file']
        https_port = int(config['general']['https'].get('port', 3443))
        
        logger.info(f"Starting HTTPS server on {host}:{https_port}")
        uvicorn.run(
            "server:app", 
            host=host, 
            port=https_port, 
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile
        )
    else:
        # Start HTTP server
        logger.info(f"Starting HTTP server on {host}:{port}")
        uvicorn.run("server:app", host=host, port=port, reload=True)