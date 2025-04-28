"""
PyTorch Inference Client
========================

This module provides a PyTorch-based inference client for running local LLM models.
It extracts the core functionality from the server-torch.py implementation and
adapts it to work within the Open Inference Server architecture.
"""

import os
import time
import asyncio
import logging
import gc
from typing import Dict, Any, Optional, List, AsyncIterator, Union
from pathlib import Path
import json
import re
from contextlib import nullcontext

import torch
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    AutoModelForCausalLM,
    PreTrainedTokenizer
)

from ..base_llm_client import BaseLLMClient

logger = logging.getLogger(__name__)

class BatchProcessor:
    """
    Handles batch processing of inference requests.
    This class manages the model, tokenizer, and request queue.
    """
    
    def __init__(self, model, tokenizer, config):
        """
        Initialize the BatchProcessor with model, tokenizer, and configuration.
        
        Args:
            model: The PyTorch model for inference
            tokenizer: The tokenizer for text processing
            config: Configuration dictionary
        """
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.device = next(model.parameters()).device  # Get model device
        
        # Extract batch settings from config
        pytorch_config = config.get('inference', {}).get('pytorch', {})
        self.max_batch_size = pytorch_config.get('max_batch_size', 1)
        self.top_p = pytorch_config.get('top_p', 0.9)
        self.top_k = pytorch_config.get('top_k', 40)
        self.temperature = pytorch_config.get('temperature', 0.7)
        self.max_tokens = pytorch_config.get('max_tokens', 1024)
        self.do_sample = pytorch_config.get('do_sample', True)
        self.use_cache = pytorch_config.get('use_cache', True)
        self.repetition_penalty = pytorch_config.get('repetition_penalty', 1.1)
        
        # Cache for recently generated responses
        self.response_cache = {}
        self.cache_max_size = pytorch_config.get('cache_size', 100)
        
        logger.info(f"BatchProcessor initialized with device: {self.device}")
        self._precompile_if_needed()
    
    def _precompile_if_needed(self):
        """
        Precompile the model for prefill phase to improve first-token latency
        if specified in the configuration.
        """
        pytorch_config = self.config.get('inference', {}).get('pytorch', {})
        if pytorch_config.get('precompile_prefill', False):
            logger.info("Precompiling model for prefill phase...")
            try:
                # Create a dummy input
                dummy_input = self.tokenizer(
                    ["Hello, how are you?"],
                    return_tensors="pt",
                    padding=True
                )
                
                # Move to correct device
                dummy_input = {k: v.to(self.device) for k, v in dummy_input.items()}
                    
                # Warm up the model with a dummy forward pass
                with torch.no_grad():
                    if self.device.type == "mps":
                        # MPS-specific handling
                        _ = self.model(**dummy_input)
                    else:
                        # CUDA/CPU handling
                        with torch.cuda.amp.autocast() if torch.cuda.is_available() else nullcontext():
                            _ = self.model(**dummy_input)
                    
                logger.info("Prefill compilation completed")
            except Exception as e:
                logger.warning(f"Could not precompile prefill: {str(e)}")
    
    async def generate_response(self, message: str, max_new_tokens: int = None, temperature: float = None) -> Dict[str, Any]:
        """
        Generate a response for the given message.
        
        Args:
            message: The input message
            max_new_tokens: Override default max tokens setting
            temperature: Override default temperature setting
            
        Returns:
            Dictionary with response text and metadata
        """
        # Use provided parameters or fallback to defaults
        max_new_tokens = max_new_tokens or self.max_tokens
        temperature = temperature or self.temperature
        
        # Check cache first (simple exact match caching)
        cache_key = f"{message}_{max_new_tokens}_{temperature}"
        if cache_key in self.response_cache:
            logger.debug("Cache hit for query")
            return {**self.response_cache[cache_key], "cache_hit": True}
        
        start_time = time.time()
        
        # Add padding if model requires special format
        formatted_prompt = f"{message}"
        
        # Run tokenization in a thread pool to avoid blocking
        tokenize_options = {
            "return_tensors": "pt",
            "padding": True,
            "truncation": True,
            "max_length": self.config.get('generation', {}).get('max_input_length', 2048)
        }
        
        # Tokenize the input
        inputs = await asyncio.to_thread(
            self.tokenizer,
            formatted_prompt,
            **tokenize_options
        )
        
        # Move inputs to device
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Configure generation parameters
        generation_config = {
            "do_sample": self.do_sample,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
            "use_cache": self.use_cache,
            "pad_token_id": self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "repetition_penalty": self.repetition_penalty,
        }
        
        # Generate response (run in thread pool)
        try:
            with torch.no_grad():
                if self.device.type == "mps":
                    # MPS-specific handling
                    outputs = await asyncio.to_thread(
                        self.model.generate,
                        **inputs,
                        **generation_config,
                        return_dict_in_generate=True,
                        output_scores=False
                    )
                else:
                    # CUDA/CPU handling with autocast
                    with torch.cuda.amp.autocast() if torch.cuda.is_available() else nullcontext():
                        outputs = await asyncio.to_thread(
                            self.model.generate,
                            **inputs,
                            **generation_config,
                            return_dict_in_generate=True,
                            output_scores=False
                        )
        except Exception as e:
            logger.error(f"Generation error: {str(e)}", exc_info=True)
            return {"error": f"Generation failed: {str(e)}"}
        
        # Process response
        output_tokens = outputs.sequences[0]
        input_length = inputs['input_ids'].shape[1]
        
        # Decode output
        generated_text = await asyncio.to_thread(
            self.tokenizer.decode,
            output_tokens[input_length:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )
        
        # Clean up response text
        response_text = self._clean_response_text(generated_text.strip())
        
        # Create result
        result = {
            "response": response_text,
            "input_tokens": input_length,
            "output_tokens": len(output_tokens) - input_length,
            "total_tokens": len(output_tokens),
            "processing_time": time.time() - start_time,
            "cache_hit": False
        }
        
        # Cache the result
        self.response_cache[cache_key] = result
        
        # Manage cache size
        if len(self.response_cache) > self.cache_max_size:
            # Remove oldest entry (first key)
            self.response_cache.pop(next(iter(self.response_cache)))
        
        return result
    
    async def generate_stream(self, message: str, max_new_tokens: int = None, temperature: float = None) -> AsyncIterator[str]:
        """
        Generate a streaming response for the given message.
        
        Args:
            message: The input message
            max_new_tokens: Override default max tokens setting
            temperature: Override default temperature setting
            
        Yields:
            Chunks of generated text
        """
        # Use provided parameters or fallback to defaults
        max_new_tokens = max_new_tokens or self.max_tokens
        temperature = temperature or self.temperature
        
        # Add padding if model requires special format
        formatted_prompt = f"{message}"
        
        # Run tokenization in a thread pool to avoid blocking
        tokenize_options = {
            "return_tensors": "pt",
            "padding": True,
            "truncation": True,
            "max_length": self.config.get('generation', {}).get('max_input_length', 2048)
        }
        
        # Tokenize the input
        inputs = await asyncio.to_thread(
            self.tokenizer,
            formatted_prompt,
            **tokenize_options
        )
        
        # Move inputs to device
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        input_ids = inputs["input_ids"]
        
        # Configure generation parameters
        generation_config = {
            "do_sample": self.do_sample,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
            "use_cache": self.use_cache,
            "pad_token_id": self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "repetition_penalty": self.repetition_penalty,
        }
        
        # For streaming, we'll generate tokens one by one
        generated_ids = input_ids
        past_key_values = None
        accumulated_text = ""
        
        # Get input length for later slicing
        input_length = input_ids.shape[1]
        
        try:
            with torch.no_grad():
                for _ in range(max_new_tokens):
                    # Prepare inputs for the next generation step
                    model_inputs = {
                        "input_ids": generated_ids[:, -1:] if past_key_values is not None else generated_ids,
                        "attention_mask": torch.ones(generated_ids.shape[0], 1, device=self.device) if past_key_values is not None else torch.ones_like(generated_ids),
                        "past_key_values": past_key_values
                    }
                    
                    # Generate next token
                    if self.device.type == "mps":
                        outputs = self.model(**model_inputs, use_cache=True)
                    else:
                        with torch.cuda.amp.autocast() if torch.cuda.is_available() else nullcontext():
                            outputs = self.model(**model_inputs, use_cache=True)
                    
                    next_token_logits = outputs.logits[:, -1, :]
                    past_key_values = outputs.past_key_values
                    
                    # Apply temperature and sampling
                    if temperature > 0:
                        next_token_logits = next_token_logits / temperature
                    
                    if self.do_sample:
                        # Apply top-k filtering
                        if self.top_k > 0:
                            indices_to_remove = next_token_logits < torch.topk(next_token_logits, self.top_k)[0][..., -1, None]
                            next_token_logits[indices_to_remove] = -float('Inf')
                        
                        # Apply top-p filtering
                        if self.top_p < 1.0:
                            sorted_logits, sorted_indices = torch.sort(next_token_logits, descending=True)
                            cumulative_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
                            
                            # Remove tokens with cumulative probability above the threshold
                            sorted_indices_to_remove = cumulative_probs > self.top_p
                            # Shift the indices to the right to keep also the first token above the threshold
                            sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
                            sorted_indices_to_remove[..., 0] = 0
                            
                            indices_to_remove = sorted_indices[sorted_indices_to_remove]
                            next_token_logits[0, indices_to_remove] = -float('Inf')
                        
                        # Sample from the filtered distribution
                        probs = torch.softmax(next_token_logits, dim=-1)
                        next_token = torch.multinomial(probs, num_samples=1)
                    else:
                        # Greedy decoding
                        next_token = torch.argmax(next_token_logits, dim=-1, keepdim=True)
                    
                    # Add the decoded token to the generated sequence
                    generated_ids = torch.cat([generated_ids, next_token], dim=-1)
                    
                    # Decode the generated tokens so far
                    current_output_ids = generated_ids[0, input_length:]
                    output_text = await asyncio.to_thread(
                        self.tokenizer.decode,
                        current_output_ids,
                        skip_special_tokens=True,
                        clean_up_tokenization_spaces=False
                    )
                    
                    # Check if output has changed enough to yield a new chunk
                    if len(output_text) > len(accumulated_text) + 1:  # At least one new character
                        new_text = output_text[len(accumulated_text):]
                        accumulated_text = output_text
                        yield new_text
                    
                    # Check for EOS token
                    if next_token.item() == self.tokenizer.eos_token_id:
                        break
        
        except Exception as e:
            logger.error(f"Streaming generation error: {str(e)}", exc_info=True)
            yield f"\nError during generation: {str(e)}"
    
    def _clean_response_text(self, text: str) -> str:
        """
        Clean and dedup the model's response text.
        
        Args:
            text: The raw model response text
            
        Returns:
            Cleaned response text
        """
        # First, check if the text is excessively repetitive and needs cleaning
        if not self._is_excessively_repetitive(text):
            return text
            
        # Detect and remove generic repeated phrases
        generic_patterns = [
            r'(I have a dream about you\.I want to be your friend\.I am a bit of a noob(?:, but)?)+',
            r'(I want to be your friend\.)+',
            r'(I am a bit of a noob(?:, but)?)+',
            r'(I\'m new to reddit(?:,| and))+',
            r'(I\'m a lurker (?:here|too)(?:,| but))+',
            r'(I\'ve been lurking for a while(?:,| but))+',
            r'(looking for a (?:good )?place to meet (?:new )?people(?:,| and))+',
            r'(I\'m not sure (?:what to do|if I should))+',
        ]
        
        # Apply generic pattern cleaning
        for pattern in generic_patterns:
            text = re.sub(pattern, lambda m: m.group(1).split('.')[0] + '.', text)
        
        # Detect and clean any repeated segments (for any pattern)
        # First, look for long repeated segments (20+ chars)
        pattern = r'(.{20,})\1+'
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) > 10:
                text = text.replace(match * 2, match)
                text = text.replace(match * 3, match)
                text = text.replace(match * 4, match)
        
        # Look for medium repeated segments (10-19 chars)
        pattern = r'(.{10,19})\1{2,}'
        matches = re.findall(pattern, text)
        for match in matches:
            text = text.replace(match * 3, match)
            text = text.replace(match * 2, match)
        
        # Look for direct repeating sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        unique_sentences = []
        for sentence in sentences:
            if sentence and sentence not in unique_sentences:
                unique_sentences.append(sentence)
            elif sentence and len(unique_sentences) >= 1 and sentence in unique_sentences[-1]:
                # Skip this sentence as it's a repeat or substring of the previous one
                continue
        
        # Rebuild text from unique sentences
        text = " ".join(unique_sentences)
        
        # Remove any triple+ repetitions of shorter phrases (using the word-level algorithm)
        words = text.split()
        deduped_words = []
        
        i = 0
        while i < len(words):
            deduped_words.append(words[i])
            # Check for repeating pattern of 1-6 words
            for pattern_len in range(1, 7):
                if i + pattern_len < len(words):
                    pattern = words[i:i+pattern_len]
                    repetitions = 1
                    
                    # Count repetitions
                    j = i + pattern_len
                    while j + pattern_len <= len(words) and words[j:j+pattern_len] == pattern:
                        repetitions += 1
                        j += pattern_len
                    
                    # Skip the repetitions (keep only one instance)
                    if repetitions > 2:
                        i = j - pattern_len
                        break
            i += 1
        
        # Rebuild text from deduped words
        deduped_text = " ".join(deduped_words)
        
        # Make sure we're not losing too much content
        # If we've lost more than 60% of content, it might be over-deduping
        if len(deduped_text) < len(text) * 0.4:
            # If text is very long, assume we need the deduplication
            if len(text) > 500:
                return deduped_text
            else:
                # For shorter texts, some duplication might be intentional
                return text
        
        return deduped_text
    
    def _is_excessively_repetitive(self, text: str) -> bool:
        """
        Check if text has excessive repetition patterns.
        
        Args:
            text: The text to check
            
        Returns:
            True if the text contains excessive repetition
        """
        # Check for repeated phrases (more than 3 times)
        words = text.split()
        if len(words) < 20:
            return False
            
        # Check for repeated sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        unique_sentences = set(sentences)
        
        # If we have many sentences but few unique ones, it's repetitive
        if len(sentences) > 5 and len(unique_sentences) < len(sentences) * 0.7:
            return True
        
        # Check for repeated phrases within the text
        for length in range(3, 8):  # Look for phrases of 3-7 words
            for i in range(len(words) - length):
                phrase = ' '.join(words[i:i+length])
                # Count occurrences but exclude the first one
                remaining_text = ' '.join(words[i+length:])
                if remaining_text.count(phrase) > 1:
                    return True
                    
        return False

class PyTorchClient(BaseLLMClient):
    """
    PyTorch-based LLM Client implementation.
    
    This client initializes and manages a local PyTorch model for text generation,
    providing both standard and streaming inference endpoints.
    """
    
    def __init__(
        self, 
        config: Dict[str, Any], 
        retriever=None,
        guardrail_service=None,
        reranker_service=None,
        prompt_service=None,
        no_results_message: str = "",
        **kwargs
    ):
        """
        Initialize the PyTorch LLM client.
        
        Args:
            config: Configuration dictionary
            retriever: Optional retriever for RAG
            guardrail_service: Optional service for content safety checks
            reranker_service: Optional service for reranking results
            prompt_service: Optional service for system prompts
            no_results_message: Message to show when no results are found
            **kwargs: Additional arguments
        """
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        self.model = None
        self.tokenizer = None
        self.batch_processor = None
        
        # Extract configuration for PyTorch
        self.pytorch_config = self.config.get('inference', {}).get('pytorch', {})
        self.model_id = self.pytorch_config.get('model_path', 'facebook/opt-350m')
        
        self.device = self._determine_device()
        logger.info(f"Using device: {self.device}")
        
        self.system_prompt = self.pytorch_config.get('system_prompt', 
                                                   "You are a helpful, accurate, precise, and expert assistant.")
        
        # Initialize log directories
        log_dir = Path(self.config.get('logging', {}).get('file', {}).get('directory', 'logs'))
        log_dir.mkdir(exist_ok=True)
        
    def _determine_device(self) -> torch.device:
        """
        Determine the best available PyTorch device.
        
        Returns:
            torch.device: The device to use
        """
        if torch.cuda.is_available():
            return torch.device("cuda")
        # Check for MPS (Apple Silicon)
        if hasattr(torch, 'mps') and torch.backends.mps.is_available() and self.pytorch_config.get('use_mps', True):
            return torch.device("mps")
        return torch.device("cpu")

    async def initialize(self) -> bool:
        """
        Initialize the PyTorch model and tokenizer.
        
        Returns:
            bool: True if successful
        """
        try:
            logger.info(f"Initializing PyTorch LLM client with model: {self.model_id}")
            
            # Free up memory before loading model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
            
            # Load tokenizer first
            tokenizer_options = {
                "use_fast": self.pytorch_config.get('use_fast_tokenizer', True),
                "padding_side": self.pytorch_config.get('padding_side', 'left'),
                "truncation_side": self.pytorch_config.get('truncation_side', 'left'),
                "trust_remote_code": self.pytorch_config.get('trust_remote_code', True),
            }
            
            # Check if there's a Hugging Face token in env
            hf_token = os.environ.get("HUGGING_FACE_HUB_TOKEN")
            if hf_token:
                tokenizer_options["token"] = hf_token
            
            logger.info(f"Loading tokenizer for model: {self.model_id}")
            # Load tokenizer asynchronously
            self.tokenizer = await asyncio.to_thread(
                AutoTokenizer.from_pretrained,
                self.model_id,
                **tokenizer_options
            )
            
            # Ensure we have a pad token
            if self.tokenizer.pad_token is None:
                if self.tokenizer.eos_token is not None:
                    self.tokenizer.pad_token = self.tokenizer.eos_token
                    logger.info("Setting pad_token to eos_token")
                else:
                    # Last resort
                    logger.warning("Setting default pad token as model has no eos token")
                    self.tokenizer.pad_token = self.tokenizer.unk_token or "<pad>"
                    
            logger.info(f"Tokenizer loaded successfully. Vocab size: {len(self.tokenizer)}")
            
            # Configure model loading parameters
            model_kwargs = {}
            
            # Add Hugging Face token if available
            if hf_token:
                model_kwargs["token"] = hf_token
            
            # Handle device mapping
            if self.device.type == "mps":
                # MPS-specific settings
                model_kwargs["device_map"] = None  # Don't use device_map with MPS
                model_kwargs["torch_dtype"] = torch.float32  # Use float32 for better MPS compatibility
            else:
                # For CUDA/CPU, load in appropriate precision
                model_kwargs["torch_dtype"] = torch.float16 if self.device.type == "cuda" else torch.float32
                
                # Setup quantization if enabled (only for CUDA)
                if self.device.type == "cuda" and self.pytorch_config.get('load_in_8bit', False):
                    logger.info("Loading model in 8-bit quantization")
                    model_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_8bit=True,
                        llm_int8_threshold=self.pytorch_config.get('int8_threshold', 6.0),
                        llm_int8_has_fp16_weight=self.pytorch_config.get('int8_has_fp16_weight', True)
                    )
                elif self.device.type == "cuda" and self.pytorch_config.get('load_in_4bit', False):
                    logger.info("Loading model in 4-bit quantization")
                    compute_dtype = torch.float16 if self.pytorch_config.get('compute_dtype', 'float16') == 'float16' else torch.float32
                    model_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=compute_dtype,
                        bnb_4bit_use_double_quant=self.pytorch_config.get('use_double_quant', True),
                        bnb_4bit_quant_type=self.pytorch_config.get('quant_type', 'nf4')
                    )
            
            # Load the model asynchronously
            logger.info(f"Loading model: {self.model_id}")
            self.model = await asyncio.to_thread(
                AutoModelForCausalLM.from_pretrained,
                self.model_id,
                trust_remote_code=self.pytorch_config.get('trust_remote_code', True),
                **model_kwargs
            )
            
            # Move model to device if not using device_map
            if model_kwargs.get("device_map") is None and not (
                self.pytorch_config.get('load_in_8bit', False) or 
                self.pytorch_config.get('load_in_4bit', False)
            ):
                logger.info(f"Moving model to {self.device}")
                self.model = await asyncio.to_thread(self.model.to, self.device)
            
            # Create batch processor
            self.batch_processor = BatchProcessor(self.model, self.tokenizer, self.config)
            
            # Log memory usage
            if self.device.type == "cuda":
                mem_allocated = torch.cuda.memory_allocated() / 1e9
                mem_reserved = torch.cuda.memory_reserved() / 1e9
                logger.info(f"Model loaded on CUDA. Memory allocated: {mem_allocated:.2f}GB, Reserved: {mem_reserved:.2f}GB")
            
            logger.info("PyTorch LLM model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize PyTorch LLM client: {str(e)}", exc_info=True)
            return False

    async def verify_connection(self) -> bool:
        """
        Verify that the model is loaded and working.
        
        Returns:
            bool: True if the model is working
        """
        if self.model is None or self.tokenizer is None or self.batch_processor is None:
            return False
            
        try:
            # Try a simple inference request
            test_result = await self.batch_processor.generate_response("Hello, can you hear me?", max_new_tokens=10)
            if "error" in test_result:
                logger.error(f"Verification failed: {test_result['error']}")
                return False
            return True
        except Exception as e:
            logger.error(f"Connection verification failed: {str(e)}")
            return False

    async def get_llm_response(self, 
                         prompt: str, 
                         system_prompt: Optional[str] = None, 
                         temperature: Optional[float] = None,
                         max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        Get a response from the LLM for the given prompt.
        
        Args:
            prompt: The input prompt
            system_prompt: Optional system prompt override
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            
        Returns:
            Dictionary containing the response and metadata
        """
        if self.model is None or self.tokenizer is None or self.batch_processor is None:
            return {"error": "PyTorch model not loaded"}
        
        # Use provided system prompt or default
        system_prompt_text = system_prompt if system_prompt else self.system_prompt
        
        # Format the prompt with the system prompt
        formatted_prompt = f"{system_prompt_text}\n\n{prompt}"
        
        result = await self.batch_processor.generate_response(
            formatted_prompt, 
            max_new_tokens=max_tokens,
            temperature=temperature
        )
        
        if "error" in result:
            return result
        
        return {
            "text": result["response"],
            "tokens": {
                "prompt": result["input_tokens"],
                "completion": result["output_tokens"],
                "total": result["total_tokens"]
            },
            "model": self.model_id,
            "finish_reason": "stop",
            "processing_time": result["processing_time"]
        }

    async def get_chat_response(self, 
                          messages: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None,
                          temperature: Optional[float] = None,
                          max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        Get a response from the LLM for the given chat messages.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            system_prompt: Optional system prompt override
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            
        Returns:
            Dictionary containing the response and metadata
        """
        if self.model is None or self.tokenizer is None or self.batch_processor is None:
            return {"error": "PyTorch model not loaded"}
        
        # Use provided system prompt or default
        system_prompt_text = system_prompt if system_prompt else self.system_prompt
        
        # Format the messages into a prompt
        prompt_parts = [system_prompt_text]
        
        for message in messages:
            role = message.get("role", "user").lower()
            content = message.get("content", "")
            
            if role == "system":
                # Add system messages directly
                prompt_parts.append(f"{content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            else:
                # Handle any other roles as generic
                prompt_parts.append(f"{role.capitalize()}: {content}")
        
        # End with "Assistant:" to prompt the model to generate a response
        prompt_parts.append("Assistant:")
        
        # Join into a single prompt string
        formatted_prompt = "\n\n".join(prompt_parts)
        
        result = await self.batch_processor.generate_response(
            formatted_prompt, 
            max_new_tokens=max_tokens,
            temperature=temperature
        )
        
        if "error" in result:
            return result
        
        return {
            "text": result["response"],
            "tokens": {
                "prompt": result["input_tokens"],
                "completion": result["output_tokens"],
                "total": result["total_tokens"]
            },
            "model": self.model_id,
            "finish_reason": "stop",
            "processing_time": result["processing_time"]
        }

    async def get_streaming_response(self, 
                               prompt: str, 
                               system_prompt: Optional[str] = None,
                               temperature: Optional[float] = None,
                               max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        """
        Get a streaming response from the LLM.
        
        Args:
            prompt: The input prompt
            system_prompt: Optional system prompt override
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            
        Yields:
            Chunks of the generated response
        """
        if self.model is None or self.tokenizer is None or self.batch_processor is None:
            yield json.dumps({"error": "PyTorch model not loaded"})
            return
        
        # Use provided system prompt or default
        system_prompt_text = system_prompt if system_prompt else self.system_prompt
        
        # Format the prompt with the system prompt
        formatted_prompt = f"{system_prompt_text}\n\n{prompt}"
        
        total_response = ""
        async for chunk in self.batch_processor.generate_stream(
            formatted_prompt,
            max_new_tokens=max_tokens,
            temperature=temperature
        ):
            total_response += chunk
            yield json.dumps({"text": total_response, "done": False})
        
        # Final chunk
        yield json.dumps({"text": total_response, "done": True})

    async def get_streaming_chat_response(self, 
                                    messages: List[Dict[str, str]], 
                                    system_prompt: Optional[str] = None,
                                    temperature: Optional[float] = None,
                                    max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        """
        Get a streaming chat response from the LLM.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            system_prompt: Optional system prompt override
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            
        Yields:
            Chunks of the generated response
        """
        if self.model is None or self.tokenizer is None or self.batch_processor is None:
            yield json.dumps({"error": "PyTorch model not loaded"})
            return
        
        # Use provided system prompt or default
        system_prompt_text = system_prompt if system_prompt else self.system_prompt
        
        # Format the messages into a prompt
        prompt_parts = [system_prompt_text]
        
        for message in messages:
            role = message.get("role", "user").lower()
            content = message.get("content", "")
            
            if role == "system":
                # Add system messages directly
                prompt_parts.append(f"{content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            else:
                # Handle any other roles as generic
                prompt_parts.append(f"{role.capitalize()}: {content}")
        
        # End with "Assistant:" to prompt the model to generate a response
        prompt_parts.append("Assistant:")
        
        # Join into a single prompt string
        formatted_prompt = "\n\n".join(prompt_parts)
        
        total_response = ""
        async for chunk in self.batch_processor.generate_stream(
            formatted_prompt,
            max_new_tokens=max_tokens,
            temperature=temperature
        ):
            total_response += chunk
            yield json.dumps({"text": total_response, "done": False})
        
        # Final chunk
        yield json.dumps({"text": total_response, "done": True})

    async def close(self) -> None:
        """Release resources and clean up."""
        logger.info("Cleaning up PyTorch LLM client resources")
        
        if self.model is not None:
            # Clear CUDA cache
            self.model.cpu()  # Move model to CPU first
            del self.model
            self.model = None
        
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        
        if self.batch_processor is not None:
            del self.batch_processor
            self.batch_processor = None
            
        # Force garbage collection
        gc.collect()
        
        # Clear CUDA cache if available
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    async def generate_response(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate a response for the given prompt.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            Dictionary containing the response and metadata
        """
        if self.model is None or self.tokenizer is None:
            return {"error": "Model not initialized"}
            
        try:
            # Tokenize input
            inputs = self.tokenizer(prompt, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate response
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=kwargs.get('max_tokens', 100),
                    temperature=kwargs.get('temperature', 0.7),
                    top_p=kwargs.get('top_p', 0.9),
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Decode response
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            return {
                "text": response,
                "tokens": {
                    "prompt": inputs["input_ids"].shape[1],
                    "completion": outputs.shape[1] - inputs["input_ids"].shape[1],
                    "total": outputs.shape[1]
                },
                "model": self.model_id,
                "finish_reason": "stop"
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Generation failed: {str(e)}"}

    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            Dictionary containing response and metadata
        """
        if self.model is None or self.tokenizer is None:
            return {"error": "Model not initialized"}
            
        try:
            # Get context from retriever
            context = ""
            sources = []
            
            if self.retriever:
                # Get context from retriever
                documents = await self.retriever.get_relevant_documents(message, collection_name)
                
                if documents:
                    # Format context for prompt
                    context = self._format_context(documents)
                    sources = self._format_sources(documents)
            
            # Get system prompt if provided
            system_prompt = ""
            if system_prompt_id and self.prompt_service:
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc:
                    system_prompt = prompt_doc.get('prompt', '')
            
            # Use default system prompt if no custom one is provided
            if not system_prompt:
                system_prompt = self.system_prompt
            
            # Create full prompt with context
            full_prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion: {message}\n\nAnswer:"
            
            # Tokenize input
            inputs = self.tokenizer(full_prompt, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate response
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=self.pytorch_config.get('max_tokens', 1024),
                    temperature=self.pytorch_config.get('temperature', 0.7),
                    top_p=self.pytorch_config.get('top_p', 0.9),
                    do_sample=self.pytorch_config.get('do_sample', True),
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Decode response
            response = self.tokenizer.decode(outputs[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            
            return {
                "response": response,
                "sources": sources,
                "tokens": {
                    "prompt": inputs["input_ids"].shape[1],
                    "completion": outputs.shape[1] - inputs["input_ids"].shape[1],
                    "total": outputs.shape[1]
                },
                "model": self.model_id,
                "finish_reason": "stop"
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Generation failed: {str(e)}"}

    async def generate_response_stream(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Generate a streaming response for a chat message.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Yields:
            Chunks of the response as they are generated
        """
        if self.model is None or self.tokenizer is None:
            yield json.dumps({"error": "Model not initialized"})
            return
            
        try:
            # Get context from retriever
            context = ""
            sources = []
            
            if self.retriever:
                # Get context from retriever
                documents = await self.retriever.get_relevant_context(message, collection_name)
                
                if documents:
                    # Format context for prompt
                    context = self._format_context(documents)
                    sources = self._format_sources(documents)
            
            # Get system prompt if provided
            system_prompt = ""
            if system_prompt_id and self.prompt_service:
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc:
                    system_prompt = prompt_doc.get('prompt', '')
            
            # Use default system prompt if no custom one is provided
            if not system_prompt:
                system_prompt = self.system_prompt
            
            # Create full prompt with context
            full_prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion: {message}\n\nAnswer:"
            
            # Tokenize input
            inputs = self.tokenizer(full_prompt, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate response token by token
            input_length = inputs["input_ids"].shape[1]
            generated_text = ""
            
            # Send sources as first chunk if available
            if sources:
                yield json.dumps({"sources": sources})
            
            # Generate with streaming
            with torch.no_grad():
                output_ids = inputs["input_ids"].clone()
                past_key_values = None
                
                for _ in range(self.pytorch_config.get('max_tokens', 1024)):
                    # Prepare inputs for the next generation step
                    if past_key_values is None:
                        # First step - use full sequence
                        model_inputs = {
                            "input_ids": output_ids,
                            "attention_mask": torch.ones_like(output_ids),
                            "past_key_values": None
                        }
                    else:
                        # Subsequent steps - only use the last token
                        model_inputs = {
                            "input_ids": output_ids[:, -1:],
                            "attention_mask": torch.ones(output_ids.shape[0], 1, device=self.device),
                            "past_key_values": past_key_values
                        }
                    
                    # Generate next token
                    outputs = self.model(**model_inputs, use_cache=True)
                    past_key_values = outputs.past_key_values
                    
                    next_token_logits = outputs.logits[:, -1, :]
                    
                    # Apply temperature
                    temperature = self.pytorch_config.get('temperature', 0.7)
                    if temperature > 0:
                        next_token_logits = next_token_logits / temperature
                    
                    # Sample next token
                    if self.pytorch_config.get('do_sample', True):
                        probs = torch.softmax(next_token_logits, dim=-1)
                        next_token = torch.multinomial(probs, num_samples=1)
                    else:
                        next_token = torch.argmax(next_token_logits, dim=-1, keepdim=True)
                    
                    # Add new token to sequence
                    output_ids = torch.cat([output_ids, next_token], dim=-1)
                    
                    # Decode only new token
                    new_token = self.tokenizer.decode(next_token[0], skip_special_tokens=True)
                    generated_text += new_token
                    
                    # Yield current response
                    if new_token.strip():  # Only yield if token isn't just whitespace
                        yield json.dumps({"response": generated_text})
                    
                    # Check if we hit the end token
                    if next_token.item() == self.tokenizer.eos_token_id:
                        break
            
            # Yield final message with done flag
            yield json.dumps({"response": generated_text, "done": True})
            
        except Exception as e:
            logger.error(f"Error in streaming generation: {str(e)}")
            yield json.dumps({"error": f"Streaming generation failed: {str(e)}"})