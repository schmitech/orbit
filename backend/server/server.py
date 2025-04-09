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
    - Safety check for user queries using GuardrailService
    - HTTPS support using provided certificates
"""

import os
import ssl
import logging
import logging.handlers
import json
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import chromadb
from langchain_ollama import OllamaEmbeddings
from dotenv import load_dotenv
import asyncio
import uvicorn
from pythonjsonlogger import jsonlogger

# Load environment variables
load_dotenv()

# Import local modules
from config.config_manager import load_config, _is_true_value
from models.schema import ChatMessage, ApiKeyCreate, ApiKeyResponse, ApiKeyDeactivate
from models import ChatMessage, HealthStatus
from clients.ollama_client import OllamaClient
from clients.chroma_client import ChromaRetriever
from services import ChatService, HealthService, LoggerService, GuardrailService, RerankerService, ApiKeyService

def setup_logging(config: Dict[str, Any]) -> None:
    """Set up logging configuration based on the config file"""
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    
    # Create logs directory if it doesn't exist
    log_dir = log_config.get('file', {}).get('directory', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Create formatters
    json_formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    text_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Configure console logging
    if _is_true_value(log_config.get('console', {}).get('enabled', True)):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            json_formatter if log_config.get('console', {}).get('format') == 'json' else text_formatter
        )
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)
    
    # Configure file logging
    if _is_true_value(log_config.get('file', {}).get('enabled', True)):
        file_config = log_config['file']
        log_file = os.path.join(log_dir, file_config.get('filename', 'server.log'))
        
        # Set up rotating file handler
        if file_config.get('rotation') == 'midnight':
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',
                interval=1,
                backupCount=file_config.get('backup_count', 30),
                encoding='utf-8'
            )
        else:
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=file_config.get('max_size_mb', 10) * 1024 * 1024,
                backupCount=file_config.get('backup_count', 30),
                encoding='utf-8'
            )
        
        file_handler.setFormatter(
            json_formatter if file_config.get('format') == 'json' else text_formatter
        )
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    
    # Capture warnings if configured
    if _is_true_value(log_config.get('capture_warnings', True)):
        logging.captureWarnings(True)
    
    # Set propagation
    root_logger.propagate = log_config.get('propagate', False)
    
    logger.info("Logging configuration completed")
    # Handle verbose setting consistently
    verbose_value = config.get('general', {}).get('verbose', False)
    if _is_true_value(verbose_value):
        logger.debug("Verbose logging enabled")

# Configure initial basic logging until config is loaded
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Set specific logger levels for more detailed debugging
logging.getLogger('clients.ollama_client').setLevel(logging.DEBUG)

# Thread pool for blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)


# ----- Application Startup and Shutdown -----

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    logger.info("Starting up FastAPI application")
    logger.info("Looking for configuration file...")

    # Show search paths before loading config
    config_paths = [
        os.path.abspath('../config/config.yaml'),
        os.path.abspath('../../backend/config/config.yaml'),
        os.path.abspath('config.yaml')
    ]
    logger.info("Config search paths (in order of preference):")
    for i, path in enumerate(config_paths, 1):
        logger.info(f"  {i}. {path}")

    # Load configuration
    app.state.config = load_config()
    
    # Set up logging with loaded configuration
    setup_logging(app.state.config)
    logger.info("Logging configuration initialized")

    # Initialize ChromaDB client
    chroma_conf = app.state.config['chroma']
    logger.info(f"Connecting to ChromaDB at {chroma_conf['host']}:{chroma_conf['port']}...")
    app.state.chroma_client = chromadb.HttpClient(
        host=chroma_conf['host'],
        port=int(chroma_conf['port'])
    )

    # Initialize API Key Service
    app.state.api_key_service = ApiKeyService(app.state.config)
    await app.state.api_key_service.initialize()
    logger.info("API Key Service initialized")

    # Initialize Ollama embeddings
    ollama_conf = app.state.config['ollama']
    app.state.embeddings = OllamaEmbeddings(
        model=ollama_conf['embed_model'],
        base_url=ollama_conf['base_url']
    )

    # Initialize retriever without a collection - it will be set when an API key is provided
    app.state.retriever = ChromaRetriever(None, app.state.embeddings, app.state.config)
    
    # Initialize GuardrailService
    app.state.guardrail_service = GuardrailService(app.state.config)
    
    # Initialize services concurrently
    try:
        # Create LLM client with guardrail service
        app.state.llm_client = OllamaClient(
            app.state.config, 
            app.state.retriever,
            guardrail_service=app.state.guardrail_service
        )
        
        app.state.logger_service = LoggerService(app.state.config)
        
        # Initialize all services concurrently
        init_tasks = [
            app.state.llm_client.initialize(),
            app.state.logger_service.initialize_elasticsearch(),
            app.state.guardrail_service.initialize(),
            app.state.retriever.initialize()
        ]
        
        # Only initialize reranker if enabled
        if _is_true_value(app.state.config.get('reranker', {}).get('enabled', False)):
            app.state.reranker_service = RerankerService(app.state.config)
            init_tasks.append(app.state.reranker_service.initialize())
        
        await asyncio.gather(*init_tasks)
    except RuntimeError as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise

    # Verify LLM connection
    if not await app.state.llm_client.verify_connection():
        logger.error("Failed to connect to Ollama. Exiting...")
        raise Exception("Failed to connect to Ollama")

    # Initialize remaining services
    app.state.health_service = HealthService(app.state.config, app.state.chroma_client, app.state.llm_client)
    app.state.chat_service = ChatService(app.state.config, app.state.llm_client, app.state.logger_service)

    # Log configuration summary
    logger.info("=" * 50)
    logger.info("Server initialization complete. Configuration summary:")
    logger.info(f"Server running with {app.state.config['ollama']['model']} model")
    logger.info(f"Using ChromaDB collection: {app.state.config['chroma']['collection']}")
    logger.info(f"Confidence threshold: {app.state.config['chroma'].get('confidence_threshold', 0.85)}")
    logger.info(f"Relevance threshold: {app.state.retriever.relevance_threshold}")
    logger.info(f"Verbose mode: {_is_true_value(app.state.config['general'].get('verbose', False))}")
    
    # Reranker settings
    reranker_config = app.state.config.get('reranker', {})
    reranker_enabled = reranker_config.get('enabled', False)
    
    logger.info(f"Reranker: {'enabled' if reranker_enabled else 'disabled'}")
    if reranker_enabled:
        model = reranker_config.get('model', app.state.config['ollama']['model'])
        top_n = reranker_config.get('top_n', 3)
        
        logger.info(f"  Model: {model}")
        logger.info(f"  Top N: {top_n} documents")
        logger.info(f"  Temperature: {reranker_config.get('temperature', 0.0)}")
    
    # Summarization settings
    summarization_config = app.state.config['ollama'].get('summarization', {})
    summarization_enabled = summarization_config.get('enabled', False)
    
    logger.info(f"Summarization: {'enabled' if summarization_enabled else 'disabled'}")
    if summarization_enabled:
        model = summarization_config.get('model', app.state.config['ollama']['model'])
        max_length = summarization_config.get('max_length', 100)
        min_text_length = summarization_config.get('min_text_length', 200)
        
        logger.info(f"  Model: {model}")
        logger.info(f"  Max length: {max_length} tokens")
        logger.info(f"  Min text length: {min_text_length} characters")
    
    # Safety check configuration
    safety_mode = app.state.config.get('safety', {}).get('mode', 'strict')
    safety_enabled = app.state.config.get('safety', {}).get('enabled', True)
    logger.info(f"Safety service: {'enabled' if safety_enabled else 'disabled'}")
    if safety_enabled:
        logger.info(f"Safety check mode: {safety_mode}")
        if safety_mode == 'fuzzy':
            logger.info("Using fuzzy matching for safety checks")
        elif safety_mode == 'disabled':
            logger.warning("⚠️ Safety checks are disabled - all queries will be processed")
    
    # Log safety configuration
    safety_config = app.state.config.get('safety', {})
    max_retries = safety_config.get('max_retries', 3)
    retry_delay = safety_config.get('retry_delay', 1.0)
    request_timeout = safety_config.get('request_timeout', 15)
    allow_on_timeout = safety_config.get('allow_on_timeout', False)
    
    if safety_enabled:
        logger.info(f"Safety check config: retries={max_retries}, delay={retry_delay}s, timeout={request_timeout}s")
        if allow_on_timeout:
            logger.warning("⚠️ Queries will be allowed through if safety check times out")

    # Log authenticated services without exposing sensitive info
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

    # Cleanup code
    try:
        logger.info("Shutting down services...")
        
        # Close services concurrently
        await asyncio.gather(
            app.state.llm_client.close(),
            app.state.logger_service.close(),
            app.state.retriever.close(),
            app.state.guardrail_service.close(),
            app.state.reranker_service.close()
        )
        
        logger.info("Services shut down successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")


# ----- FastAPI App Creation -----

app = FastAPI(
    title="FastAPI Chat Server",
    description="A FastAPI server with chat endpoint",
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


async def get_guardrail_service():
    return app.state.guardrail_service


async def get_api_key_service():
    return app.state.api_key_service


async def get_api_key(
    request: Request,
    api_key_service = Depends(get_api_key_service)
) -> Optional[str]:
    """
    Extract API key from request headers and validate it
    
    Args:
        request: The incoming request
        api_key_service: The API key service
        
    Returns:
        The collection name associated with the API key
    """
    # Skip API key check if not enabled
    if not app.state.config.get('api_keys', {}).get('enabled', False):
        return app.state.config['chroma']['collection']
        
    # Get API key from header
    header_name = app.state.config.get('api_keys', {}).get('header_name', 'X-API-Key')
    api_key = request.headers.get(header_name)
    
    # Validate API key and get collection name
    try:
        collection_name = await api_key_service.get_collection_for_api_key(api_key)
        return collection_name
    except HTTPException as e:
        # Allow health check without API key if configured
        if (request.url.path == "/health" and 
            not app.state.config.get('api_keys', {}).get('require_for_health', False)):
            return app.state.config['chroma']['collection']
        raise e

# ----- API Routes -----

@app.post("/chat")
async def chat_endpoint(
    request: Request,
    chat_message: ChatMessage,
    chat_service = Depends(get_chat_service),
    collection_name: str = Depends(get_api_key)
):
    """
    Process a chat message and return a response
    
    This endpoint validates the API key and uses the associated collection
    for retrieval augmented generation.
    """
    # Resolve client IP (using X-Forwarded-For if available)
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    
    # Determine if streaming is requested via header or request payload
    stream = (request.headers.get("Accept") == "text/event-stream") or chat_message.stream
    
    # Log the collection being used
    if app.state.config.get('general', {}).get('verbose', False):
        logger.info(f"Using collection '{collection_name}' for chat request from {client_ip}")

    if stream:
        return StreamingResponse(
            chat_service.process_chat_stream(
                message=chat_message.message,
                voice_enabled=chat_message.voiceEnabled,
                client_ip=client_ip,
                collection_name=collection_name
            ),
            media_type="text/event-stream"
        )
    else:
        result = await chat_service.process_chat(
            message=chat_message.message,
            voice_enabled=chat_message.voiceEnabled,
            client_ip=client_ip,
            collection_name=collection_name
        )
        return result


# ----- API Key Management Routes -----

@app.post("/admin/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    api_key_data: ApiKeyCreate,
    api_key_service = Depends(get_api_key_service)
):
    """
    Create a new API key associated with a specific collection
    
    This is an admin-only endpoint and should be properly secured in production.
    """
    # In production, add authentication middleware to restrict access to admin endpoints
    
    return await api_key_service.create_api_key(
        api_key_data.collection_name,
        api_key_data.client_name,
        api_key_data.notes
    )


@app.post("/admin/api-keys/deactivate")
async def deactivate_api_key(
    data: ApiKeyDeactivate,
    api_key_service = Depends(get_api_key_service)
):
    """
    Deactivate an API key
    
    This is an admin-only endpoint and should be properly secured in production.
    """
    # In production, add authentication middleware to restrict access to admin endpoints
    
    success = await api_key_service.deactivate_api_key(data.api_key)
    
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
        
    return {"status": "success", "message": "API key deactivated"}


@app.get("/health")
async def health_check(
    health_service = Depends(get_health_service),
    collection_name: str = Depends(get_api_key)
):
    """Check the health of the application and its dependencies"""
    health = await health_service.get_health_status(collection_name)
    return health

def create_ssl_context(config):
    """Create an SSL context from the certificate and key files specified in the config."""
    if not _is_true_value(config.get('general', {}).get('https', {}).get('enabled', False)):
        return None
    
    try:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(
            certfile=config['general']['https']['cert_file'],
            keyfile=config['general']['https']['key_file']
        )
        return ssl_context
    except Exception as e:
        logger.error(f"Failed to create SSL context: {str(e)}")
        raise


# Run the application if script is executed directly
if __name__ == "__main__":
    # Load configuration
    config = load_config()

    # Get server settings from config
    port = int(config.get('general', {}).get('port', 3000))
    host = config.get('general', {}).get('host', '0.0.0.0')

    # Use HTTPS if enabled in config
    https_enabled = _is_true_value(config.get('general', {}).get('https', {}).get('enabled', False))
    
    if https_enabled:
        try:
            ssl_keyfile = config['general']['https']['key_file']
            ssl_certfile = config['general']['https']['cert_file']
            https_port = int(config['general']['https'].get('port', 3443))
            
            logger.info(f"Starting HTTPS server on {host}:{https_port}")
            ssl_context = create_ssl_context(config)
            
            uvicorn.run(
                app,
                host=host,
                port=https_port,
                ssl_keyfile=ssl_keyfile,
                ssl_certfile=ssl_certfile
            )
        except Exception as e:
            logger.error(f"Failed to start HTTPS server: {str(e)}")
            import sys
            sys.exit(1)
    else:
        logger.info(f"Starting HTTP server on {host}:{port}")
        uvicorn.run(app, host=host, port=port, reload=True)