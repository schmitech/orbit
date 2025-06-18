import json
import time
import logging
import os
from typing import Dict, List, Any, Optional, AsyncGenerator

from together import AsyncTogether

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class TogetherAIClient(BaseLLMClient, LLMClientCommon):
    '''LLM client implementation for Together.ai using the official Python package.'''
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, reranker_service, prompt_service, no_results_message)

        # Get Together.ai specific configuration
        together_config = config.get('inference', {}).get('together', {})

        self.api_key = os.getenv('TOGETHER_API_KEY', together_config.get('api_key', ''))
        if not self.api_key:
            raise ValueError("TOGETHER_API_KEY environment variable or api_key in config is required")
            
        self.api_base = together_config.get('api_base', 'https://api.together.xyz/v1')
        self.model = together_config.get('model', 'together-llama-3-8b-8192')
        self.temperature = together_config.get('temperature', 0.1)
        self.top_p = together_config.get('top_p', 0.8)
        self.max_tokens = together_config.get('max_tokens', 1024)
        self.stream = together_config.get('stream', True)
        self.show_thinking = together_config.get('show_thinking', False)
        self.verbose = config.get('general', {}).get('verbose', False)

        self.client = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        '''Initialize the Together.ai client using the official package.'''
        try:
            if not self.api_key:
                raise ValueError("TOGETHER_API_KEY is not set")
                
            self.client = AsyncTogether(
                api_key=self.api_key,
                base_url=self.api_base
            )
            
            # Test the connection immediately
            await self.verify_connection()
            
            self.logger.info(f'Successfully initialized Together.ai client with base_url {self.api_base} and model {self.model}')
        except ImportError:
            self.logger.error('together package not installed. Please install with: pip install together')
            raise
        except Exception as e:
            self.logger.error(f'Error initializing Together.ai client: {str(e)}')
            raise

    async def verify_connection(self) -> bool:
        '''Verify that the connection to Together.ai is working.'''
        try:
            if not self.client:
                await self.initialize()
                
            # Try a simple completion request as a connection test
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': 'You are a helpful assistant.'},
                    {'role': 'user', 'content': 'Ping'}
                ],
                max_tokens=10
            )
            
            if not response or not response.choices:
                raise Exception("No response received from Together AI")
                
            return True
        except Exception as e:
            self.logger.error(f'Error connecting to Together.ai API: {str(e)}')
            return False

    async def close(self) -> None:
        '''Clean up resources.'''
        try:
            if self.client and hasattr(self.client, 'close'):
                await self.client.close()
                self.logger.info('Closed Together.ai client session')
        except Exception as e:
            self.logger.error(f'Error closing Together.ai client: {str(e)}')
        self.logger.info('Together.ai client resources released')

    def _clean_response(self, text: str) -> str:
        '''Remove thinking process from response if show_thinking is False.'''
        if not self.show_thinking:
            # Remove content between <think> tags
            import re
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            # Clean up any extra whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = text.strip()
            # Remove any remaining thinking tags
            text = text.replace('<think>', '').replace('</think>', '')
        return text

    async def generate_response(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        '''Generate a response using Together.ai.'''
        retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
        system_prompt = await self._get_system_prompt(system_prompt_id)
        context = self._format_context(retrieved_docs)

        # If no context was found, return the default no-results message
        if context is None:
            no_results_message = self.config.get('messages', {}).get('no_results_response', 
                "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")
            return {
                "response": no_results_message,
                "sources": [],
                "tokens": 0,
                "processing_time": 0
            }

        if not self.client:
            await self.initialize()

        # Prepare messages for the API call
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add context messages if provided
        if context_messages:
            messages.extend(context_messages)
        
        # Add the current message with context
        messages.append({
            "role": "user", 
            "content": f"Context information:\n{context}\n\nUser Query: {message}"
        })

        start_time = time.time()
        try:
            params = {
                'model': self.model,
                'messages': messages,
                'max_tokens': self.max_tokens,
                'temperature': self.temperature,
                'top_p': self.top_p
            }

            response = await self.client.chat.completions.create(**params)
            processing_time = self._measure_execution_time(start_time)
            text = self._clean_response(response.choices[0].message.content)
            sources = self._format_sources(retrieved_docs)
            tokens = {
                'prompt': response.usage.prompt_tokens,
                'completion': response.usage.completion_tokens,
                'total': response.usage.total_tokens
            }
            return {
                'response': text,
                'sources': sources,
                'tokens': tokens['total'],
                'token_usage': tokens,
                'processing_time': processing_time
            }
        except Exception as e:
            self.logger.error(f'Error generating response from Together.ai: {str(e)}')
            raise

    async def generate_response_stream(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        '''Generate a streaming response using Together.ai.'''
        retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
        system_prompt = await self._get_system_prompt(system_prompt_id)
        context = self._format_context(retrieved_docs)

        # If no context was found, return the default no-results message
        if context is None:
            no_results_message = self.config.get('messages', {}).get('no_results_response', 
                "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")
            yield json.dumps({
                "response": no_results_message,
                "sources": [],
                "done": True
            })
            return

        if not self.client:
            await self.initialize()

        # Prepare messages for the API call
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add context messages if provided
        if context_messages:
            messages.extend(context_messages)
        
        # Add the current message with context
        messages.append({
            "role": "user", 
            "content": f"Context information:\n{context}\n\nUser Query: {message}"
        })

        try:
            params = {
                'model': self.model,
                'messages': messages,
                'max_tokens': self.max_tokens,
                'temperature': self.temperature,
                'top_p': self.top_p,
                'stream': True
            }

            response_stream = await self.client.chat.completions.create(**params)
            chunk_count = 0
            sources = self._format_sources(retrieved_docs)
            current_chunk = ""
            in_thinking_block = False
            
            async for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    chunk_count += 1
                    content = chunk.choices[0].delta.content
                    current_chunk += content
                    
                    # Check if we're entering or exiting a thinking block
                    if '<think>' in content:
                        in_thinking_block = True
                    if '</think>' in content:
                        in_thinking_block = False
                        continue
                        
                    # Only yield content if we're not in a thinking block or show_thinking is True
                    if self.show_thinking or not in_thinking_block:
                        response_data = {
                            'response': content,
                            'sources': [] if chunk_count > 1 else sources,
                            'done': False
                        }
                        yield json.dumps(response_data)
            
            # Clean up any remaining thinking content
            if not self.show_thinking:
                current_chunk = self._clean_response(current_chunk)
            
            # Send final message with sources
            final_response = {
                'response': '',
                'sources': sources,
                'done': True
            }
            yield json.dumps(final_response)
            
        except Exception as e:
            self.logger.error(f'Error generating streaming response from Together.ai: {str(e)}')
            error_response = {
                'error': str(e),
                'done': True
            }
            yield json.dumps(error_response)
