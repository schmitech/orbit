#!/usr/bin/env python
"""
MCP Protocol Client Test Script

This script tests the MCP protocol endpoint with a real client request.
It can be used for manual testing of the MCP protocol implementation.

Usage:
    python test_mcp_client.py [--url=URL] [--api-key=KEY] [--stream]

Example:
    python test_mcp_client.py --api-key=orbit_1234567890 --stream
"""

import argparse
import json
import time
import uuid
import requests
import sseclient
from typing import Dict, Any, List, Optional

def create_mcp_request(message: str, stream: bool = True) -> Dict[str, Any]:
    """
    Create an MCP protocol request with the given message.
    
    Args:
        message: The message to send
        stream: Whether to stream the response
        
    Returns:
        A dictionary with the MCP request
    """
    return {
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "object": "thread.message",
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": message
                    }
                ],
                "created_at": int(time.time())
            }
        ],
        "stream": stream
    }

def send_non_streaming_request(url: str, api_key: str, message: str) -> None:
    """
    Send a non-streaming MCP request and print the response.
    
    Args:
        url: The server URL
        api_key: The API key to use
        message: The message to send
    """
    print(f"\n[Non-Streaming Request] Message: '{message}'")
    
    # Create request data
    request_data = create_mcp_request(message, stream=False)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    
    # Send request
    try:
        start_time = time.time()
        response = requests.post(url, json=request_data, headers=headers)
        end_time = time.time()
        
        # Check response
        if response.status_code == 200:
            response_data = response.json()
            
            # Print response info
            print(f"Response received in {end_time - start_time:.2f} seconds:")
            print(f"ID: {response_data.get('id')}")
            print(f"Created at: {response_data.get('created_at')}")
            print(f"Role: {response_data.get('role')}")
            
            # Print content
            if "content" in response_data and response_data["content"]:
                for content_item in response_data["content"]:
                    if content_item.get("type") == "text":
                        print(f"\nResponse text: {content_item.get('text')}")
            
            # Print full JSON response if verbose
            print("\nFull JSON response:")
            print(json.dumps(response_data, indent=2))
        else:
            print(f"Error: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"Request failed: {str(e)}")

def send_streaming_request(url: str, api_key: str, message: str) -> None:
    """
    Send a streaming MCP request and print the chunked response.
    
    Args:
        url: The server URL
        api_key: The API key to use
        message: The message to send
    """
    print(f"\n[Streaming Request] Message: '{message}'")
    
    # Create request data
    request_data = create_mcp_request(message, stream=True)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    
    # Send request
    try:
        start_time = time.time()
        response = requests.post(url, json=request_data, headers=headers, stream=True)
        
        if response.status_code == 200:
            # Initialize SSE client
            client = sseclient.SSEClient(response)
            
            # Process streaming response
            full_text = ""
            chunk_count = 0
            
            print("\nStreaming response:")
            for event in client.events():
                if event.data == "[DONE]":
                    break
                
                try:
                    chunk_data = json.loads(event.data)
                    chunk_count += 1
                    
                    # Extract text content
                    if "delta" in chunk_data and "content" in chunk_data["delta"]:
                        for content_item in chunk_data["delta"]["content"]:
                            if content_item.get("type") == "text":
                                text_chunk = content_item.get("text", "")
                                full_text += text_chunk
                                print(text_chunk, end="", flush=True)
                    
                except json.JSONDecodeError:
                    print(f"[Error parsing JSON] {event.data}")
            
            end_time = time.time()
            print(f"\n\nComplete response received in {end_time - start_time:.2f} seconds")
            print(f"Received {chunk_count} chunks")
            print(f"Total length: {len(full_text)} characters")
        else:
            print(f"Error: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"Request failed: {str(e)}")

def main():
    """Main function to parse arguments and send requests."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test the MCP protocol endpoint")
    parser.add_argument("--url", default="http://localhost:3000/v1/chat",
                       help="The server URL (default: http://localhost:3000/v1/chat)")
    parser.add_argument("--api-key", required=True,
                       help="The API key to use for authentication")
    parser.add_argument("--stream", action="store_true",
                       help="Use streaming mode (default: False)")
    parser.add_argument("--message", default="What is the fee for a residential parking permit?",
                       help="The message to send (default: 'What is the fee for a residential parking permit?')")
    
    args = parser.parse_args()
    
    # Print configuration
    print("MCP Protocol Client Test")
    print("=======================")
    print(f"Server URL: {args.url}")
    print(f"API key: {args.api_key[:4]}...{args.api_key[-4:]}")
    print(f"Streaming: {args.stream}")
    print(f"Message: {args.message}")
    
    # Send request
    if args.stream:
        send_streaming_request(args.url, args.api_key, args.message)
    else:
        send_non_streaming_request(args.url, args.api_key, args.message)

if __name__ == "__main__":
    main() 