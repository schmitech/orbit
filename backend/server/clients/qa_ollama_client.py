"""
Q&A Ollama Client - Specialized client for Question-Answering applications
=========================================================================

This module provides a specialized Ollama client for Q&A applications,
building on the BaseOllamaClient with specific features for:
- Document/Q&A pair retrieval
- Safety checks
- Reranking 
- Language detection
- Summarization
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Generator
from bson import ObjectId

from .base_ollama_client import BaseOllamaClient
from utils.language_detector import LanguageDetector

logger = logging.getLogger(__name__)

class QAOllamaClient(BaseOllamaClient):
    """
    Specialized Ollama client for Q&A applications.
    
    This client extends the BaseOllamaClient with features specific to
    Q&A applications, such as document retrieval, safety checks,
    reranking, and summarization.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        retriever,
        guardrail_service=None,
        reranker_service=None,
        prompt_service=None,
        no_results_message: Optional[str] = None,
    ):
        """
        Initialize the Q&A Ollama client.
        
        Args:
            config: Configuration dictionary
            retriever: Context retriever object
            guardrail_service: Optional service for safety checks
            reranker_service: Optional service for reranking results
            prompt_service: Optional service for managing system prompts
            no_results_message: Message to show when no results are found
        """
        super().__init__(config)
        
        self.retriever = retriever
        self.guardrail_service = guardrail_service
        self.reranker_service = reranker_service
        self.prompt_service = prompt_service
        
        # Default system prompt
        self.default_prompt = config.get('ollama', {}).get(
            'default_system_prompt', 
            "I am going to ask you a question, which I would like you to answer based only on the provided context, and not any other information."
        )
        
        self.no_results_message = no_results_message or "I couldn't find any relevant information to answer your question."
        
        # Current system prompt ID and text - updated for each request
        self.current_prompt_id = None
        self.current_prompt_text = self.default_prompt
        
        # Language detection
        self.detector = LanguageDetector(self.verbose)
        
        # Summarization settings
        summarization_config = config.get("ollama", {}).get("summarization", {})
        self.summarization_enabled = summarization_config.get("enabled", False)
        self.summarization_model = summarization_config.get("model", self.model)
        self.max_length = summarization_config.get("max_length", 100)
        self.min_text_length = summarization_config.get("min_text_length", 200)

    async def check_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform a safety pre-clearance check on the user query.
        
        Args:
            query: The user's query
            
        Returns:
            Tuple of (is_safe, refusal_message)
        """
        if self.guardrail_service:
            return await self.guardrail_service.check_safety(query)
        logger.warning("No GuardrailService provided - skipping safety check")
        return True, None

    async def get_context(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for the user query.
        
        Args:
            query: The user's query
            **kwargs: Additional parameters like collection_name
            
        Returns:
            List of context items
        """
        # Set collection if provided
        collection_name = kwargs.get('collection_name')
        if collection_name and hasattr(self.retriever, "set_collection"):
            await self.retriever.set_collection(collection_name)
            
        # Retrieve context
        context = await self.retriever.get_relevant_context(query)
        
        # Apply reranking if available
        if self.reranker_service and context:
            try:
                if self.verbose:
                    original_scores = [item.get("confidence", 0) for item in context]
                    logger.info(f"Applying reranking to {len(context)} documents, original scores: {original_scores}")
                
                reranked_context = await self.reranker_service.rerank(query, context)
                
                if not isinstance(reranked_context, list) or not reranked_context:
                    logger.warning("Reranker returned invalid or empty result; using original context")
                    return context
                    
                valid_items = [item for item in reranked_context if isinstance(item, dict) and "content" in item]
                
                if not valid_items:
                    logger.warning("No valid items found in reranked context; using original context")
                    return context
                    
                if self.verbose:
                    new_scores = [item.get("confidence", 0) for item in valid_items]
                    logger.info(f"Reranking complete, new confidence scores: {new_scores}")
                
                return valid_items
            
            except Exception as e:
                logger.error(f"Error in reranking: {str(e)}; using original context")
                
        return context

    async def set_system_prompt(self, prompt_id: Optional[ObjectId] = None) -> None:
        """
        Set the system prompt to use for the current request.
        
        Args:
            prompt_id: The ObjectId of the system prompt to use, if None use default prompt
        """
        # Reset to default
        self.current_prompt_text = self.default_prompt
        self.current_prompt_id = None
        
        # If no prompt ID or no prompt service, use default
        if not prompt_id or not self.prompt_service:
            if self.verbose:
                logger.info("Using default system prompt")
            return
        
        try:
            # Try to get the specified prompt
            prompt_doc = await self.prompt_service.get_prompt_by_id(prompt_id)
            
            if prompt_doc and "prompt" in prompt_doc:
                self.current_prompt_text = prompt_doc["prompt"]
                self.current_prompt_id = prompt_id
                if self.verbose:
                    logger.info(f"Using system prompt: {prompt_doc.get('name', str(prompt_id))}")
            else:
                logger.warning(f"System prompt with ID {prompt_id} not found, using default")
        except Exception as e:
            logger.error(f"Error setting system prompt: {str(e)}")
            logger.info("Using default system prompt due to error")

    async def create_prompt(self, query: str, context: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Create a prompt for Ollama based on the query and context.
        
        Args:
            query: The user's query
            context: Retrieved context
            
        Returns:
            Formatted prompt string
        """
        # Extract direct answer or relevant content
        chroma_response = ""
        if context:
            # Try to get direct answer
            chroma_response = self.retriever.get_direct_answer(context)
            
            # If no direct answer, use most relevant content
            if not chroma_response:
                if "answer" in context[0]:
                    chroma_response = f"Question: {context[0].get('question', '')}\nAnswer: {context[0].get('answer', '')}"
                else:
                    chroma_response = context[0].get("content", "")

        # Detect query language
        query_language = self.detector.detect(query)
        is_non_english = query_language != "en"

        if self.verbose:
            logger.info(f"Language detection result: '{query}' detected as '{query_language}'")

        # Create language instruction if needed
        language_instruction = ""
        if is_non_english:
            language_instruction = f"IMPORTANT: The user's query is in {query_language}. You MUST respond in {query_language}. "

        # Build complete prompt
        if self.summarization_enabled and len(chroma_response) >= self.min_text_length:
            if self.verbose:
                logger.info("Summarization triggered - response exceeds minimum length threshold")
                
            full_prompt = (
                f"{language_instruction}{self.current_prompt_text}\n\n"
                f"Please provide a concise, direct answer to the user's question using only the information provided. "
                f"Do not use headings like 'Summary' or 'Answer' in your response. "
                f"Read and understand the context carefully, but respond with a brief and to-the-point answer.\n\n"
                f"Context:\n{chroma_response}\n\n"
                f"User Question: {query}\n\n"
                f"Assistant:"
            )
        else:
            full_prompt = (
                f"{language_instruction}{self.current_prompt_text}\n\n"
                f"Please provide a concise, direct answer to the user's question using only the information provided. "
                f"Keep your response brief and to the point.\n\n"
                f"Context:\n{chroma_response}\n\n"
                f"User Question: {query}\n\n"
                f"Assistant:"
            )

        if self.verbose:
            logger.info("=== Full Prompt to Ollama ===")
            logger.info(full_prompt)
            logger.info("===========================")
            
        return full_prompt

    async def generate_response(
        self, 
        query: str, 
        stream: bool = True, 
        collection_name: Optional[str] = None,
        system_prompt_id: Optional[ObjectId] = None
    ) -> Generator[str, None, None]:
        """
        Generate a response using retrieved context and Ollama.
        
        Args:
            query: The user's query
            stream: Whether to stream the response
            collection_name: Optional name of the collection to use
            system_prompt_id: Optional ID of system prompt to use
            
        Yields:
            Response chunks or complete response
        """
        try:
            await self.initialize()
                
            # Set system prompt if provided
            await self.set_system_prompt(system_prompt_id)

            # Perform safety check
            is_safe, refusal_message = await self.check_safety(query)
            if not is_safe:
                yield refusal_message
                return

            # Retrieve context
            context = await self.get_context(query, collection_name=collection_name)
            if not context:
                yield self.no_results_message
                return

            # Create prompt
            prompt = await self.create_prompt(query, context)
            
            # Call Ollama API
            async for chunk in self._call_ollama_api(prompt, stream):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."