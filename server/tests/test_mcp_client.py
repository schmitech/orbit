#!/usr/bin/env python
"""
ORBIT API Client Test Script

This script tests the /v1/chat endpoint with a real client request.
It uses a standard RESTful approach and supports both streaming and non-streaming modes.

Usage:
    python test_mcp_client.py [--url=URL] [--api-key=KEY] [--message=MESSAGE] [--stream] [--session-id=SESSION_ID]

Arguments:
    --url          Server URL (default: http://localhost:3000/v1/chat)
    --api-key      Optional API key for authentication
    --message      Custom query/message to send (default: "What is the fee for a residential parking permit?")
    --stream       Enable streaming mode (default: False)
    --session-id   Session ID to use (default: auto-generates UUID)

Examples:
    # Non-streaming with custom message
    python test_mcp_client.py --api-key=your_api_key --message="What are the business hours?" --session-id=user_123_session_456
    
    # Streaming with custom message and auto-generated session ID
    python test_mcp_client.py --api-key=your_api_key --message="How do I apply for a permit?" --stream
    
    # Use default message with streaming
    python test_mcp_client.py --api-key=your_api_key --stream
    
    # Non-streaming with default message
    python test_mcp_client.py --api-key=your_api_key
"""

import argparse
import json
import time
import uuid
import requests
from typing import Dict, Any, Optional

def create_chat_request(message: str, stream: bool = True) -> Dict[str, Any]:
    """
    Create a RESTful chat request with the given message.
    
    Args:
        message: The message to send
        stream: Whether to stream the response
        
    Returns:
        A dictionary with the chat request payload
    """
    return {
        "messages": [
            {"role": "user", "content": message}
        ],
        "stream": stream
    }

def send_non_streaming_request(url: str, api_key: Optional[str], message: str, session_id: str) -> None:
    """
    Send a non-streaming chat request and print the response.
    
    Args:
        url: The server URL
        api_key: Optional API key to use
        message: The message to send
        session_id: The session ID to use
    """
    print(f"\n[Non-Streaming Request] Message: '{message}'")
    print(f"Session ID: {session_id}")
    
    # Create request data
    request_data = create_chat_request(message, stream=False)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-Session-ID": session_id
    }
    
    # Add API key header if provided
    if api_key:
        headers["X-API-Key"] = api_key
    
    # Log request details
    print("\nRequest Details:")
    print(f"URL: {url}")
    print(f"Headers: {json.dumps({k: v if k != 'X-API-Key' else f'***{v[-4:]}' for k, v in headers.items()}, indent=2)}")
    print(f"Payload: {json.dumps(request_data, indent=2)}")
    
    # Send request
    try:
        start_time = time.time()
        response = requests.post(url, json=request_data, headers=headers)
        end_time = time.time()
        
        # Check response
        if response.status_code == 200:
            response_data = response.json()
            
            print(f"\nResponse received in {end_time - start_time:.2f} seconds:")
            
            if "response" in response_data:
                print(f"\nResponse text: {response_data.get('response', '')}")
                # Print sources if available
                if "sources" in response_data:
                    print("\nSources:")
                    for source in response_data["sources"]:
                        print(f"- {source}")
            elif "detail" in response_data:
                print(f"\nError: {response_data['detail']}")

            # Print full JSON response
            print("\nFull JSON response:")
            print(json.dumps(response_data, indent=2))
        else:
            print(f"Error: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"Request failed: {str(e)}")

def send_streaming_request(url: str, api_key: Optional[str], message: str, session_id: str) -> None:
    """
    Send a streaming chat request and print the chunked response.
    
    Args:
        url: The server URL
        api_key: Optional API key to use
        message: The message to send
        session_id: The session ID to use
    """
    print(f"\n[Streaming Request] Message: '{message}'")
    print(f"Session ID: {session_id}")
    
    # Create request data
    request_data = create_chat_request(message, stream=True)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-Session-ID": session_id
    }
    
    # Add API key header if provided
    if api_key:
        headers["X-API-Key"] = api_key
    
    # Log request details
    print("\nRequest Details:")
    print(f"URL: {url}")
    print(f"Headers: {json.dumps({k: v if k != 'X-API-Key' else f'***{v[-4:]}' for k, v in headers.items()}, indent=2)}")
    print(f"Payload: {json.dumps(request_data, indent=2)}")
    
    # Send request
    try:
        start_time = time.time()
        first_token_time = None
        # Use stream=True and disable buffering
        response = requests.post(url, json=request_data, headers=headers, stream=True)

        if response.status_code == 200:
            full_text = ""
            chunk_count = 0
            buffer = ""

            print("\nStreaming response:")
            # Use iter_content with small chunk_size to avoid buffering
            # Read bytes and decode manually
            for byte_chunk in response.iter_content(chunk_size=16):
                if not byte_chunk:
                    continue

                # Decode bytes to string
                try:
                    chunk = byte_chunk.decode('utf-8')
                except UnicodeDecodeError:
                    # Skip incomplete UTF-8 sequences
                    continue

                # Add to buffer
                buffer += chunk

                # Process complete lines (SSE format: "data: {...}\n\n")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line or not line.startswith("data: "):
                        continue

                    # Extract data payload
                    data_text = line[6:].strip()  # Remove "data: " prefix

                    if data_text == "[DONE]":
                        break

                    try:
                        # Parse JSON chunk
                        chunk_data = json.loads(data_text)
                        chunk_count += 1

                        if first_token_time is None:
                            first_token_time = time.time()

                        if "response" in chunk_data:
                            text_chunk = chunk_data.get("response", "")
                            full_text += text_chunk
                            print(text_chunk, end="", flush=True)
                        elif "error" in chunk_data:
                            error_msg = chunk_data.get("error", "Unknown error")
                            print(f"\nError: {error_msg}")
                            full_text = error_msg
                            break

                    except json.JSONDecodeError:
                        # Handle non-JSON data
                        if data_text:
                            full_text += data_text
                            print(data_text, end="", flush=True)

            end_time = time.time()
            print(f"\n\nComplete response received in {end_time - start_time:.2f} seconds")
            if first_token_time:
                print(f"Time to first token: {first_token_time - start_time:.2f} seconds")
            print(f"Received {chunk_count} chunks")
            print(f"Total length: {len(full_text)} characters")
        else:
            print(f"Error: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Request failed: {str(e)}")

def main():
    """Main function to parse arguments and send requests."""
    parser = argparse.ArgumentParser(description="Test the ORBIT chat endpoint")
    parser.add_argument("--url", default="http://localhost:3000/v1/chat",
                       help="The server URL (default: http://localhost:3000/v1/chat)")
    parser.add_argument("--api-key",
                       help="Optional API key to use for authentication")
    parser.add_argument("--stream", action="store_true",
                       help="Use streaming mode (default: False)")
    parser.add_argument("--message", default="What is the fee for a residential parking permit?",
                       help="The message to send")
    parser.add_argument("--session-id",
                       help="Session ID to use (default: generates a new UUID).")
    
    args = parser.parse_args()

    url = args.url
    session_id = args.session_id if args.session_id else str(uuid.uuid4())
    
    print("ORBIT API Client Test")
    print("=====================")
    print(f"Server URL: {url}")
    if args.api_key:
        print(f"API key: {args.api_key[:4]}...{args.api_key[-4:]}")
    else:
        print("API key: None")
    print(f"Session ID: {session_id}")
    
    print(f"Request type: {'Streaming' if args.stream else 'Non-streaming'}")
    print(f"Message: {args.message}")
    
    if args.stream:
        send_streaming_request(url, args.api_key, args.message, session_id)
    else:
        send_non_streaming_request(url, args.api_key, args.message, session_id)

if __name__ == "__main__":
    main()
