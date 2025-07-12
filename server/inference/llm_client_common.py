"""
LLM Client Common

This module provides common functionality shared across different LLM client implementations.
"""

import json
import time
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator

class LLMClientCommon:
    """
    Common class providing common functionality for LLM clients.
    
    This Common implements common patterns found across different LLM client implementations,
    reducing code duplication and making clients more maintainable.
    """
    
    def __init__(self):
        """Initialize the common client with security services if available."""
        self.llm_guard_service = None
        self.moderator_service = None
        self.security_enabled = False
        
    def set_security_services(self, llm_guard_service=None, moderator_service=None):
        """
        Set security services for response checking.
        
        Args:
            llm_guard_service: Optional LLM Guard service instance
            moderator_service: Optional Moderator service instance
        """
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("🔧 [LLM CLIENT SECURITY] Initializing security services...")
        
        self.llm_guard_service = llm_guard_service
        self.moderator_service = moderator_service
        self.security_enabled = (llm_guard_service and llm_guard_service.enabled) or (moderator_service and moderator_service.enabled)
        
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            # Show detailed security configuration
            if llm_guard_service:
                llm_guard_status = "ENABLED" if llm_guard_service.enabled else "DISABLED"
                self.logger.info(f"🛡️ [LLM CLIENT SECURITY] LLM Guard service: {llm_guard_status}")
            else:
                self.logger.info("🛡️ [LLM CLIENT SECURITY] LLM Guard service: NOT PROVIDED")
            
            if moderator_service:
                moderator_status = "ENABLED" if moderator_service.enabled else "DISABLED"
                self.logger.info(f"🛡️ [LLM CLIENT SECURITY] Moderator service: {moderator_status}")
            else:
                self.logger.info("🛡️ [LLM CLIENT SECURITY] Moderator service: NOT PROVIDED")
            
            if self.security_enabled:
                self.logger.info("✅ [LLM CLIENT SECURITY] Overall security status: ENABLED - responses will be checked")
            else:
                self.logger.info("⚠️ [LLM CLIENT SECURITY] Overall security status: DISABLED - responses will pass through unchecked")
        
    async def _get_system_prompt(self, system_prompt_id: Optional[str] = None) -> str:
        """
        Get the system prompt from the prompt service or return default.
        
        Args:
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            System prompt string
        """
        # First check if there's an in-memory override
        if hasattr(self, 'override_system_prompt') and self.override_system_prompt:
            if getattr(self, 'verbose', False):
                self.logger.info("Using in-memory system prompt override")
            return self.override_system_prompt
            
        # If no system_prompt_id or prompt_service, return empty string (inference-only mode)
        if not system_prompt_id or not self.prompt_service:
            return ""
            
        # Log if verbose mode is enabled
        if getattr(self, 'verbose', False):
            self.logger.info(f"Fetching system prompt with ID: {system_prompt_id}")
            
        # Get prompt from service
        prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
        if prompt_doc and 'prompt' in prompt_doc:
            system_prompt = prompt_doc['prompt']
            if getattr(self, 'verbose', False):
                self.logger.debug(f"Using custom system prompt: {system_prompt[:100]}...")
                
        return system_prompt
    
    async def _retrieve_and_rerank_docs(self, message: str, adapter_name: str) -> List[Dict[str, Any]]:
        """
        Retrieve documents and rerank them if a reranker is available.
        
        Args:
            message: The user's message
            adapter_name: Name of the adapter to use for retrieval
            
        Returns:
            List of retrieved and optionally reranked documents
        """
        if self.inference_only:
            # In inference_only mode, return empty list to skip RAG
            return []
        
        # Log if verbose mode is enabled
        if getattr(self, 'verbose', False):
            self.logger.info(f"Retrieving context using adapter: {adapter_name}")
            
        # Query for relevant documents using the adapter proxy
        retrieved_docs = await self.retriever.get_relevant_context(
            query=message,
            adapter_name=adapter_name
        )
        
        if getattr(self, 'verbose', False):
            self.logger.info(f"Retrieved {len(retrieved_docs)} relevant documents")
        
        # Rerank if reranker is available
        if self.reranker_service and retrieved_docs:
            if getattr(self, 'verbose', False):
                self.logger.info("Reranking retrieved documents")
            retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
        return retrieved_docs
    
    async def _handle_unsafe_message(self, refusal_message: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a standard response for unsafe messages.
        
        Args:
            refusal_message: Optional custom message from guardrail service
            
        Returns:
            Dictionary with safety response
        """
        message = refusal_message or "I cannot assist with that type of request."
        return {
            "response": message,
            "sources": [],
            "tokens": 0,
            "processing_time": 0
        }
    
    async def _handle_unsafe_message_stream(self, refusal_message: Optional[str] = None) -> str:
        """
        Generate a standard streaming response for unsafe messages.
        
        Args:
            refusal_message: Optional custom message from guardrail service
            
        Returns:
            JSON string with safety response
        """
        message = refusal_message or "I cannot assist with that type of request."
        return json.dumps({
            "response": message,
            "sources": [],
            "done": True
        })
    
    async def _prepare_prompt_with_context(
        self, 
        message: str, 
        system_prompt: str, 
        context: str,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Prepare the full prompt with system prompt, context, conversation history and user message.
        
        Args:
            message: The user's message
            system_prompt: The system prompt to use
            context: The context from retrieved documents
            context_messages: Optional list of previous conversation messages
            
        Returns:
            Formatted prompt string
        """
        # Start with system prompt
        prompt_parts = [system_prompt]
        
        # Add context if not in inference_only mode
        if not self.inference_only and context:
            prompt_parts.append(f"\nContext information:\n{context}")
        
        # Add conversation history if available
        if context_messages:
            conversation_history = []
            for msg in context_messages:
                role = msg.get('role', '').lower()
                content = msg.get('content', '')
                if role and content:
                    if role == 'user':
                        conversation_history.append(f"User: {content}")
                    elif role == 'assistant':
                        conversation_history.append(f"Assistant: {content}")
            
            if conversation_history:
                prompt_parts.append("\nPrevious conversation:")
                prompt_parts.extend(conversation_history)
        
        # Add current user message
        prompt_parts.append(f"\nUser: {message}")
        prompt_parts.append("Assistant:")
        
        # Join all parts with newlines
        prompt = "\n".join(prompt_parts)
        
        if getattr(self, 'verbose', False):
            self.logger.debug(f"Prepared prompt length: {len(prompt)} characters")
            
        return prompt
    
    def _measure_execution_time(self, start_time: float) -> float:
        """
        Calculate execution time from start time to now.
        
        Args:
            start_time: The start time from time.time()
            
        Returns:
            Processing time in seconds
        """
        end_time = time.time()
        processing_time = end_time - start_time
        
        if getattr(self, 'verbose', False):
            self.logger.info(f"Received response in {processing_time:.2f} seconds")
            
        return processing_time
    
    def _estimate_tokens(self, prompt: str, response_text: str) -> int:
        """
        Estimate token count for models that don't provide direct token counts.
        
        Args:
            prompt: The input prompt
            response_text: The generated response
            
        Returns:
            Estimated token count
        """
        # Rough estimate: ~4 chars per token
        estimated_tokens = len(prompt) // 4 + len(response_text) // 4
        
        if getattr(self, 'verbose', False):
            self.logger.info(f"Estimated token usage: {estimated_tokens}")
            
        return estimated_tokens
    
    def clear_override_system_prompt(self) -> None:
        """
        Clear any in-memory system prompt override.
        """
        if hasattr(self, 'override_system_prompt'):
            self.override_system_prompt = None
            if getattr(self, 'verbose', False):
                self.logger.info("Cleared in-memory system prompt override")
    
    async def _check_response_security(
        self,
        content: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check response security using available security services.
        
        Args:
            content: The response content to check
            user_id: Optional user identifier
            session_id: Optional session identifier
            
        Returns:
            Dictionary with security check results
        """
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("🔍 [LLM CLIENT SECURITY] Starting OUTGOING response security check")
            self.logger.info(f"📝 [LLM CLIENT SECURITY] Response content preview: '{content[:100]}...' (length: {len(content)})")
            if session_id:
                self.logger.info(f"🆔 [LLM CLIENT SECURITY] Session ID: {session_id}")
        
        if not self.security_enabled:
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("⚠️ [LLM CLIENT SECURITY] Security checking is DISABLED - allowing response")
            return {
                "is_safe": True,
                "risk_score": 0.0,
                "sanitized_content": content,
                "flagged_scanners": [],
                "recommendations": ["Security checking is disabled"]
            }
        
        # First check with LLM Guard service if enabled
        if self.llm_guard_service and self.llm_guard_service.enabled:
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("🛡️ [LLM CLIENT SECURITY] Running LLM Guard check on OUTGOING response...")
            
            try:
                # Prepare metadata for the security check
                metadata = {}
                if session_id:
                    metadata["session_id"] = session_id
                
                # Perform LLM Guard security check
                llm_guard_result = await self.llm_guard_service.check_security(
                    content=content,
                    content_type="response",
                    user_id=user_id,
                    metadata=metadata
                )
                
                if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                    is_safe = llm_guard_result.get("is_safe", True)
                    risk_score = llm_guard_result.get("risk_score", 0.0)
                    flagged_scanners = llm_guard_result.get("flagged_scanners", [])
                    
                    if is_safe:
                        self.logger.info(f"✅ [LLM CLIENT SECURITY] LLM Guard OUTGOING check PASSED - Safe: {is_safe}, Risk: {risk_score:.3f}")
                        if risk_score > 0.0:
                            self.logger.info(f"⚠️ [LLM CLIENT SECURITY] Low risk detected in response: {risk_score:.3f}")
                    else:
                        self.logger.warning(f"🚫 [LLM CLIENT SECURITY] LLM Guard OUTGOING check FAILED - Safe: {is_safe}, Risk: {risk_score:.3f}")
                        if flagged_scanners:
                            self.logger.warning(f"🚩 [LLM CLIENT SECURITY] Response flagged by scanners: {flagged_scanners}")
                
                # If LLM Guard deems the content unsafe, return immediately
                if not llm_guard_result.get("is_safe", True):
                    if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                        self.logger.warning("🛑 [LLM CLIENT SECURITY] OUTGOING response BLOCKED by LLM Guard - stopping security chain")
                    return llm_guard_result
                    
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"❌ [LLM CLIENT SECURITY] Error during LLM Guard OUTGOING check: {str(e)}")
                # Continue with moderator check if available
        else:
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("⏭️ [LLM CLIENT SECURITY] LLM Guard not enabled - skipping OUTGOING check")
        
        # If LLM Guard passed or is disabled, check with Moderator Service if enabled
        if self.moderator_service and self.moderator_service.enabled:
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("🛡️ [LLM CLIENT SECURITY] Running Moderator Service check on OUTGOING response...")
            
            try:
                is_safe, refusal_message = await self.moderator_service.check_safety(content)
                
                if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                    if is_safe:
                        self.logger.info(f"✅ [LLM CLIENT SECURITY] Moderator Service OUTGOING check PASSED - Safe: {is_safe}")
                    else:
                        self.logger.warning(f"🚫 [LLM CLIENT SECURITY] Moderator Service OUTGOING check FAILED - Safe: {is_safe}")
                        self.logger.warning(f"🚫 [LLM CLIENT SECURITY] Moderator blocked response: {refusal_message}")
                
                if not is_safe:
                    if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                        self.logger.warning("🛑 [LLM CLIENT SECURITY] OUTGOING response BLOCKED by Moderator Service")
                    # Content was flagged by Moderator Service
                    return {
                        "is_safe": False,
                        "risk_score": 1.0,
                        "sanitized_content": content,
                        "flagged_scanners": ["moderator_service"],
                        "recommendations": [refusal_message or "Content flagged by Moderator Service"]
                    }
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error(f"❌ [LLM CLIENT SECURITY] Error during Moderator Service OUTGOING check: {str(e)}")
        else:
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("⏭️ [LLM CLIENT SECURITY] Moderator Service not enabled - skipping OUTGOING check")
        
        # All checks passed or no security services available
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("✅ [LLM CLIENT SECURITY] All OUTGOING security checks PASSED - response is safe")
        
        return {
            "is_safe": True,
            "risk_score": 0.0,
            "sanitized_content": content,
            "flagged_scanners": [],
            "recommendations": []
        }
    
    async def _secure_response(
        self,
        response_data: Dict[str, Any],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check response security and return safe response or security error.
        
        Args:
            response_data: The original response data
            user_id: Optional user identifier
            session_id: Optional session identifier
            
        Returns:
            Secure response data (original if safe, error if unsafe)
        """
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("🔒 [LLM CLIENT SECURITY] Starting _secure_response wrapper for non-streaming response")
        
        # Skip security check if disabled or no response content
        if not self.security_enabled or not response_data.get("response"):
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                if not self.security_enabled:
                    self.logger.info("⚠️ [LLM CLIENT SECURITY] Security disabled - returning response without check")
                else:
                    self.logger.info("⚠️ [LLM CLIENT SECURITY] No response content - skipping security check")
            return response_data
        
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("🔍 [LLM CLIENT SECURITY] Calling security check for non-streaming response...")
        
        # Check response security
        security_result = await self._check_response_security(
            content=response_data["response"],
            user_id=user_id,
            session_id=session_id
        )
        
        # If response is safe, return original
        if security_result.get("is_safe", True):
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("✅ [LLM CLIENT SECURITY] Non-streaming response passed security - returning original response")
            return response_data
        
        # If response is unsafe, return security error
        risk_score = security_result.get("risk_score", 1.0)
        flagged_scanners = security_result.get("flagged_scanners", [])
        recommendations = security_result.get("recommendations", [])
        
        # Create user-friendly error message
        error_msg = "Response blocked by security scanner."
        if recommendations and len(recommendations) > 0:
            reason = recommendations[0]
            # Sanitize the reason for user display
            reason = reason.replace("Potential ", "").replace(" detected", "").replace("Review and sanitize user input", "").strip()
            if reason:
                error_msg += f" Reason: {reason}"
        
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.warning(f"🛑 [LLM CLIENT SECURITY] Non-streaming response BLOCKED - Risk: {risk_score:.3f}, Scanners: {flagged_scanners}")
            self.logger.warning(f"🚫 [LLM CLIENT SECURITY] Returning security error instead of original response")
        
        # Return error in the same format as a normal response
        return {
            "error": error_msg,
            "blocked": True,
            "risk_score": risk_score,
            "flagged_scanners": flagged_scanners,
            "sources": response_data.get("sources", []),
            "tokens": response_data.get("tokens", 0),
            "processing_time": response_data.get("processing_time", 0)
        }
    
    async def _secure_response_stream(
        self,
        stream_generator: AsyncGenerator[str, None],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Security wrapper for streaming responses.
        
        Args:
            stream_generator: The original stream generator
            user_id: Optional user identifier
            session_id: Optional session identifier
            
        Yields:
            Secure stream chunks (original if safe, error if unsafe)
        """
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("🔒 [LLM CLIENT SECURITY] Starting _secure_response_stream wrapper for streaming response")
        
        # If security is disabled, pass through the original stream
        if not self.security_enabled:
            if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                self.logger.info("⚠️ [LLM CLIENT SECURITY] Security disabled - passing through original stream without checks")
            async for chunk in stream_generator:
                yield chunk
            return
        
        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
            self.logger.info("🔄 [LLM CLIENT SECURITY] Security enabled - buffering stream for security check")
            self.logger.info("📥 [LLM CLIENT SECURITY] Phase 1: Collecting all stream chunks...")
        
        # Buffer the entire response for security checking
        accumulated_text = ""
        sources = []
        chunks_buffer = []
        stream_completed = False
        chunk_count = 0
        
        try:
            # Collect all chunks
            async for chunk in stream_generator:
                chunk_count += 1
                
                if getattr(self, 'verbose', False) and hasattr(self, 'logger') and chunk_count % 5 == 0:
                    self.logger.debug(f"📥 [LLM CLIENT SECURITY] Buffered {chunk_count} chunks so far...")
                
                try:
                    chunk_data = json.loads(chunk)
                    
                    # If there's an error in the chunk, pass it through immediately
                    if "error" in chunk_data:
                        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                            self.logger.warning(f"⚠️ [LLM CLIENT SECURITY] Error chunk detected - passing through immediately: {chunk_data.get('error', 'Unknown error')}")
                        yield chunk
                        return
                    
                    # Buffer the chunk
                    chunks_buffer.append(chunk)
                    
                    # Accumulate response text
                    if "response" in chunk_data:
                        accumulated_text += chunk_data["response"]
                    
                    # Handle sources
                    if "sources" in chunk_data:
                        sources = chunk_data["sources"]
                    
                    # Handle done marker
                    if chunk_data.get("done", False):
                        stream_completed = True
                        if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                            self.logger.info(f"✅ [LLM CLIENT SECURITY] Stream collection complete - {chunk_count} chunks buffered")
                            self.logger.info(f"📝 [LLM CLIENT SECURITY] Accumulated text length: {len(accumulated_text)} characters")
                        break
                        
                except json.JSONDecodeError:
                    # If we can't parse the chunk, pass it through
                    if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                        self.logger.warning(f"⚠️ [LLM CLIENT SECURITY] Unparseable chunk - passing through: {chunk[:100]}...")
                    yield chunk
                    continue
            
            # Security check the complete response
            if accumulated_text and stream_completed:
                if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                    self.logger.info("🔍 [LLM CLIENT SECURITY] Phase 2: Running security check on complete buffered response...")
                
                security_result = await self._check_response_security(
                    content=accumulated_text,
                    user_id=user_id,
                    session_id=session_id
                )
                
                if security_result.get("is_safe", True):
                    # Response is safe - yield all buffered chunks
                    if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                        self.logger.info(f"✅ [LLM CLIENT SECURITY] Phase 3: Security check PASSED - releasing {len(chunks_buffer)} buffered chunks to client")
                    
                    for i, chunk in enumerate(chunks_buffer):
                        if getattr(self, 'verbose', False) and hasattr(self, 'logger') and i == 0:
                            self.logger.info("📤 [LLM CLIENT SECURITY] Starting to yield buffered chunks...")
                        yield chunk
                    
                    if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                        self.logger.info("🎉 [LLM CLIENT SECURITY] All buffered chunks successfully streamed to client")
                else:
                    # Response is unsafe - yield security error instead
                    risk_score = security_result.get("risk_score", 1.0)
                    flagged_scanners = security_result.get("flagged_scanners", [])
                    recommendations = security_result.get("recommendations", [])
                    
                    # Create user-friendly error message
                    error_msg = "Response blocked by security scanner."
                    if recommendations and len(recommendations) > 0:
                        reason = recommendations[0]
                        # Sanitize the reason for user display
                        reason = reason.replace("Potential ", "").replace(" detected", "").replace("Review and sanitize user input", "").strip()
                        if reason:
                            error_msg += f" Reason: {reason}"
                    
                    if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                        self.logger.warning(f"🛑 [LLM CLIENT SECURITY] Phase 3: Security check FAILED - Risk: {risk_score:.3f}, Scanners: {flagged_scanners}")
                        self.logger.warning(f"🚫 [LLM CLIENT SECURITY] DISCARDING {len(chunks_buffer)} buffered chunks and sending security error instead")
                    
                    # Yield security error as streaming response
                    error_chunk = json.dumps({
                        "error": error_msg,
                        "done": True,
                        "blocked": True,
                        "risk_score": risk_score,
                        "flagged_scanners": flagged_scanners,
                        "sources": sources
                    })
                    yield error_chunk
            else:
                # No content or stream failed - yield error
                if getattr(self, 'verbose', False) and hasattr(self, 'logger'):
                    if not accumulated_text:
                        self.logger.warning("⚠️ [LLM CLIENT SECURITY] No content accumulated from stream")
                    if not stream_completed:
                        self.logger.warning("⚠️ [LLM CLIENT SECURITY] Stream did not complete successfully")
                    self.logger.warning("🚫 [LLM CLIENT SECURITY] Sending 'no response' error")
                
                error_chunk = json.dumps({
                    "error": "No response generated or stream failed",
                    "done": True
                })
                yield error_chunk
                
        except Exception as e:
            # Error during security processing - yield error
            if hasattr(self, 'logger'):
                self.logger.error(f"❌ [LLM CLIENT SECURITY] Error in streaming security check: {str(e)}")
                self.logger.error(f"🚫 [LLM CLIENT SECURITY] Sending security processing error")
            error_chunk = json.dumps({
                "error": f"Security processing failed: {str(e)}",
                "done": True
            })
            yield error_chunk 