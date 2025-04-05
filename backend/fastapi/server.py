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
    - Safety check for user queries
"""

import os
import yaml
import json
from typing import Dict, Any, List, Optional, AsyncGenerator, Tuple
from fastapi import FastAPI, Request, Response, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from langchain_ollama import OllamaEmbeddings
import chromadb
import requests
import logging
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from functools import lru_cache
import re
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Thread pool for blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)

# Precompile regex patterns for text formatting
RE_PUNCTUATION_SPACE = re.compile(r'([.,!?:;])([A-Za-z0-9])')
RE_SENTENCE_SPACE = re.compile(r'([.!?])([A-Z])')
RE_WORD_SPACE = re.compile(r'([a-z])([A-Z])')

# ----- Models -----

class ChatMessage(BaseModel):
    message: str
    voiceEnabled: bool = False
    stream: bool = Field(default=True, description="Whether to stream the response")


class HealthStatus(BaseModel):
    status: str
    components: Dict[str, Dict[str, Any]]


# ----- Configuration -----

@lru_cache(maxsize=1)
def load_config():
    """Load configuration from shared config.yaml file"""
    # First try the shared config
    config_paths = [
        '../config/config.yaml',  # Shared config
        '../../backend/config/config.yaml',  # Alternative path
        'config.yaml',  # Fallback to local config
    ]
    
    for config_path in config_paths:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"Successfully loaded configuration from {os.path.abspath(config_path)}")
                
                # Ensure all required config sections exist with defaults
                config = ensure_config_defaults(config)
                
                # Log key configuration values
                _log_config_summary(config, config_path)
                
                return config
        except FileNotFoundError:
            logger.debug(f"Config file not found at {os.path.abspath(config_path)}")
            continue
        except Exception as e:
            logger.warning(f"Error loading config from {os.path.abspath(config_path)}: {str(e)}")
    
    # If we get here, no config was found - use default config
    logger.warning("No config file found. Using default configuration.")
    default_config = get_default_config()
    _log_config_summary(default_config, "DEFAULT")
    return default_config


def _log_config_summary(config: Dict[str, Any], source_path: str):
    """Log a summary of important config values with sensitive data masked"""
    logger.info(f"Configuration summary (source: {source_path}):")
    
    # Server settings
    logger.info(f"  Server: port={config['general'].get('port')}, verbose={config['general'].get('verbose')}")
    
    # Chroma settings
    logger.info(f"  Chroma: host={config['chroma'].get('host')}, port={config['chroma'].get('port')}, collection={config['chroma'].get('collection')}")
    
    # Ollama settings - don't log any potential API keys
    logger.info(f"  Ollama: base_url={_mask_url(config['ollama'].get('base_url'))}, model={config['ollama'].get('model')}, embed_model={config['ollama'].get('embed_model')}")
    logger.info(f"  Stream: {_is_true_value(config['ollama'].get('stream', True))}")
    
    # Elasticsearch settings - mask credentials
    if _is_true_value(config.get('elasticsearch', {}).get('enabled', False)):
        es_node = _mask_url(config['elasticsearch'].get('node', ''))
        has_auth = bool(config['elasticsearch'].get('auth', {}).get('username'))
        logger.info(f"  Elasticsearch: enabled=True, node={es_node}, index={config['elasticsearch'].get('index')}, auth={'[CONFIGURED]' if has_auth else '[NONE]'}")
    
    # Eleven Labs settings - mask API key
    if 'eleven_labs' in config:
        has_api_key = bool(config['eleven_labs'].get('api_key'))
        logger.info(f"  ElevenLabs: api_key={'[CONFIGURED]' if has_api_key else '[NONE]'}, voice_id={config['eleven_labs'].get('voice_id')}")
    
    # Log if HTTPS is enabled
    https_enabled = _is_true_value(config.get('general', {}).get('https', {}).get('enabled', False))
    if https_enabled:
        logger.info(f"  HTTPS: enabled=True, port={config['general']['https'].get('port')}")


def _mask_url(url: str) -> str:
    """Mask sensitive parts of URLs like credentials"""
    if not url:
        return url
    
    try:
        # For URLs with credentials like https://user:pass@host.com
        if '@' in url and '//' in url:
            # Split by // to get the protocol and the rest
            protocol, rest = url.split('//', 1)
            # If there are credentials in the URL
            if '@' in rest:
                # Split by @ to separate credentials from host
                credentials_part, host_part = rest.split('@', 1)
                # Replace credentials with [REDACTED]
                return f"{protocol}//[REDACTED]@{host_part}"
        
        # For URLs with API keys like query parameters
        if '?' in url and ('key=' in url.lower() or 'token=' in url.lower() or 'api_key=' in url.lower() or 'apikey=' in url.lower()):
            # Simple pattern matching for common API key parameters
            # Split URL and query string
            base_url, query = url.split('?', 1)
            params = query.split('&')
            masked_params = []
            
            for param in params:
                param_lower = param.lower()
                if 'key=' in param_lower or 'token=' in param_lower or 'api_key=' in param_lower or 'apikey=' in param_lower or 'password=' in param_lower:
                    # Find the parameter name
                    param_name = param.split('=')[0]
                    masked_params.append(f"{param_name}=[REDACTED]")
                else:
                    masked_params.append(param)
            
            return f"{base_url}?{'&'.join(masked_params)}"
        
        return url
    except Exception:
        # If any error occurs during masking, return a generically masked URL
        return url.split('//')[0] + '//[HOST_REDACTED]' if '//' in url else '[URL_REDACTED]'


def ensure_config_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required config sections and values exist with defaults"""
    default_config = get_default_config()
    
    # Process environment variables in config before checking defaults
    config = _process_env_vars(config)
    
    # Ensure top-level sections exist
    for section in default_config:
        if section not in config:
            logger.warning(f"Missing config section '{section}'. Using defaults.")
            config[section] = default_config[section]
        elif isinstance(default_config[section], dict):
            # For dict sections, merge with defaults preserving existing values
            for key, value in default_config[section].items():
                if key not in config[section]:
                    logger.warning(f"Missing config key '{section}.{key}'. Using default value: {value}")
                    config[section][key] = value
    
    # Make sure confidence_threshold exists
    if 'chroma' in config:
        if 'confidence_threshold' not in config['chroma']:
            config['chroma']['confidence_threshold'] = 0.65
    
    return config


def _process_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Process environment variables in config values"""
    # Handle environment variables in the config (format: ${ENV_VAR_NAME})
    def replace_env_vars(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var_name = value[2:-1]
            env_value = os.environ.get(env_var_name)
            if env_value is not None:
                logger.info(f"Using environment variable {env_var_name} for configuration")
                return env_value
            else:
                logger.warning(f"Environment variable {env_var_name} not found")
                return ""
        return value

    # Recursively process the config
    def process_dict(d):
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                result[k] = process_dict(v)
            elif isinstance(v, list):
                result[k] = [process_dict(item) if isinstance(item, dict) else replace_env_vars(item) for item in v]
            else:
                result[k] = replace_env_vars(v)
        return result

    return process_dict(config)


def _is_true_value(value) -> bool:
    """Helper function to check if a value (string or boolean) is equivalent to True"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', 'y', '1', 'on')
    # Numeric values - 0 is False, anything else is True
    if isinstance(value, (int, float)):
        return bool(value)
    # Default for anything else
    return False


def get_default_config() -> Dict[str, Any]:
    """Return default configuration values"""
    return {
        "general": {
            "port": 3000,
            "verbose": "false",
            "https": {
                "enabled": False,
                "port": 3443,
                "cert_file": "./cert.pem",
                "key_file": "./key.pem"
            }
        },
        "chroma": {
            "host": "localhost",
            "port": 8000,
            "collection": "qa-chatbot",
            "confidence_threshold": 0.85
        },
        "elasticsearch": {
            "enabled": False,
            "node": "http://localhost:9200",
            "index": "chatbot",
            "auth": {
                "username": "",
                "password": ""
            }
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "num_predict": 1024,
            "model": "llama2",
            "embed_model": "nomic-embed-text"
        }
    }


# ----- Client Classes -----

class ChromaRetriever:
    """Handles retrieval of relevant documents from ChromaDB"""
    
    def __init__(self, collection, embeddings, config):
        self.collection = collection
        self.embeddings = embeddings
        self.config = config
        
        # Use thresholds from config or fall back to defaults
        self.confidence_threshold = float(config['chroma'].get('confidence_threshold', 0.85))
        
        # If relevance_threshold exists in config, use it directly
        if 'relevance_threshold' in config['chroma']:
            self.relevance_threshold = float(config['chroma']['relevance_threshold'])
        else:
            # Otherwise, calculate it based on confidence_threshold
            self.relevance_threshold = self.confidence_threshold - 0.15
        
        logger.info(f"ChromaRetriever initialized with confidence threshold: {self.confidence_threshold}, relevance threshold: {self.relevance_threshold}")
    
    async def get_relevant_context(self, query: str, n_results: int = 5):
        """Retrieve relevant context for a query"""
        try:
            # Generate embedding for query using thread pool to avoid blocking
            query_embedding = await asyncio.get_event_loop().run_in_executor(
                thread_pool, 
                self.embeddings.embed_query, 
                query
            )
            
            # Query the collection in thread pool
            results = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"]
                )
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
                    
                    if 'question' in metadata and 'answer' in metadata:
                        # Calculate relevance score with keyword matching
                        score = similarity
                        query_terms = query.lower().split()
                        question_text = metadata.get('question', '').lower()
                        answer_text = metadata.get('answer', '').lower()
                        
                        # Boost score for term matches
                        for term in query_terms:
                            if len(term) > 3:  # Only consider significant terms
                                if term in question_text:
                                    score += 0.05  # Boost for question matches
                                if term in answer_text:
                                    score += 0.03  # Smaller boost for answer matches
                        
                        formatted_results.append({
                            "question": metadata['question'],
                            "answer": metadata['answer'],
                            "similarity": similarity,
                            "score": score,
                            "confidence": similarity  # For direct answer checks
                        })
                    else:
                        # Calculate score for general content
                        score = similarity
                        query_terms = query.lower().split()
                        content = doc.lower()
                        
                        # Boost score for content matches
                        for term in query_terms:
                            if len(term) > 3 and term in content:
                                score += 0.02
                        
                        formatted_results.append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": similarity,
                            "score": score
                        })
            
            # Sort by calculated score (most relevant first)
            formatted_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            # Filter by threshold
            formatted_results = [r for r in formatted_results if r["similarity"] >= self.relevance_threshold]
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []
    
    def get_direct_answer(self, results):
        """Check if we have a high-confidence direct answer from metadata"""
        if not results:
            return None
        
        best_match = results[0]
        if 'question' in best_match and 'answer' in best_match and 'confidence' in best_match:
            confidence = best_match['confidence']
            if confidence >= self.confidence_threshold:
                return best_match['answer']
        
        return None


class OllamaClient:
    """Handles communication with Ollama API"""
    
    def __init__(self, config: Dict[str, Any], retriever: ChromaRetriever):
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama']['model']
        self.retriever = retriever
        self.system_prompt = self._load_system_prompt()
        self.safety_prompt = self._load_safety_prompt()
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        # Create aiohttp ClientSession for async requests
        self.session = None
    
    def _load_system_prompt(self):
        """Load system prompt from file if available"""
        try:
            prompt_file = self.config.get('general', {}).get('system_prompt_file', '../prompts/system_prompt.txt')
            with open(prompt_file, 'r') as file:
                return file.read().strip()
        except Exception as e:
            logger.warning(f"Could not load system prompt: {str(e)}")
            return """You are a helpful assistant that answers questions based on the provided context."""
    
    def _load_safety_prompt(self):
        """Load safety prompt from file if available"""
        try:
            prompt_file = self.config.get('general', {}).get('safety_prompt_file', '../prompts/safety_prompt.txt')
            with open(prompt_file, 'r') as file:
                return file.read().strip()
        except Exception as e:
            logger.error(f"Could not load safety prompt from file {prompt_file}: {str(e)}")
            raise RuntimeError(f"Safety prompt file '{prompt_file}' is required but could not be loaded: {str(e)}")
    
    async def initialize(self):
        """Initialize the aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def verify_connection(self) -> bool:
        """Verify connection to Ollama service"""
        try:
            # Use aiohttp for non-blocking requests
            await self.initialize()
            async with self.session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            return False
    
    async def check_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform a safety pre-clearance check on the user query.
        Returns a tuple of (is_safe, refusal_message)
        """
        try:
            await self.initialize()  # Ensure session is initialized
            
            # Use the loaded safety prompt + the query
            prompt = self.safety_prompt + " Query: " + query
            
            # Create payload for Ollama API
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": 0.0,  # Use 0 for deterministic response
                "top_p": 1.0,
                "top_k": 1,
                "repeat_penalty": self.config['ollama'].get('repeat_penalty', 1.1),
                "num_predict": 20,  # Limit response length
                "stream": False
            }
            
            start_time = asyncio.get_event_loop().time()
            # Make direct API call to Ollama
            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Safety check failed with status {response.status}")
                    return False, "I cannot assist with that type of request."
                
                data = await response.json()
                model_response = data.get("response", "").strip()
                
                if self.verbose:
                    end_time = asyncio.get_event_loop().time()
                    logger.info(f"Safety check completed in {end_time - start_time:.3f}s")
                    logger.info(f"Safety check response: {model_response}")
                
                # Check if response indicates the query is safe
                is_safe = model_response == "SAFE: true"
                refusal_message = None if is_safe else "I cannot assist with that type of request."
                
                return is_safe, refusal_message
                
        except Exception as e:
            logger.error(f"Error in safety check: {str(e)}")
            # On error, err on the side of caution
            return False, "I cannot assist with that type of request."
    
    async def _format_prompt(self, message: str, context):
        """Format the prompt with context"""
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
        
        return full_prompt
    
    async def generate_response(self, message: str, stream: bool = True):
        """Generate a response using Ollama and retrieved context with safety check - optimized for streaming"""
        try:
            # Ensure session is initialized
            await self.initialize()
            
            # Perform safety check first
            start_time = asyncio.get_event_loop().time()
            is_safe, refusal_message = await self.check_safety(message)
            
            if self.verbose:
                safety_time = asyncio.get_event_loop().time() - start_time
                logger.info(f"Safety check took {safety_time:.3f}s, result: {is_safe}")
            
            # If not safe, return the refusal message
            if not is_safe:
                if stream:
                    yield refusal_message
                else:
                    yield refusal_message
                return
            
            # Get relevant context
            context = await self.retriever.get_relevant_context(message)
            
            # Check for direct answer with high confidence
            direct_answer = self.retriever.get_direct_answer(context)
            if direct_answer:
                if self.verbose:
                    logger.info(f"Using direct answer: {direct_answer}")
                if stream:
                    yield direct_answer
                else:
                    yield direct_answer
                return
            
            # Format prompt
            full_prompt = await self._format_prompt(message, context)
            
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
            
            if self.verbose:
                logger.info(f"Sending prompt to Ollama (length: {len(full_prompt)})")
            
            # Make async request to Ollama
            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if stream:
                    # Process streaming response more efficiently
                    last_chunk = ""
                    async for line in response.content:
                        try:
                            line_text = line.decode('utf-8').strip()
                            if not line_text:
                                continue
                                
                            response_data = json.loads(line_text)
                            if response_data.get("response"):
                                chunk = response_data["response"]
                                
                                # Smart space addition only when needed
                                if last_chunk and last_chunk[-1] in ".!?,:;" and chunk and chunk[0].isalnum():
                                    chunk = " " + chunk
                                # Add space between lowercase and uppercase only when needed
                                elif last_chunk and last_chunk[-1].islower() and chunk and chunk[0].isupper():
                                    chunk = " " + chunk
                                    
                                last_chunk = chunk
                                yield chunk
                        except json.JSONDecodeError:
                            continue
                else:
                    # For non-streaming, yield the complete response once
                    response_data = await response.json()
                    yield response_data.get("response", "I'm sorry, I couldn't generate a response.")
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."

    def _simple_fix_text(self, text: str) -> str:
        """Apply minimal text fixes to a chunk (focused on beginning of chunk only)"""
        # Only fix beginning of chunk if needed - for connecting to previous chunk
        if text and text[0].isalnum() and not text[0].isupper():
            # This might be continuing a sentence, so no changes needed
            return text
        elif text and text[0].isupper() and len(text) > 1:
            # This could be a new sentence, might need a space
            return " " + text if text[0].isupper() else text
        return text


class ChatService:
    """Handles chat-related functionality"""
    
    def __init__(self, config: Dict[str, Any], llm_client: OllamaClient, logger_service=None):
        self.config = config
        self.llm_client = llm_client
        self.logger_service = logger_service
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
    
    async def process_chat(self, message: str, voice_enabled: bool, client_ip: str) -> Dict[str, Any]:
        """Process a chat message and return a response"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Generate response
            response_text = ""
            async for chunk in self.llm_client.generate_response(message, stream=False):
                response_text += chunk
            
            # Apply text fixes
            response_text = self._fix_text_formatting(response_text)
            
            # Log conversation if logger service is available
            if self.logger_service:
                await self.logger_service.log_conversation(message, response_text, client_ip)
            
            if self.verbose:
                end_time = asyncio.get_event_loop().time()
                logger.info(f"Chat processed in {end_time - start_time:.3f}s")
            
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
            start_time = asyncio.get_event_loop().time()
            
            # Keep track of the full response for post-processing
            full_text = ""
            first_token_received = False
            
            # Get stream setting from config or default to true
            # Handle both string and boolean values
            stream_enabled = _is_true_value(self.config['ollama'].get('stream', True))
            
            # Collect chunks to build the response
            async for chunk in self.llm_client.generate_response(message, stream=stream_enabled):
                if not first_token_received:
                    first_token_received = True
                    first_token_time = asyncio.get_event_loop().time()
                    if self.verbose:
                        logger.info(f"Time to first token: {first_token_time - start_time:.3f}s")
                
                full_text += chunk
                
                # Apply text fixes (add spaces where needed)
                fixed_text = self._fix_text_formatting(full_text)
                
                # Send the current fixed text
                yield f"data: {json.dumps({'text': fixed_text, 'done': False})}\n\n"
            
            # Send final done message
            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
            
            if self.verbose:
                end_time = asyncio.get_event_loop().time()
                logger.info(f"Stream completed in {end_time - start_time:.3f}s")
            
            # Log conversation if logger service is available
            if self.logger_service:
                await self.logger_service.log_conversation(message, full_text, client_ip)
                
        except Exception as e:
            logger.error(f"Error processing chat stream: {str(e)}")
            yield f"data: {json.dumps({'text': f'Error: {str(e)}', 'done': True})}\n\n"
    
    def _fix_text_formatting(self, text: str) -> str:
        """Fix common text formatting issues from LLM responses using precompiled regex"""
        # Fix missing spaces after punctuation
        text = RE_PUNCTUATION_SPACE.sub(r'\1 \2', text)
        
        # Fix missing spaces between sentences
        text = RE_SENTENCE_SPACE.sub(r'\1 \2', text)
        
        # Fix missing spaces between words (lowercase followed by uppercase)
        text = RE_WORD_SPACE.sub(r'\1 \2', text)
        
        return text


class HealthService:
    """Handles health check functionality"""
    
    def __init__(self, config: Dict[str, Any], chroma_client, llm_client: OllamaClient):
        self.config = config
        self.chroma_client = chroma_client
        self.llm_client = llm_client
        self._last_status = None
        self._last_check_time = 0
        self._cache_ttl = 30  # Cache health status for 30 seconds
    
    async def get_health_status(self, use_cache: bool = True) -> HealthStatus:
        """Get health status of all components"""
        current_time = asyncio.get_event_loop().time()
        
        # Return cached status if available and not expired
        if use_cache and self._last_status and (current_time - self._last_check_time) < self._cache_ttl:
            return self._last_status
        
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
            # Simple heartbeat check in thread pool
            await asyncio.get_event_loop().run_in_executor(
                thread_pool, 
                self.chroma_client.heartbeat
            )
            status["components"]["chroma"]["status"] = "ok"
        except Exception as e:
            status["components"]["chroma"]["status"] = "error"
            status["components"]["chroma"]["error"] = _sanitize_error_message(str(e))
        
        # Check LLM (Ollama)
        try:
            llm_ok = await self.llm_client.verify_connection()
            status["components"]["llm"]["status"] = "ok" if llm_ok else "error"
            if not llm_ok:
                status["components"]["llm"]["error"] = "Failed to connect to Ollama"
        except Exception as e:
            status["components"]["llm"]["status"] = "error"
            status["components"]["llm"]["error"] = _sanitize_error_message(str(e))
        
        # Overall status
        if any(component["status"] != "ok" for component in status["components"].values()):
            status["status"] = "error"
        
        # Cache the result
        self._last_status = HealthStatus(**status)
        self._last_check_time = current_time
        
        return self._last_status
    
    def is_healthy(self, health: HealthStatus) -> bool:
        """Check if the system is healthy based on health status"""
        return health.status == "ok"


# Add a utility function to sanitize error messages
def _sanitize_error_message(message: str) -> str:
    """Sanitize error messages to remove sensitive information"""
    # List of patterns to look for
    sensitive_patterns = [
        (r'password=([^&\s]+)', 'password=[REDACTED]'),
        (r'apiKey=([^&\s]+)', 'apiKey=[REDACTED]'),
        (r'api_key=([^&\s]+)', 'api_key=[REDACTED]'),
        (r'accessToken=([^&\s]+)', 'accessToken=[REDACTED]'),
        (r'access_token=([^&\s]+)', 'access_token=[REDACTED]'),
        (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer [REDACTED]'),
        (r'Basic\s+[A-Za-z0-9\-._~+/]+=*', 'Basic [REDACTED]'),
        # Auth patterns for URLs
        (r'https?://[^:]+:[^@]+@', 'https://[USER]:[REDACTED]@'),
        # Connection strings
        (r'mongodb(\+srv)?://[^:]+:[^@]+@', 'mongodb$1://[USER]:[REDACTED]@'),
        (r'postgres://[^:]+:[^@]+@', 'postgres://[USER]:[REDACTED]@'),
        # IP addresses - don't redact these as they're needed for debugging
        # but redact any sensitive path info
        (r'/home/[^/]+', '/home/[USER]'),
        # AWS keys pattern
        (r'AKIA[0-9A-Z]{16}', '[AWS_KEY_ID]'),
        (r'AWS_SECRET_ACCESS_KEY[=:]\s*[A-Za-z0-9/+]{40}', 'AWS_SECRET_ACCESS_KEY=[REDACTED]'),
    ]
    
    sanitized = message
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    
    return sanitized


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