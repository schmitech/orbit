#!/usr/bin/env python3
# Version: 1.0.1
import requests
import json
import sys
import time
import argparse
import re
import uuid
import os
import toml
import importlib.metadata
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.syntax import Syntax
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts import CompleteStyle

# Initialize Rich console
console = Console()

# --- Configuration --- #
CONFIG_DIR = os.path.expanduser("~/.orbit")
CONFIG_FILE = os.path.join(CONFIG_DIR, "client.toml")
HISTORY_FILE = os.path.join(CONFIG_DIR, "chat_history")

# Rich styles configuration
USER_STYLE = "bold blue"
ASSISTANT_STYLE = "#e5e5e5"  # Light gray for assistant
SYSTEM_STYLE = "cyan"
ERROR_STYLE = "bold red"
WARNING_STYLE = "bold yellow"

# Conversation history for /clear command
conversation_history = []

# Dark theme for prompt_toolkit with completion styling
prompt_style = Style.from_dict({
    # Completion menu styling
    'completion-menu': 'bg:#1a1b26 fg:#a9b1d6',
    'completion-menu.completion': 'bg:#1a1b26 fg:#a9b1d6',
    'completion-menu.completion.current': 'bg:#1a1b26 fg:#e0af68 bold',

    # 🔧 Descriptions (meta) — remove gray background
    'completion-menu.meta': 'bg:default fg:#565f89',
    'completion-menu.meta.current': 'bg:default fg:#9ece6a',

    # Some prompt_toolkit builds use these selectors for meta text; set them too
    'completion-menu.meta.completion': 'bg:default fg:#565f89',
    'completion-menu.meta.completion.current': 'bg:default fg:#9ece6a',

    # Multi-column variants (cover both spellings used across versions)
    'completion-menu.multi-column': 'bg:#1a1b26 fg:#a9b1d6',
    'completion-menu.multi-column.meta': 'bg:default fg:#565f89',
    'completion-menu.multi-column-meta': 'bg:default fg:#565f89',

    # Base completion + scrollbar + prompt colors (unchanged)
    'completion': 'bg:#1a1b26',
    'scrollbar.background': 'bg:#24283b',
    'scrollbar.button': 'bg:#414868',
    'scrollbar.arrow': 'bg:#c0caf5',
    'prompt': 'fg:#7aa2f7 bold',
    '': 'fg:#c0caf5',
})


class SlashCommandCompleter(Completer):
    """Custom completer for slash commands."""
    
    def __init__(self):
        self.commands = [
            "/help",
            "/clear",
            "/clear-history", 
            "/reset-session",
            "/status",
            "/debug",
            "/timing",
            "/debug-request",
            "/version",
            "/quit"
        ]
        
        self.command_descriptions = {
            "/help": "Show available commands",
            "/clear": "Clear conversation display",
            "/clear-history": "Clear persistent history file",
            "/reset-session": "Generate new session ID",
            "/status": "Show current status",
            "/debug": "Toggle debug mode",
            "/timing": "Toggle timing display",
            "/debug-request": "Debug next request",
            "/version": "Show client version",
            "/quit": "Exit the client"
        }
    
    def get_completions(self, document, complete_event):
        """Generate completions for the current document."""
        text = document.text_before_cursor
        
        # Only provide completions if we're at the start of a line and it begins with /
        if text.startswith('/'):
            word = text
            for command in self.commands:
                if command.startswith(word):
                    # Calculate how many characters to replace
                    yield Completion(
                        command, 
                        start_position=-len(word),
                        display=command,  # Just show the command
                        display_meta=self.command_descriptions.get(command, ''),  # Description in meta
                        style='bg:#1a1b26 fg:#a9b1d6',  # Style for unselected
                        selected_style='bg:#1a1b26 fg:#e0af68 bold'  # Style for selected
                    )

def create_default_config():
    """Creates a default config file for the user."""
    default_content = (
        "[defaults]\n"
        "# URL of your ORBIT server\n"
        "url = \"http://localhost:3000\"\n\n"
        "# Your API key for the ORBIT server\n"
        "# api_key = \"your_api_key_here\"\n"
    )
    try:
        with open(CONFIG_FILE, "w") as f:
            f.write(default_content)
        console.print(f"✅ Successfully created default config file at: [green]{CONFIG_FILE}[/green]")
    except Exception as e:
        console.print(f"Error creating config file: {e}", style=ERROR_STYLE)

def load_config():
    """Loads configuration from the TOML file, with interactive setup."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    defaults = {
        "url": "http://localhost:3000",
        "api_key": None
    }
    
    if not os.path.exists(CONFIG_FILE):
        try:
            console.print(f"⚠️  Config file not found at [yellow]{CONFIG_FILE}[/yellow]")
            answer = Prompt.ask(
                "Would you like to create a default one?",
                choices=["y", "n"],
                default="y"
            ).lower().strip()
            
            if answer == 'y':
                create_default_config()
                console.print("📝 Config file created! You can edit it later if needed.", style="green")
            else:
                console.print("Skipping config file creation. Please provide required arguments via flags.", style=WARNING_STYLE)
        except (KeyboardInterrupt, EOFError):
            console.print("\nSetup cancelled. Exiting.", style=WARNING_STYLE)
            sys.exit(0)
        return defaults

    try:
        with open(CONFIG_FILE, "r") as f:
            config_data = toml.load(f).get("defaults", {})
        return {**defaults, **config_data}
    except Exception as e:
        console.print(f"Error reading config file {CONFIG_FILE}: {e}", style=ERROR_STYLE)
        return defaults

def clean_response(text):
    """Cleans up model response text."""
    # First, protect currency patterns from being modified
    currency_patterns = []
    def protect_currency(match):
        placeholder = f"__CURRENCY_{len(currency_patterns)}__"
        currency_patterns.append(match.group(0))
        return placeholder
    
    # Protect currency amounts (e.g., $12,144.32, $1,234.56)
    text = re.sub(r'\$\d{1,3}(?:,\d{3})*(?:\.\d+)?', protect_currency, text)
    
    # Apply the original cleaning logic
    text = re.sub(r'([.,!?:;])(?!\]d)([A-Za-z0-9])', r'\1 \2', text)
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    
    # Restore currency patterns
    for i, pattern in enumerate(currency_patterns):
        text = text.replace(f"__CURRENCY_{i}__", pattern)
    
    prefixes = ["Assistant:", "A:", "Model:", "AI:", "Gemma:", "Assistant: "]
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip()
    return text.strip()

def handle_slash_command(command, session_id, args, session=None):
    """Handle slash commands like /help, /clear, etc."""
    cmd = command.lower().strip()
    
    if cmd == "/help":
        help_table = Table(title="🔧 Available Commands", show_header=True)
        help_table.add_column("Command", style="cyan", width=20)
        help_table.add_column("Description", style="white")
        
        commands = [
            ("/help", "Show this help message"),
            ("/clear", "Clear conversation display"),
            ("/clear-history", "Clear persistent command history file"),
            ("/reset-session", "Generate a new session ID"),
            ("/status", "Show current session and server info"),
            ("/debug", "Toggle debug mode on/off"),
            ("/timing", "Toggle timing display on/off"),
            ("/debug-request", "Show next request details for debugging"),
            ("/version", "Show client version"),
            ("/quit", "Exit the chat client"),
        ]
        
        for cmd, desc in commands:
            help_table.add_row(cmd, desc)
        
        console.print(help_table)
        return True, session_id, args, False
    
    elif cmd == "/clear":
        # Clear the screen and conversation history
        console.clear()
        conversation_history.clear()
        
        # Redisplay welcome banner with proper newlines
        welcome_panel = Panel.fit(
            f"[bold cyan]Welcome to the Orbit Chat Client![/bold cyan]\n\n"
            f"[cyan]Server URL:[/cyan] {args.url}\n"
            f"[cyan]Session ID:[/cyan] {session_id}\n\n"
            f"[dim]Type 'exit' or 'quit' to end the conversation[/dim]\n"
            f"[dim]Type '/help' for available commands[/dim]",
            title="🚀 ORBIT Chat",
            border_style="cyan"
        )
        console.print(welcome_panel)
        console.print("✨ Conversation cleared!", style="green")
        return True, session_id, args, False
    
    elif cmd == "/clear-history":
        # Clear the persistent history file
        try:
            if os.path.exists(HISTORY_FILE):
                # Truncate the history file instead of deleting it
                open(HISTORY_FILE, 'w').close()
                # Also clear the in-memory history if session is provided
                if session and hasattr(session, 'history'):
                    session.history.store = []  # Clear the in-memory history
                console.print("🗑️  Persistent command history cleared!", style="green")
                console.print("💡 Restart the client for complete history reset", style="dim cyan")
            else:
                console.print("ℹ️  No history file found to clear", style="yellow")
        except Exception as e:
            console.print(f"❌ Error clearing history: {e}", style=ERROR_STYLE)
        return True, session_id, args, True  # True indicates history was cleared
    
    elif cmd == "/reset-session":
        new_session_id = str(uuid.uuid4())
        console.print(f"🔄 Session reset! New ID: [cyan]{new_session_id}[/cyan]")
        return True, new_session_id, args, False
    
    elif cmd == "/status":
        status_table = Table(title="📊 Current Status", show_header=False)
        status_table.add_column("Property", style="cyan")
        status_table.add_column("Value", style="white")
        
        status_table.add_row("Server URL", args.url)
        status_table.add_row("Session ID", session_id)
        status_table.add_row("API Key", "***" + args.api_key[-4:] if args.api_key else "Not set")
        status_table.add_row("Debug Mode", "On" if args.debug else "Off")
        status_table.add_row("Show Timing", "On" if args.show_timing else "Off")
        status_table.add_row("Messages in History", str(len(conversation_history)))
        
        console.print(status_table)
        return True, session_id, args, False
    
    elif cmd == "/debug":
        args.debug = not args.debug
        status = "enabled" if args.debug else "disabled"
        console.print(f"🐛 Debug mode {status}", style="yellow")
        return True, session_id, args, False
    
    elif cmd == "/timing":
        args.show_timing = not args.show_timing
        status = "enabled" if args.show_timing else "disabled"
        console.print(f"⏱️ Timing display {status}", style="yellow")
        return True, session_id, args, False
    
    elif cmd == "/debug-request":
        # Temporarily enable debug for the next request
        console.print("🔍 Debug mode enabled for next request", style="yellow")
        args.debug = True
        return True, session_id, args, False
    
    elif cmd == "/version":
        try:
            version = importlib.metadata.version("schmitech-orbit-client")
        except importlib.metadata.PackageNotFoundError:
            version = "0.0.0 (not installed)"
        console.print(f"🚀 Orbit Chat Client v{version}", style="cyan")
        return True, session_id, args, False
    
    elif cmd == "/quit":
        return False, session_id, args, False  # False indicates exit, goodbye handled in main loop
    
    else:
        console.print(f"❌ Unknown command: [red]{command}[/red]", style="yellow")
        console.print("💡 Type [cyan]/help[/cyan] to see available commands")
        return True, session_id, args, False

def stream_chat(url, message, api_key=None, session_id=None, debug=False, progress=None):
    """Streams a chat response from the server with rich formatting."""
    if not url.endswith('/v1/chat'):
        url = url.rstrip('/') + '/v1/chat'
        
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Session-ID": session_id
    }
    if api_key:
        headers["X-API-Key"] = api_key
    
    data = {"messages": [{"role": "user", "content": message}], "stream": True}
    
    if debug:
        debug_table = Table(title="Debug Information", show_header=False)
        debug_table.add_row("Request URL", url)
        debug_table.add_row("Headers", json.dumps({k: v if k != 'X-API-Key' else f'***{v[-4:]}' for k, v in headers.items()}, indent=2))
        debug_table.add_row("Body", json.dumps(data, indent=2))
        console.print(debug_table)
    
    try:
        start_time = time.time()
        first_token_time = None
        with requests.post(url, headers=headers, json=data, stream=True, timeout=60) as response:
            if response.status_code != 200:
                # Stop progress immediately on error
                if progress:
                    progress.stop()
                console.print(f"❌ Error: Server returned status code {response.status_code}", style=ERROR_STYLE)
                try:
                    error_detail = response.json()
                    console.print(f"Error details: {error_detail}", style=ERROR_STYLE)
                except:
                    console.print(f"Error response: {response.text}", style=ERROR_STYLE)
                if debug:
                    console.print(Panel(response.text, title="Full Response", border_style="red"))
                return None, None
            
            full_response = ""
            buffer = ""
            response_text = Text("", style=ASSISTANT_STYLE)
            
            # Start Live display first
            live = Live(response_text, console=console, refresh_per_second=30, transient=False)
            live.start()
            
            try:
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        line = line.decode('utf-8')
                        if not line.startswith('data: '):
                            continue
                        data_text = line[6:].strip()
                        if not data_text or data_text == "[DONE]":
                            continue
                        chunk_data = json.loads(data_text)
                        if first_token_time is None:
                            first_token_time = time.time()
                            # Stop the progress spinner immediately on first token
                            if progress:
                                progress.stop()
                                progress = None
                        if "response" in chunk_data:
                            buffer += chunk_data.get("response", "")
                        elif "error" in chunk_data:
                            error_msg = chunk_data.get("error", "Unknown error")
                            if isinstance(error_msg, dict):
                                error_msg = error_msg.get("message", "Unknown error")
                            console.print(f"\n❌ Error from server: {error_msg}", style=ERROR_STYLE)
                            return error_msg, None
                        clean_content = clean_response(buffer)
                        response_text.plain = clean_content
                        full_response = clean_content
                    except Exception as e:
                        if debug:
                            console.print(f"\n❌ Error processing chunk: {e}", style=ERROR_STYLE)
                        continue
            finally:
                live.stop()
            
            end_time = time.time()
            total_time = end_time - start_time
            time_to_first_token = first_token_time - start_time if first_token_time else None
            return full_response, {"total_time": total_time, "time_to_first_token": time_to_first_token}
    except requests.exceptions.RequestException as e:
        # Stop progress on connection error
        if progress:
            progress.stop()
        console.print(f"❌ Error connecting to server: {e}", style=ERROR_STYLE)
        return None, None

def main():
    try:
        version = importlib.metadata.version("schmitech-orbit-client")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0 (not installed)"

    config = load_config()
    parser = argparse.ArgumentParser(description="Chat Client for ORBIT Server", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {version}")
    parser.add_argument("--url", default=config.get("url"), help="Chat server URL")
    parser.add_argument("--api-key", default=config.get("api_key"), help="API key for authentication")
    parser.add_argument("--session-id", default=config.get("session_id"), help="Session ID to use")
    parser.add_argument("--debug", action="store_true", default=config.get("debug"), help="Enable debug mode")
    parser.add_argument("--show-timing", action="store_true", default=config.get("show_timing"), help="Show latency timing information")
    args = parser.parse_args()

    # The API key is optional. If not provided, the server will decide whether to allow the request.
    # For a local server, this usually works fine. For a remote server, you will likely need an API key.

    session_id = args.session_id if args.session_id else str(uuid.uuid4())
    session = PromptSession(
        history=FileHistory(HISTORY_FILE),
        completer=SlashCommandCompleter(),
        style=prompt_style,
        complete_style=CompleteStyle.COLUMN  # Single column for better style control
    )

    # Welcome banner
    welcome_panel = Panel.fit(
        f"[bold cyan]Welcome to the Orbit Chat Client![/bold cyan]\n\n"
        f"[cyan]Server URL:[/cyan] {args.url}\n"
        f"[cyan]Session ID:[/cyan] {session_id}\n\n"
        f"[dim]Type 'exit' or 'quit' to end the conversation[/dim]\n"
        f"[dim]Type '/help' for available commands[/dim]",
        title="🚀 ORBIT Chat",
        border_style="cyan"
    )
    console.print(welcome_panel)
    
    while True:
        try:
            # Use rich prompt for user input
            console.print()
            user_input = session.prompt(
                "You: ",
                auto_suggest=AutoSuggestFromHistory()
            )
            # Skip empty input
            if not user_input.strip():
                continue
                
            if user_input.lower() in ["exit", "quit"]:
                break
            
            # Handle slash commands
            if user_input.startswith('/'):
                continue_chat, session_id, args, history_cleared = handle_slash_command(user_input, session_id, args, session)
                if not continue_chat:
                    break
                if history_cleared:
                    # Recreate the session with fresh history
                    session = PromptSession(
                        history=FileHistory(HISTORY_FILE),
                        completer=SlashCommandCompleter(),
                        style=prompt_style,
                        complete_style=CompleteStyle.COLUMN
                    )
                continue
            
            # Add to conversation history
            conversation_history.append({"role": "user", "content": user_input})
            
            # Show spinner only (no text)
            console.print()
            progress = Progress(
                SpinnerColumn(style="cyan"),
                transient=True,
                console=console,
                refresh_per_second=10
            )
            progress.start()
            task = progress.add_task("", total=None)
            
            # Start streaming response - progress will be stopped inside stream_chat
            response, timing_info = stream_chat(
                args.url, user_input, api_key=args.api_key, session_id=session_id, debug=args.debug,
                progress=progress
            )
            
            # Add assistant response to conversation history
            if response:
                conversation_history.append({"role": "assistant", "content": response})
            
            if args.show_timing and timing_info and timing_info.get('time_to_first_token') is not None:
                streaming_time = timing_info['total_time'] - timing_info['time_to_first_token']
                
                # Create timing table
                timing_table = Table(title="⏱️  Latency Metrics", show_header=False)
                timing_table.add_column("Metric", style="cyan")
                timing_table.add_column("Value", style="yellow")
                timing_table.add_row("Total time", f"{timing_info['total_time']:.3f}s")
                timing_table.add_row("Time to first token", f"{timing_info['time_to_first_token']:.3f}s")
                timing_table.add_row("Streaming time", f"{streaming_time:.3f}s")
                console.print(timing_table)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
            break
        except Exception as e:
            console.print(f"\n❌ An error occurred: {e}", style=ERROR_STYLE)

    console.print("\n[bold cyan]👋 Goodbye![/bold cyan]")

if __name__ == "__main__":
    main()