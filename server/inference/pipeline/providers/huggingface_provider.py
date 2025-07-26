"""
Hugging Face Provider for Pipeline Architecture

This module provides a clean Hugging Face implementation for the pipeline architecture.
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class HuggingFaceProvider(LLMProvider):
    """
    Clean Hugging Face implementation for the pipeline architecture.
    
    This provider uses Hugging Face Transformers for local model inference
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Hugging Face provider.
        
        Args:
            config: Configuration dictionary containing Hugging Face settings
        """
        self.config = config
        hf_config = config.get("inference", {}).get("huggingface", {})
        
        self.model_name = hf_config.get("model_name", "gpt2")
        self.device = hf_config.get("device", "auto")  # Will be resolved to cuda/cpu in initialize
        self.max_length = hf_config.get("max_length", 1024)
        self.temperature = hf_config.get("temperature", 0.7)
        self.top_p = hf_config.get("top_p", 0.9)
        self.top_k = hf_config.get("top_k", 50)
        self.do_sample = hf_config.get("do_sample", True)
        
        self.model = None
        self.tokenizer = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Hugging Face provider."""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            # Resolve device if set to auto
            if self.device == "auto":
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            
            if self.verbose:
                self.logger.info(f"Loading Hugging Face model: {self.model_name} on {self.device}")
            
            # Load model and tokenizer in a thread to avoid blocking
            def _load_model():
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model = AutoModelForCausalLM.from_pretrained(self.model_name).to(self.device)
                model.eval()
                
                # Ensure tokenizer has padding token
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token
                
                return model, tokenizer
            
            self.model, self.tokenizer = await asyncio.to_thread(_load_model)
            
            self.logger.info(f"Initialized Hugging Face provider with model: {self.model_name}")
            
        except ImportError:
            self.logger.error("torch and transformers packages not installed. Please install with: pip install torch transformers")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Hugging Face model: {str(e)}")
            raise
    
    def _build_prompt(self, prompt: str) -> str:
        """
        Build prompt in the format expected by Hugging Face models.
        
        Args:
            prompt: The input prompt
            
        Returns:
            Formatted prompt string
        """
        # Extract system prompt and user message if present
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                # Build conversational format
                formatted_parts = []
                if system_part:
                    formatted_parts.append(f"System: {system_part}")
                formatted_parts.append(f"User: {user_part}")
                formatted_parts.append("Assistant:")
                
                return "\n".join(formatted_parts)
        
        # If no clear separation, add Assistant: prompt at the end
        if not prompt.endswith("Assistant:"):
            return f"{prompt}\nAssistant:"
        return prompt
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Hugging Face.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.model:
            await self.initialize()
        
        try:
            import torch
            
            # Build prompt
            formatted_prompt = self._build_prompt(prompt)
            
            if self.verbose:
                self.logger.debug(f"Generating with Hugging Face: model={self.model_name}, temperature={self.temperature}")
            
            # Generate response in a thread to avoid blocking
            def _generate():
                inputs = self.tokenizer(
                    formatted_prompt, 
                    return_tensors="pt", 
                    padding=True, 
                    truncation=True
                ).to(self.device)
                
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_length=inputs["input_ids"].shape[1] + kwargs.get("max_tokens", self.max_length),
                        temperature=kwargs.get("temperature", self.temperature),
                        top_p=kwargs.get("top_p", self.top_p),
                        top_k=kwargs.get("top_k", self.top_k),
                        do_sample=kwargs.get("do_sample", self.do_sample),
                        pad_token_id=self.tokenizer.pad_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                        **{k: v for k, v in kwargs.items() if k not in ["max_tokens", "temperature", "top_p", "top_k", "do_sample"]}
                    )
                
                # Extract only the generated part (excluding the input prompt)
                generated = outputs[0][inputs["input_ids"].shape[1]:]
                return self.tokenizer.decode(generated, skip_special_tokens=True)
            
            response_text = await asyncio.to_thread(_generate)
            
            return response_text.strip()
            
        except Exception as e:
            self.logger.error(f"Error generating response with Hugging Face: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Hugging Face.
        
        Note: Hugging Face doesn't have native streaming, so we simulate it
        by generating the full response and yielding it as one chunk.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        try:
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Hugging Face (simulated)")
            
            # Generate the full response
            response_text = await self.generate(prompt, **kwargs)
            
            # Yield the full response as a single chunk
            # In a real streaming implementation, this would be broken into smaller chunks
            yield response_text
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Hugging Face: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Hugging Face provider."""
        try:
            if self.model is not None:
                del self.model
                self.model = None
            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None
            
            # Clear CUDA cache if using GPU
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            
            self.logger.info("Hugging Face provider closed")
        except Exception as e:
            self.logger.error(f"Error closing Hugging Face provider: {str(e)}")
    
    async def validate_config(self) -> bool:
        """
        Validate the Hugging Face configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.model_name:
                self.logger.error("Hugging Face model_name is missing")
                return False
            
            # Test model loading with a simple request
            if not self.model:
                await self.initialize()
            
            # Validate with a minimal test
            test_response = await self.generate("test", max_tokens=5)
            
            if self.verbose:
                self.logger.info("Hugging Face configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("torch and transformers packages not installed")
            return False
        except Exception as e:
            self.logger.error(f"Hugging Face configuration validation failed: {str(e)}")
            return False