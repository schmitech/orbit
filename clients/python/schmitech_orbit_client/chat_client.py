#!/usr/bin/env python3
# Version: 1.2.0 - Updated for MCP protocol
import requests
import json
import sys
import time
import argparse
import re
import uuid
from colorama import Fore, Style, init
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.formatted_text import HTML
import os

# Initialize colorama for cross-platform colored terminal output
init()

# Ensure history directory exists
os.makedirs(os.path.expanduser("~/.orbit_client_history"), exist_ok=True)
HISTORY_FILE = os.path.expanduser("~/.orbit_client_history/chat_history")

# Create a prompt session with history
session = PromptSession(history=FileHistory(HISTORY_FILE))

# Define prompt_toolkit styles
prompt_style = PromptStyle.from_dict({
    'you': '#0000ff bold',     # blue
    'assistant': '#00aa00 bold', # green
    'system': '#00aaaa',       # cyan
    'error': '#aa0000',        # red
})

def clean_response(text):
    """Clean any artifacts or strange characters from the response without removing non-English text"""
    # Fix missing spaces after punctuation (for Latin-based languages)
    # But exclude decimal points in numbers (e.g., $70.83)
    text = re.sub(r'([.,!?:;])(?!\d)([A-Za-z0-9])', r'\1 \2', text)
    
    # Fix missing spaces between sentences (for Latin-based languages)
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    
    # Fix missing spaces between words (for Latin-based languages)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    
    # Remove any markdown formatting
    text = re.sub(r'\*+', '', text)  # Remove asterisks
    text = re.sub(r'`+', '', text)   # Remove backticks
    text = re.sub(r'#+\s*', '', text) # Remove heading markers
    
    # Remove any model identifier prefixes
    prefixes = ["Assistant:", "A:", "Model:", "AI:", "Gemma:", "Assistant: "]
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip()
    
    # Normalize whitespace while preserving intentional line breaks and Unicode characters
    lines = text.split('\n')
    lines = [line.strip() for line in lines]
    normalized_lines = []
    
    for line in lines:
        if line:
            # Only normalize multiple spaces within a line
            normalized_line = re.sub(r' +', ' ', line)
            normalized_lines.append(normalized_line)
    
    text = '\n'.join(normalized_lines)
    
    return text.strip()

def stream_chat(url, message, api_key=None, session_id=None, debug=False):
    """
    Stream a chat response from the server using MCP protocol, displaying it gradually like a chatbot.
    
    Args:
        url (str): The chat server URL
        message (str): The message to send to the chat server
        api_key (str): Optional API key for authentication
        session_id (str): Session ID for tracking the conversation
        debug (bool): Whether to show debug information
        
    Returns:
        tuple: (response_text, latency_info)
    """
    # Ensure URL ends with correct endpoint
    if not url.endswith('/v1/chat'):
        url = url.rstrip('/') + '/v1/chat'
        
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    if api_key:
        headers["X-API-Key"] = api_key
    
    # Add session ID to headers
    if session_id:
        headers["X-Session-ID"] = session_id
    
    # Create MCP request data using uuid for ID (consistent with test_mcp_client.py)
    data = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "chat",
            "arguments": {
                "messages": [
                    {"role": "user", "content": message}
                ],
                "stream": True
            }
        },
        "id": str(uuid.uuid4())  # Use UUID instead of timestamp
    }
    
    if debug:
        print(f"\n{Fore.YELLOW}Debug - Request URL:{Style.RESET_ALL} {url}")
        print(f"\n{Fore.YELLOW}Debug - Request Headers:{Style.RESET_ALL}")
        print(json.dumps({k: v if k != 'X-API-Key' else f'***{v[-4:]}' for k, v in headers.items()}, indent=2))
        print(f"\n{Fore.YELLOW}Debug - Request Body:{Style.RESET_ALL}")
        print(json.dumps(data, indent=2))
    
    try:
        # Start timing - track when we send the request
        start_time = time.time()
        first_token_time = None
        
        with requests.post(url, headers=headers, json=data, stream=True) as response:
            if response.status_code != 200:
                print(f"{Fore.RED}Error: Server returned status code {response.status_code}{Style.RESET_ALL}")
                if debug:
                    print(f"Response: {response.text}")
                return None, None
            
            # Process the streaming response
            full_response = ""
            last_displayed_length = 0
            buffer = ""  # Buffer for accumulating MCP response
            
            for line in response.iter_lines():
                if line:
                    try:
                        # Decode the line
                        line = line.decode('utf-8')
                        
                        # Skip if not a data line or empty line
                        if not line.startswith('data: '):
                            continue
                            
                        # Skip empty data lines
                        data_text = line[6:].strip()  # Skip "data: " prefix
                        if not data_text:
                            continue
                            
                        # Check for [DONE] message
                        if data_text == "[DONE]":
                            if debug:
                                print(f"\n{Fore.YELLOW}Debug - Stream complete{Style.RESET_ALL}")
                            break
                            
                        # Parse the JSON data
                        try:
                            data = json.loads(data_text)
                        except json.JSONDecodeError as e:
                            # Only log JSON decode errors if we're in debug mode
                            if debug:
                                print(f"\n{Fore.YELLOW}Debug - Skipping malformed JSON: {e}{Style.RESET_ALL}")
                            continue
                        
                        # Record time of first token
                        if first_token_time is None:
                            first_token_time = time.time()
                        
                        # Handle MCP protocol response
                        if "result" in data:
                            # Handle error responses (including moderation blocks)
                            if "error" in data["result"]:
                                error_msg = data["result"]["error"].get("message", "Unknown error")
                                print(f"\n{Fore.RED}Error: {error_msg}{Style.RESET_ALL}")
                                full_response = error_msg
                                break
                                
                            if "type" in data["result"]:
                                # Handle different chunk types
                                chunk_type = data["result"]["type"]
                                if chunk_type == "start":
                                    continue
                                elif chunk_type == "chunk" and "chunk" in data["result"]:
                                    content = data["result"]["chunk"].get("content", "")
                                    if content:  # Only add non-empty content
                                        buffer += content
                                elif chunk_type == "complete":
                                    # Handle complete response
                                    if "output" in data["result"] and "messages" in data["result"]["output"]:
                                        messages = data["result"]["output"]["messages"]
                                        if messages and messages[0].get("role") == "assistant":
                                            # For moderation responses, the content might be empty
                                            # but we should still display the message
                                            if not messages[0].get("content"):
                                                buffer = "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines."
                                            else:
                                                buffer = messages[0].get("content", "")
                                    elif "response" in data["result"]:
                                        # Handle direct response field
                                        buffer = data["result"]["response"]
                            elif "response" in data["result"]:
                                # Handle direct response field
                                buffer = data["result"]["response"]
                            else:
                                continue
                        else:
                            continue
                            
                        # Use the accumulated buffer for display
                        content = buffer
                        
                        if content:  # Only display if we have content
                            # We already have the fixed text from the server, just clean it for display
                            clean_content = clean_response(content)
                            
                            # Only display new characters since the last update
                            if len(clean_content) > last_displayed_length:
                                new_text = clean_content[last_displayed_length:]
                                
                                # Display character by character
                                for char in new_text:
                                    print(char, end='', flush=True)
                                    time.sleep(0.02)  # 20ms delay per character
                                
                                # Update our last position
                                last_displayed_length = len(clean_content)
                                full_response = clean_content
                            
                    except json.JSONDecodeError as e:
                        if debug:
                            print(f"\n{Fore.RED}Error decoding JSON: {e}{Style.RESET_ALL}")
                        continue
                    except Exception as e:
                        if debug:
                            print(f"\n{Fore.RED}Error processing chunk: {e}{Style.RESET_ALL}")
                        continue
            
            # Calculate timing information
            end_time = time.time()
            total_time = end_time - start_time
            
            # Only calculate time to first token if we received one
            time_to_first_token = None
            if first_token_time is not None:
                time_to_first_token = first_token_time - start_time
            
            # Prepare timing information
            timing_info = {
                "total_time": total_time,
                "time_to_first_token": time_to_first_token
            }
            
            print("\n")
            return full_response, timing_info
            
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}Error connecting to server: {e}{Style.RESET_ALL}")
        return None, None

def main():
    parser = argparse.ArgumentParser(description="Chat Client for Testing Chat Server")
    parser.add_argument("--url", default="http://localhost:3000", help="Chat server URL (will be appended with /v1/chat)")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--session-id", help="Session ID to use (default: generates a new UUID). Can be any non-empty string.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--show-timing", action="store_true", help="Show latency timing information")
    args = parser.parse_args()
    
    # Generate or use provided session ID
    session_id = args.session_id if args.session_id else str(uuid.uuid4())
    
    # Use colorama for system messages
    print(f"{Fore.CYAN}Welcome to the Orbit Chat Client!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Server URL: {args.url}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Session ID: {session_id}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Type 'exit' or 'quit' to end the conversation.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}You can use arrow keys to navigate, up/down for history.{Style.RESET_ALL}")
    
    while True:
        try:
            # Use a plain text prompt without ANSI color codes
            user_input = session.prompt(
                "You: ",
                auto_suggest=AutoSuggestFromHistory()
            )
            
            if user_input.lower() in ["exit", "quit"]:
                print(f"{Fore.CYAN}Goodbye!{Style.RESET_ALL}")
                break
            
            # Print assistant indicator before response
            print(f"\n{Fore.GREEN}Assistant:{Style.RESET_ALL} ", end="", flush=True)
            
            # Stream the response and capture timing info
            response, timing_info = stream_chat(
                args.url, 
                user_input, 
                api_key=args.api_key,
                session_id=session_id,
                debug=args.debug
            )
            
            # Display timing information if requested
            if args.show_timing and timing_info:
                print(f"\n{Fore.YELLOW}Latency Metrics:{Style.RESET_ALL}")
                print(f"  Total time: {timing_info['total_time']:.3f}s")
                if timing_info['time_to_first_token'] is not None:
                    print(f"  Time to first token: {timing_info['time_to_first_token']:.3f}s")
                print(f"  Streaming time: {(timing_info['total_time'] - timing_info['time_to_first_token']):.3f}s")
            
        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}Conversation ended by user.{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}An error occurred: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()