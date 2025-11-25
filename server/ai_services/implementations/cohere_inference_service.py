"""
Cohere inference service implementation using unified architecture.

This is a migrated version of the Cohere inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/cohere_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import CohereBaseService
from ..services import InferenceService


class CohereInferenceService(InferenceService, CohereBaseService):
    """
    Cohere inference service using unified architecture.

    Old implementation: ~267 lines (cohere_provider.py)
    New implementation: ~90 lines
    Reduction: ~66%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Cohere inference service."""
        # Initialize via InferenceService which will cooperate with CohereBaseService
        InferenceService.__init__(self, config, "cohere")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)

    def _get_temperature(self, default: float = 0.7) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 1024) -> int:
        """Get max_tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _parse_prompt(self, prompt: str) -> tuple[str, str]:
        """
        Parse prompt to extract system context and user message.
        
        This handles prompts that include conversation formatting like:
        "System prompt/context...\nUser: question\nAssistant:"
        
        Args:
            prompt: The full prompt string
            
        Returns:
            Tuple of (system_context, user_message)
            - system_context: Everything before "User:" (or empty if no "User:" label)
            - user_message: Content after "User:" with "Assistant:" removed
        """
        # If prompt contains "User:" label, split into system and user parts
        if "\nUser:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_context = parts[0].strip()
                # Extract user content and remove "Assistant:" label if present
                user_content = parts[1].replace("Assistant:", "").strip()
                return system_context, user_content
        
        # If no "User:" label, treat entire prompt as user message
        return "", prompt.strip()

    def _clean_response(self, text: str) -> str:
        """
        Clean response text by removing unwanted formatting.
        
        Removes:
        - "User:" and "Assistant:" labels that might be included in response
        - Repeated user questions
        - Extra formatting prefixes like "Certainly! Here's..."
        
        Args:
            text: Raw response text
            
        Returns:
            Cleaned response text
        """
        if not text:
            return text
        
        lines = text.split('\n')
        cleaned_lines = []
        skip_until_assistant = False
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Skip empty lines at the start
            if not cleaned_lines and not line_stripped:
                continue
            
            # Detect pattern: "Certainly! Here's..." followed by "User:" question
            if not cleaned_lines and any(line_stripped.startswith(prefix) for prefix in 
                                        ["Certainly!", "Here's", "Here is"]):
                # Check if next lines contain "User:" - if so, skip this prefix
                if i + 1 < len(lines) and "User:" in lines[i + 1]:
                    skip_until_assistant = True
                    continue
            
            # Skip lines until we find "Assistant:" or actual content
            if skip_until_assistant:
                if "Assistant:" in line_stripped:
                    skip_until_assistant = False
                    # Remove "Assistant:" label and continue
                    cleaned_line = line_stripped.replace("Assistant:", "").strip()
                    if cleaned_line:
                        cleaned_lines.append(cleaned_line)
                    continue
                elif "User:" in line_stripped:
                    # Skip user question repetition
                    continue
                else:
                    # If we hit content without "Assistant:", stop skipping
                    skip_until_assistant = False
            
            # Remove "User:" lines that appear in the middle of response
            if "User:" in line_stripped and cleaned_lines:
                # This is likely a repeated user question, skip it
                continue
            
            # Remove "Assistant:" label if present
            if line_stripped.startswith("Assistant:"):
                cleaned_line = line_stripped.replace("Assistant:", "").strip()
                if cleaned_line:
                    cleaned_lines.append(cleaned_line)
            elif line_stripped:
                cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        # Final cleanup: remove leading "Assistant:" if still present
        if result.startswith("Assistant:"):
            result = result.replace("Assistant:", "", 1).strip()
        
        return result

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Cohere."""
        if not self.initialized:
            await self.initialize()

        try:
            # Check API version and use appropriate format
            if hasattr(self, 'api_version') and self.api_version == 'v2':
                # v2 API uses messages format
                messages = kwargs.pop('messages', None)

                if messages is None:
                    # Traditional format - parse prompt to extract system context and user message
                    system_context, user_message = self._parse_prompt(prompt)
                    
                    # Build messages array with system context if present
                    messages = []
                    if system_context:
                        # Include context before the user message to provide full context
                        # Combine system context and user message into a single user message
                        full_content = f"{system_context}\n\n{user_message}"
                        messages.append({"role": "user", "content": full_content})
                    else:
                        messages.append({"role": "user", "content": user_message})

                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get('temperature', self.temperature),
                    max_tokens=kwargs.get('max_tokens', self.max_tokens),
                    p=kwargs.get('top_p', self.top_p),
                    **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens', 'top_p']}
                )

                # v2 API response structure: message.content is an array
                response_text = response.message.content[0].text
                # Clean the response to remove any unwanted formatting
                return self._clean_response(response_text)
            else:
                # v1 API uses message (singular) format
                # For v1, keep the full prompt but remove "Assistant:" label at the end
                cleaned_prompt = prompt.replace("Assistant:", "").strip()
                
                response = await self.client.chat(
                    model=self.model,
                    message=cleaned_prompt,
                    temperature=kwargs.get('temperature', self.temperature),
                    max_tokens=kwargs.get('max_tokens', self.max_tokens),
                    p=kwargs.get('top_p', self.top_p),
                    **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens', 'top_p', 'messages']}
                )

                response_text = response.text
                # Clean the response to remove any unwanted formatting
                return self._clean_response(response_text)

        except Exception as e:
            self._handle_cohere_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Cohere."""
        if not self.initialized:
            await self.initialize()

        try:
            # Check API version and use appropriate format
            if hasattr(self, 'api_version') and self.api_version == 'v2':
                # v2 API uses messages format
                messages = kwargs.pop('messages', None)

                if messages is None:
                    # Traditional format - parse prompt to extract system context and user message
                    system_context, user_message = self._parse_prompt(prompt)
                    
                    # Build messages array with system context if present
                    messages = []
                    if system_context:
                        # Include context before the user message to provide full context
                        # Combine system context and user message into a single user message
                        full_content = f"{system_context}\n\n{user_message}"
                        messages.append({"role": "user", "content": full_content})
                    else:
                        messages.append({"role": "user", "content": user_message})

                stream = self.client.chat_stream(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get('temperature', self.temperature),
                    max_tokens=kwargs.get('max_tokens', self.max_tokens),
                    p=kwargs.get('top_p', self.top_p),
                    **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens', 'top_p', 'stream']}
                )

                async for event in stream:
                    if event.type == "content-delta":
                        yield event.delta.message.content.text
                
                # Note: For streaming, we can't clean the full response until it's complete
                # The cleaning will happen on the client side or in the response processor
            else:
                # v1 API uses message (singular) format
                # For v1, keep the full prompt but remove "Assistant:" label at the end
                cleaned_prompt = prompt.replace("Assistant:", "").strip()
                
                stream = self.client.chat_stream(
                    model=self.model,
                    message=cleaned_prompt,
                    temperature=kwargs.get('temperature', self.temperature),
                    max_tokens=kwargs.get('max_tokens', self.max_tokens),
                    p=kwargs.get('top_p', self.top_p),
                    **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens', 'top_p', 'stream', 'messages']}
                )

                async for chunk in stream:
                    if chunk.event_type == "text-generation":
                        yield chunk.text

        except Exception as e:
            self._handle_cohere_error(e, "streaming generation")
            yield f"Error: {str(e)}"
