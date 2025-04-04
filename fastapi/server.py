"""
FastAPI Chat Server
==================

A minimalistic FastAPI server that provides a chat endpoint with Ollama LLM integration
and Chroma vector database for retrieval augmented generation.

Usage:
    uvicorn main:app --reload

Features:
    - Chat endpoint with context-aware responses
    - Health check endpoint
    - ChromaDB integration for document retrieval
    - Ollama integration for embeddings and LLM responses
"""

import os
import yaml
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, Response, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_ollama import OllamaEmbeddings
import chromadb
import requests
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# ----- Models -----

class ChatMessage(BaseModel):
    message: str
    voiceEnabled: bool = False


class HealthStatus(BaseModel):
    status: str
    components: Dict[str, Dict[str, Any]]


# ----- Configuration -----

def load_config():
    """Load configuration from config.yaml file"""
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)


# ----- Client Classes -----

class ChromaRetriever:
    """Handles retrieval of relevant documents from ChromaDB"""
    
    def __init__(self, collection, embeddings):
        self.collection = collection
        self.embeddings = embeddings
    
    async def get_relevant_context(self, query: str, n_results: int = 3):
        """Retrieve relevant context for a query"""
        try:
            # Generate embedding for query
            query_embedding = self.embeddings.embed_query(query)
            
            # Query the collection
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            if results['metadatas'] and len(results['metadatas'][0]) > 0:
                for i, (doc, metadata, distance) in enumerate(zip(
                    results['documents'][0], 
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    similarity = 1 - distance
                    if similarity < 0.7:  # Threshold for relevance
                        continue
                        
                    if 'question' in metadata and 'answer' in metadata:
                        formatted_results.append({
                            "question": metadata['question'],
                            "answer": metadata['answer'],
                            "similarity": similarity
                        })
                    else:
                        formatted_results.append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": similarity
                        })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []


class OllamaClient:
    """Handles communication with Ollama API"""
    
    def __init__(self, config: Dict[str, Any], retriever: ChromaRetriever):
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama']['model']
        self.retriever = retriever
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self):
        """Load system prompt from file if available"""
        try:
            prompt_file = self.config.get('general', {}).get('system_prompt_file', 'system_prompt.txt')
            with open(prompt_file, 'r') as file:
                return file.read().strip()
        except Exception as e:
            logger.warning(f"Could not load system prompt: {str(e)}")
            return """You are a helpful assistant that answers questions based on the provided context."""
    
    async def verify_connection(self) -> bool:
        """Verify connection to Ollama service"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            return False
    
    async def generate_response(self, message: str, stream: bool = True):
        """Generate a response using Ollama and retrieved context"""
        try:
            # Get relevant context
            context = await self.retriever.get_relevant_context(message)
            
            # Format context for prompt
            context_text = ""
            if context:
                context_text = "Here is some relevant information:\n\n"
                for item in context:
                    if "question" in item and "answer" in item:
                        context_text += f"Question: {item['question']}\nAnswer: {item['answer']}\n\n"
                    elif "content" in item:
                        context_text += f"{item['content']}\n\n"
            
            # Create full prompt with system message, context, and user query
            full_prompt = f"{self.system_prompt}\n\n"
            if context_text:
                full_prompt += f"{context_text}\n\n"
            full_prompt += f"User: {message}\n\nAssistant:"
            
            # Create request payload
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "temperature": self.config['ollama'].get('temperature', 0.7),
                "top_p": self.config['ollama'].get('top_p', 0.9),
                "top_k": self.config['ollama'].get('top_k', 40),
                "repeat_penalty": self.config['ollama'].get('repeat_penalty', 1.1),
                "num_predict": self.config['ollama'].get('num_predict', 1024),
                "stream": stream
            }
            
            # Make request to Ollama
            response = requests.post(f"{self.base_url}/api/generate", json=payload, stream=stream)
            
            if stream:
                # Return a generator for streaming responses
                buffer = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            response_data = json.loads(line)
                            if response_data.get("response"):
                                chunk = response_data["response"]
                                # Add space after punctuation if needed
                                if buffer and buffer[-1] in ".!?,:;" and chunk and chunk[0].isalnum():
                                    chunk = " " + chunk
                                # Add space between lowercase and uppercase if needed
                                elif buffer and buffer[-1].islower() and chunk and chunk[0].isupper():
                                    chunk = " " + chunk
                                buffer += chunk
                                yield chunk
                        except json.JSONDecodeError:
                            continue
            else:
                # For non-streaming, yield the complete response once
                response_data = response.json()
                yield response_data.get("response", "I'm sorry, I couldn't generate a response.")
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."


class ChatService:
    """Handles chat-related functionality"""
    
    def __init__(self, config: Dict[str, Any], llm_client: OllamaClient, logger_service=None):
        self.config = config
        self.llm_client = llm_client
        self.logger_service = logger_service
    
    async def process_chat(self, message: str, voice_enabled: bool, client_ip: str) -> Dict[str, Any]:
        """Process a chat message and return a response"""
        try:
            # Generate response
            response_text = ""
            async for chunk in self.llm_client.generate_response(message, stream=False):
                response_text += chunk
            
            # Log conversation if logger service is available
            if self.logger_service:
                await self.logger_service.log_conversation(message, response_text, client_ip)
            
            # Return response
            result = {
                "response": response_text,
                "audio": None  # We'll leave audio handling as a future enhancement
            }
            
            return result
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def process_chat_stream(self, message: str, voice_enabled: bool, client_ip: str):
        """Process a chat message and stream the response"""
        try:
            # Keep track of the full response for post-processing
            full_text = ""
            
            # Collect chunks to build the response
            async for chunk in self.llm_client.generate_response(message, stream=True):
                full_text += chunk
                
                # Apply text fixes (add spaces where needed)
                fixed_text = self._fix_text_formatting(full_text)
                
                # Send the current fixed text
                yield f"data: {json.dumps({'text': fixed_text, 'done': False})}\n\n"
            
            # Send final done message
            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
            
            # Log conversation if logger service is available
            if self.logger_service:
                await self.logger_service.log_conversation(message, full_text, client_ip)
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            yield f"data: {json.dumps({'text': f'Error: {str(e)}', 'done': True})}\n\n"
    
    def _fix_text_formatting(self, text: str) -> str:
        """Fix common text formatting issues from LLM responses"""
        import re
        
        # Fix missing spaces after punctuation
        text = re.sub(r'([.,!?:;])([A-Za-z0-9])', r'\1 \2', text)
        
        # Fix missing spaces between sentences
        text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
        
        # Fix missing spaces between words (lowercase followed by uppercase)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        return text


class HealthService:
    """Handles health check functionality"""
    
    def __init__(self, config: Dict[str, Any], chroma_client, llm_client: OllamaClient):
        self.config = config
        self.chroma_client = chroma_client
        self.llm_client = llm_client
    
    async def get_health_status(self) -> HealthStatus:
        """Get health status of all components"""
        status = {
            "status": "ok",
            "components": {
                "server": {
                    "status": "ok"
                },
                "chroma": {
                    "status": "unknown"
                },
                "llm": {
                    "status": "unknown"
                }
            }
        }
        
        # Check Chroma
        try:
            # Simple heartbeat check
            self.chroma_client.heartbeat()
            status["components"]["chroma"]["status"] = "ok"
        except Exception as e:
            status["components"]["chroma"]["status"] = "error"
            status["components"]["chroma"]["error"] = str(e)
        
        # Check LLM (Ollama)
        try:
            llm_ok = await self.llm_client.verify_connection()
            status["components"]["llm"]["status"] = "ok" if llm_ok else "error"
            if not llm_ok:
                status["components"]["llm"]["error"] = "Failed to connect to Ollama"
        except Exception as e:
            status["components"]["llm"]["status"] = "error"
            status["components"]["llm"]["error"] = str(e)
        
        # Overall status
        if any(component["status"] != "ok" for component in status["components"].values()):
            status["status"] = "error"
        
        return HealthStatus(**status)
    
    def is_healthy(self, health: HealthStatus) -> bool:
        """Check if the system is healthy based on health status"""
        return health.status == "ok"


# ----- Application Startup and Shutdown -----

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up FastAPI application")
    app.state.config = load_config()
    
    # Initialize ChromaDB client
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
    app.state.retriever = ChromaRetriever(collection, app.state.embeddings)
    
    # Initialize LLM client
    app.state.llm_client = OllamaClient(app.state.config, app.state.retriever)
    
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
    
    logger.info("Startup complete")
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI application")
    # Cleanup code here
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
    stream = request.headers.get("Accept") == "text/event-stream"
    
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
    uvicorn.run("main:app", host="0.0.0.0", port=3000, reload=True)