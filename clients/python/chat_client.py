#!/usr/bin/env python3
import requests
import json
import sys
import time
import argparse
import re
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
os.makedirs(os.path.expanduser("~/.chat_client_history"), exist_ok=True)
HISTORY_FILE = os.path.expanduser("~/.chat_client_history/chat_history")

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
    # Don't remove non-ASCII characters - this was causing Chinese and Arabic to be stripped
    # text = re.sub(r'[^\x20-\x7E\n.,!?:;\'"-]', '', text)  # REMOVE THIS LINE
    
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

def stream_chat(url, message, api_key=None, debug=False, use_mcp=False):
    """
    Stream a chat response from the server, displaying it gradually like a chatbot.
    
    Args:
        url (str): The chat server URL
        message (str): The message to send to the chat server
        api_key (str): Optional API key for authentication
        debug (bool): Whether to show debug information
        use_mcp (bool): Whether to use the MCP protocol format
        
    Returns:
        tuple: (response_text, latency_info)
    """
    # Ensure URL ends with correct endpoint
    if use_mcp:
        if not url.endswith('/v1/chat'):
            url = url.rstrip('/') + '/v1/chat'
    else:
        if not url.endswith('/chat'):
            url = url.rstrip('/') + '/chat'
        
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    if api_key:
        headers["X-API-Key"] = api_key
    
    # Create request data based on protocol
    if use_mcp:
        data = {
            "jsonrpc": "2.0",
            "method": "query",
            "params": {
                "message": message,
                "stream": True
            },
            "id": str(int(time.time() * 1000))  # Use timestamp as request ID
        }
    else:
        data = {
            "message": message,
            "stream": True
        }
    
    if debug:
        print(f"\n{Fore.YELLOW}Debug - Request:{Style.RESET_ALL}")
        print(json.dumps(data, indent=2))
    
    try:
        # Start timing - track when we send the request
        start_time = time.time()
        first_token_time = None
        
        with requests.post(url, headers=headers, json=data, stream=True) as response:
            if response.status_code != 200:
                print(f"{Fore.RED}Error: Server returned status code {response.status_code}{Style.RESET_ALL}")
                if debug:
                    print(response.text)
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
                        
                        # Skip if not a data line
                        if not line.startswith('data: '):
                            continue
                            
                        # Parse the JSON data
                        data = json.loads(line[6:])  # Skip "data: " prefix
                        
                        # Record time of first token
                        if first_token_time is None:
                            first_token_time = time.time()
                        
                        if debug:
                            print(f"\n{Fore.YELLOW}Debug - Received:{Style.RESET_ALL}")
                            print(json.dumps(data, indent=2))
                        
                        # Check if we're done
                        if data == "[DONE]":
                            if debug:
                                print(f"\n{Fore.YELLOW}Debug - Stream complete{Style.RESET_ALL}")
                            break
                        
                        # Get the text content based on protocol
                        if use_mcp:
                            # Handle MCP protocol response
                            if "result" in data:
                                if "content" in data["result"]:
                                    content = data["result"]["content"]
                                    buffer += content
                                elif "type" in data["result"]:
                                    # Handle different chunk types
                                    chunk_type = data["result"]["type"]
                                    if chunk_type == "start":
                                        continue
                                    elif chunk_type in ["chunk", "end"] and "content" in data["result"]:
                                        content = data["result"]["content"]
                                        buffer += content
                                    elif chunk_type == "end" and "response" in data["result"]:
                                        # Final response with complete text
                                        buffer = data["result"]["response"]
                                else:
                                    continue
                            else:
                                continue
                            
                            # Use the accumulated buffer for display
                            content = buffer
                        else:
                            # Handle standard protocol response
                            content = data.get('text', '')
                        
                        if content:
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
        print(f"Error connecting to server: {e}")
        return None, None

def main():
    parser = argparse.ArgumentParser(description="Chat Client for Testing Chat Server")
    parser.add_argument("--url", default="http://localhost:3000", help="Chat server URL (with or without /chat)")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--show-timing", action="store_true", help="Show latency timing information")
    parser.add_argument("--mcp", action="store_true", help="Use MCP protocol format")
    args = parser.parse_args()
    
    # Use colorama for system messages
    print(f"{Fore.CYAN}Welcome to the Chat Client!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Server URL: {args.url}{Style.RESET_ALL}")
    if args.mcp:
        print(f"{Fore.CYAN}Using MCP protocol format{Style.RESET_ALL}")
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
                debug=args.debug,
                use_mcp=args.mcp
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