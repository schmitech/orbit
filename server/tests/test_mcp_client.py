#!/usr/bin/env python
"""
MCP Protocol Client Test Script

This script tests the MCP protocol endpoint with a real client request.
It uses the JSON-RPC 2.0 format as per the MCP protocol standard.

Usage:
    python test_mcp_client.py [--url=URL] [--api-key=KEY] [--stream] [--tools] [--session-id=SESSION_ID]

Example:
    # Using UUID format (recommended)
    python test_mcp_client.py --api-key=orbit_1234567890 --session-id=123e4567-e89b-12d3-a456-426614174000
    
    # Using custom format
    python test_mcp_client.py --api-key=orbit_1234567890 --session-id=user_123_session_456
    
    # Using timestamp-based ID
    python test_mcp_client.py --api-key=orbit_1234567890 --session-id=20240315_123456
    
    # Auto-generated UUID
    python test_mcp_client.py --api-key=orbit_1234567890 --stream
"""

import argparse
import json
import time
import uuid
import requests
import sseclient
from typing import Dict, Any, List, Optional

def create_mcp_chat_request(message: str, stream: bool = True) -> Dict[str, Any]:
    """
    Create a JSON-RPC 2.0 MCP request with the given message.
    
    Args:
        message: The message to send
        stream: Whether to stream the response
        
    Returns:
        A dictionary with the JSON-RPC request
    """
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "chat",
            "arguments": {
                "messages": [
                    {"role": "user", "content": message}
                ],
                "stream": stream
            }
        },
        "id": str(uuid.uuid4())
    }

def create_mcp_tools_request(tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a JSON-RPC 2.0 MCP tools request.
    
    Args:
        tools: List of tool requests with name and parameters
        
    Returns:
        A dictionary with the JSON-RPC tools request
    """
    # Convert traditional tools format to MCP format
    mcp_tools = []
    for tool in tools:
        mcp_tools.append({
            "name": tool["name"],
            "arguments": tool["parameters"]
        })
    
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "tool_invoker",
            "arguments": {
                "tools": mcp_tools
            }
        },
        "id": str(uuid.uuid4())
    }

def send_non_streaming_request(url: str, api_key: str, message: str, session_id: str) -> None:
    """
    Send a non-streaming MCP request and print the response.
    
    Args:
        url: The server URL
        api_key: The API key to use
        message: The message to send
        session_id: The session ID to use
    """
    print(f"\n[Non-Streaming MCP Request] Message: '{message}'")
    print(f"Session ID: {session_id}")
    
    # Create request data
    request_data = create_mcp_chat_request(message, stream=False)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Session-ID": session_id
    }
    
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
            
            # Print response info
            print(f"\nResponse received in {end_time - start_time:.2f} seconds:")
            print(f"JSON-RPC: {response_data.get('jsonrpc')}")
            print(f"ID: {response_data.get('id')}")
            
            if "result" in response_data:
                # Check if response is in new MCP format
                if "output" in response_data["result"] and "messages" in response_data["result"]["output"]:
                    messages = response_data["result"]["output"]["messages"]
                    assistant_message = next((m for m in messages if m.get("role") == "assistant"), None)
                    if assistant_message:
                        print(f"\nResponse text: {assistant_message.get('content', '')}")
                # Handle older format for backward compatibility
                elif "response" in response_data["result"]:
                    print(f"\nResponse text: {response_data['result'].get('response', '')}")
                
                # Print sources if available
                if "sources" in response_data["result"]:
                    print("\nSources:")
                    for source in response_data["result"]["sources"]:
                        print(f"- {source}")
            
            elif "error" in response_data:
                print(f"\nError: {response_data['error'].get('code')} - {response_data['error'].get('message')}")
            
            # Print full JSON response
            print("\nFull JSON response:")
            print(json.dumps(response_data, indent=2))
        else:
            print(f"Error: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"Request failed: {str(e)}")

def send_streaming_request(url: str, api_key: str, message: str, session_id: str) -> None:
    """
    Send a streaming MCP request and print the chunked response.
    
    Args:
        url: The server URL
        api_key: The API key to use
        message: The message to send
        session_id: The session ID to use
    """
    print(f"\n[Streaming MCP Request] Message: '{message}'")
    print(f"Session ID: {session_id}")
    
    # Create request data
    request_data = create_mcp_chat_request(message, stream=True)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Session-ID": session_id
    }
    
    # Log request details
    print("\nRequest Details:")
    print(f"URL: {url}")
    print(f"Headers: {json.dumps({k: v if k != 'X-API-Key' else f'***{v[-4:]}' for k, v in headers.items()}, indent=2)}")
    print(f"Payload: {json.dumps(request_data, indent=2)}")
    
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
                    
                    # Process MCP-compliant streaming chunk
                    if "result" in chunk_data:
                        if chunk_data["result"].get("type") == "chunk" and "chunk" in chunk_data["result"]:
                            # New MCP format
                            text_chunk = chunk_data["result"]["chunk"].get("content", "")
                            full_text += text_chunk
                            print(text_chunk, end="", flush=True)
                        elif "content" in chunk_data["result"]:
                            # Older format for backward compatibility
                            text_chunk = chunk_data["result"]["content"]
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

def send_tools_request(url: str, api_key: str, session_id: str) -> None:
    """
    Send a tools request using JSON-RPC format.
    
    Args:
        url: The server URL
        api_key: The API key to use
        session_id: The session ID to use
    """
    print("\n[MCP Tools Request]")
    print(f"Session ID: {session_id}")
    
    # Create sample tools request
    tools = [
        {
            "name": "weather",
            "parameters": {
                "location": "San Francisco",
                "unit": "celsius"
            }
        },
        {
            "name": "calculator",
            "parameters": {
                "expression": "2 + 2"
            }
        }
    ]
    
    request_data = create_mcp_tools_request(tools)
    
    # Create headers
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Session-ID": session_id
    }
    
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
            
            # Print response info
            print(f"Response received in {end_time - start_time:.2f} seconds:")
            print(f"JSON-RPC: {response_data.get('jsonrpc')}")
            print(f"ID: {response_data.get('id')}")
            
            # Handle MCP format tool results
            if "result" in response_data:
                if "output" in response_data["result"] and "tools" in response_data["result"]["output"]:
                    print("\nTool results:")
                    for result in response_data["result"]["output"]["tools"]:
                        print(f"- Tool: {result.get('name')}")
                        print(f"  Status: {result.get('status', 'completed')}")
                        print(f"  Result: {result.get('output')}")
                # Handle legacy format
                elif "tool_results" in response_data["result"]:
                    print("\nTool results:")
                    for result in response_data["result"]["tool_results"]:
                        print(f"- Tool: {result.get('tool_name')}")
                        print(f"  Status: {result.get('status')}")
                        print(f"  Result: {result.get('result')}")
            
            # Print full JSON response
            print("\nFull JSON response:")
            print(json.dumps(response_data, indent=2))
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
    parser.add_argument("--tools", action="store_true",
                       help="Send a tools request")
    parser.add_argument("--session-id",
                       help="Session ID to use (default: generates a new UUID). Can be any non-empty string.")
    
    args = parser.parse_args()
    
    # Generate or use provided session ID
    session_id = args.session_id if args.session_id else str(uuid.uuid4())
    
    # Print configuration
    print("MCP Protocol Client Test")
    print("=======================")
    print(f"Server URL: {args.url}")
    print(f"API key: {args.api_key[:4]}...{args.api_key[-4:]}")
    print(f"Session ID: {session_id}")
    print(f"Mode: JSON-RPC 2.0 (MCP-compliant)")
    
    if args.tools:
        print("Request type: Tools")
        send_tools_request(args.url, args.api_key, session_id)
    else:
        print(f"Request type: {'Streaming' if args.stream else 'Non-streaming'}")
        print(f"Message: {args.message}")
        
        # Send request
        if args.stream:
            send_streaming_request(args.url, args.api_key, args.message, session_id)
        else:
            send_non_streaming_request(args.url, args.api_key, args.message, session_id)

if __name__ == "__main__":
    main()