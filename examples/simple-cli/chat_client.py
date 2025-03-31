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
    """Clean any artifacts or strange characters from the response"""
    # Remove non-ASCII characters
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    
    # Fix missing spaces (Gemma specific issue)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # Add space between lowercase and uppercase
    text = re.sub(r'([.,!?:;])([A-Za-z])', r'\1 \2', text)  # Add space after punctuation
    text = re.sub(r'([a-zA-Z])(\*)', r'\1 \2', text)  # Add space before asterisk
    text = re.sub(r'(\*)([a-zA-Z])', r'\1 \2', text)  # Add space after asterisk
    
    # Normalize spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Remove any markdown formatting that might appear
    text = text.replace('**', '')
    text = re.sub(r'\*+', '*', text)  # Replace multiple asterisks with single
    
    # Remove any escape sequences
    text = text.replace('\\', '')
    
    # Remove any model identifier prefixes
    prefixes = ["Assistant:", "A:", "model", "AI:", "Gemma:"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    
    return text.strip()

def stream_chat(url, message, max_tokens=256, temperature=0.7, debug=False):
    """
    Stream a chat response from the server, displaying it gradually like a chatbot.
    
    Args:
        url (str): The chat server URL
        message (str): The message to send to the chat server
        max_tokens (int): Maximum number of tokens to generate
        temperature (float): Sampling temperature for generation
        debug (bool): Whether to show debug information
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    data = {
        "message": message,
        "voiceEnabled": False,
        "stream": True,
        "max_new_tokens": max_tokens,
        "temperature": temperature
    }
    
    if debug:
        print(f"\n{Fore.YELLOW}Debug - Request:{Style.RESET_ALL}")
        print(json.dumps(data, indent=2))
    
    try:
        with requests.post(url, headers=headers, json=data, stream=True) as response:
            if response.status_code != 200:
                print(f"{Fore.RED}Error: Server returned status code {response.status_code}{Style.RESET_ALL}")
                if debug:
                    print(response.text)
                return None
            
            # Process the streaming response
            full_response = ""
            buffer = ""
            
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    # Try to decode the chunk
                    try:
                        text = chunk.decode('utf-8')
                        buffer += text
                        
                        # Process complete JSON objects
                        lines = buffer.split('\n')
                        buffer = lines.pop() if lines else ""
                        
                        for line in lines:
                            if line.strip():
                                try:
                                    data = json.loads(line)
                                    # Handle data in format similar to api.ts
                                    content = data.get('text', data.get('content', ''))
                                    is_done = data.get('done', False)
                                    
                                    if is_done:
                                        if debug:
                                            print(f"\n\n{Fore.YELLOW}Debug - Stream complete{Style.RESET_ALL}")
                                        continue
                                    
                                    if content:
                                        # Clean the content before displaying
                                        clean_content = clean_response(content)
                                        
                                        # Display character by character for a typing effect
                                        for char in clean_content:
                                            print(char, end="", flush=True)
                                            # Adjust this delay to control typing speed
                                            time.sleep(0.02)  # 20ms delay per character
                                            
                                        full_response += clean_content
                                except json.JSONDecodeError:
                                    if debug:
                                        print(f"\n{Fore.RED}Error decoding JSON: {line}{Style.RESET_ALL}")
                                    continue
                    
                    except UnicodeDecodeError:
                        if debug:
                            print(f"\n{Fore.RED}Error decoding chunk{Style.RESET_ALL}")
                        continue
            
            # Process any remaining content in the buffer
            if buffer:
                try:
                    data = json.loads(buffer)
                    content = data.get('text', data.get('content', ''))
                    if content:
                        clean_content = clean_response(content)
                        
                        # Display character by character for the remaining content
                        for char in clean_content:
                            print(char, end="", flush=True)
                            time.sleep(0.02)  # 20ms delay per character
                            
                        full_response += clean_content
                except json.JSONDecodeError:
                    if debug:
                        print(f"\n{Fore.RED}Error decoding final JSON: {buffer}{Style.RESET_ALL}")
            
            print("\n")
            return full_response
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to server: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Chat Client for Testing Chat Server")
    parser.add_argument("--url", default="http://localhost:3000/chat", help="Chat server URL")
    parser.add_argument("--max-tokens", type=int, default=256, help="Maximum tokens to generate")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature for generation")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()
    
    # Use colorama for system messages
    print(f"{Fore.CYAN}Welcome to the Chat Client!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Server URL: {args.url}{Style.RESET_ALL}")
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
            
            response = stream_chat(args.url, user_input, args.max_tokens, args.temperature, args.debug)
            
        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}Conversation ended by user.{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}An error occurred: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()