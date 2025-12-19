#!/usr/bin/env python3
# Version: 1.0.2
import requests
import httpx
import json
import sys
import time
import argparse
import re
import uuid
import os
import toml
import importlib.metadata
from typing import Optional, Dict, Any
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
from prompt_toolkit.layout import menus as prompt_menus
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.screen import Point

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

# Remove the default left padding so slash command completions line up with the cursor.
_original_menu_fragment_fn = getattr(prompt_menus, "_get_menu_item_fragments", None)
if _original_menu_fragment_fn and not getattr(prompt_menus, "_orbit_menu_patch", False):
    def _flush_left_menu_item_fragments(*args, _orig=_original_menu_fragment_fn, **kwargs):
        fragments = _orig(*args, **kwargs)
        if fragments:
            style, text = fragments[0]
            if text.startswith(" "):
                trimmed = text[1:]
                if trimmed:
                    fragments[0] = (style, trimmed)
                else:
                    del fragments[0]
        return fragments

    prompt_menus._get_menu_item_fragments = _flush_left_menu_item_fragments
    prompt_menus._orbit_menu_patch = True

_buffer_control_create_content = getattr(BufferControl, "create_content", None)
if _buffer_control_create_content and not getattr(BufferControl, "_orbit_menu_shift_patch", False):
    def _buffer_control_create_content_with_shift(self, *args, **kwargs):
        content = _buffer_control_create_content(self, *args, **kwargs)
        shift = getattr(self.buffer, "_orbit_completion_shift", 0)
        if shift and content.menu_position:
            new_x = max(0, content.menu_position.x + shift)
            content.menu_position = Point(x=new_x, y=content.menu_position.y)
        return content

    BufferControl.create_content = _buffer_control_create_content_with_shift
    BufferControl._orbit_menu_shift_patch = True


def _normalize_api_url(api_url: str) -> str:
    """Normalize base API URL by trimming whitespace and known endpoints."""
    if not api_url:
        raise ValueError("API URL is required")

    normalized = api_url.strip()
    if not normalized:
        raise ValueError("API URL is required")

    normalized = normalized.rstrip('/')
    if normalized.endswith('/v1/chat'):
        normalized = normalized[:-len('/v1/chat')]

    return normalized


class OrbitChatClient:
    """Lightweight client for interacting with the ORBIT chat service."""

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: int = 30,
        verbose: bool = False
    ) -> None:
        self.api_url = _normalize_api_url(api_url)
        self.api_key = api_key
        self.session_id = session_id
        self.timeout = timeout
        self.verbose = verbose

    def validate_api_key(self) -> Dict[str, Any]:
        """
        Validate that the API key exists and is active.
        
        Returns:
            Dictionary containing the API key status information
            
        Raises:
            ValueError: If API key is not provided
            RuntimeError: If API key validation fails or key is inactive
        """
        if not self.api_key:
            raise ValueError("API key is required for validation")

        headers = {
            "X-API-Key": self.api_key
        }

        url = f"{self.api_url}/admin/api-keys/{self.api_key}/status"

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Network error while validating API key: {exc}") from exc

        if response.status_code == 200:
            try:
                status: Dict[str, Any] = response.json()
                # Check if the key is active
                if not status.get('active', True):
                    raise RuntimeError("API key is inactive")
                return status
            except ValueError as exc:
                raise RuntimeError("Server returned an invalid JSON response") from exc
        elif response.status_code == 401:
            raise RuntimeError("API key is invalid or expired")
        elif response.status_code == 403:
            raise RuntimeError("Access denied: API key does not have required permissions")
        elif response.status_code == 404:
            raise RuntimeError("API key not found")
        else:
            try:
                error_detail = response.json().get('detail')
            except ValueError:
                error_detail = response.text or f"HTTP {response.status_code}"
            raise RuntimeError(f"Failed to validate API key: {error_detail}")

    def clear_conversation_history(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Clear conversation history for a specific session via admin endpoint."""
        target_session_id = session_id or self.session_id
        if not target_session_id:
            raise ValueError("Session ID is required to clear conversation history")

        if not self.api_key:
            raise ValueError("API key is required for clearing conversation history")

        # Note: We don't validate API key here because:
        # 1. Validation might fail if the key doesn't have admin permissions
        # 2. The clear endpoint will handle validation and return appropriate errors
        # 3. This allows valid API keys to clear history even if they can't check their own status

        headers = {
            "Content-Type": "application/json",
            "X-Session-ID": target_session_id,
            "X-API-Key": self.api_key
        }

        url = f"{self.api_url}/admin/chat-history/{target_session_id}"

        try:
            response = requests.delete(url, headers=headers, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Network error while clearing conversation history: {exc}") from exc

        if response.status_code == 200:
            try:
                result: Dict[str, Any] = response.json()
            except ValueError as exc:
                raise RuntimeError("Server returned an invalid JSON response") from exc

            if self.verbose:
                console.print(
                    f"[green]✓[/green] Cleared {result.get('deleted_count', 0)} messages from session {target_session_id}")
            return result

        try:
            error_detail = response.json().get('detail')
        except ValueError:
            error_detail = response.text or f"HTTP {response.status_code}"

        raise RuntimeError(
            f"Failed to clear conversation history for session {target_session_id}: {error_detail}"
        )


def clear_conversation_history(
    api_url: str,
    api_key: str,
    session_id: str,
    *,
    timeout: int = 30,
    verbose: bool = False
) -> Dict[str, Any]:
    """Convenience wrapper to clear a session's conversation history."""
    client = OrbitChatClient(
        api_url=api_url,
        api_key=api_key,
        session_id=session_id,
        timeout=timeout,
        verbose=verbose
    )
    return client.clear_conversation_history()


class SlashCommandCompleter(Completer):
    """Custom completer for slash commands."""
    
    def __init__(self):
        self.commands = [
            "/help",
            "/clear",
            "/clear-previous-messages",
            "/clear-server-history",
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
            "/clear-previous-messages": "Clear local prompt/history autocomplete cache",
            "/clear-server-history": "Clear server conversation history for the current session",
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
    """Cleans up model response text by protecting numeric values, emails, and other structured data."""
    # Storage for protected patterns
    protected_patterns = []
    pattern_counter = 0
    
    def protect_pattern(match):
        """Create a unique placeholder for a matched pattern."""
        nonlocal pattern_counter
        placeholder = f"__PROTECTED_{pattern_counter}__"
        protected_patterns.append(match.group(0))
        pattern_counter += 1
        return placeholder
    
    # Protect email addresses (e.g., user@example.com, test.email@domain.co.uk)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', protect_pattern, text)
    
    # Protect time formats (e.g., 1:00 PM, 1:00AM, 13:00, 1:00:30 PM)
    # Handle cases where colon might have spaces after it (1: 00 PM -> 1:00 PM)
    def normalize_and_protect_time(match):
        """Normalize time format by removing spaces after colon, then protect."""
        nonlocal pattern_counter
        time_str = match.group(0)
        # Remove spaces after colons
        normalized = re.sub(r':\s+', ':', time_str)
        placeholder = f"__PROTECTED_{pattern_counter}__"
        protected_patterns.append(normalized)
        pattern_counter += 1
        return placeholder
    
    # Match times with AM/PM first (most specific) - handles spaces after colon
    text = re.sub(r'\b\d{1,2}:\s*\d{2}(?::\s*\d{2})?\s*(?:AM|PM|am|pm)\b', 
                  normalize_and_protect_time, text, flags=re.IGNORECASE)
    # Then match 24-hour time format (HH:MM or HH:MM:SS), also normalize spaces
    text = re.sub(r'\b\d{1,2}:\s*\d{2}(?::\s*\d{2})?\b', normalize_and_protect_time, text)
    
    # Protect date formats
    # ISO date format (YYYY-MM-DD)
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', protect_pattern, text)
    # US date format (MM/DD/YYYY or M/D/YYYY)
    text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{4}\b', protect_pattern, text)
    # Date format with month names (Jan 15, 2025 or January 15, 2025)
    text = re.sub(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b', protect_pattern, text, flags=re.IGNORECASE)
    text = re.sub(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', protect_pattern, text, flags=re.IGNORECASE)
    
    # Protect decimal numbers with time units (e.g., 29.5s, 1.5ms, 0.5h, 2.3s)
    # This must be done before general decimal protection to include the unit
    text = re.sub(r'\b\d+\.\d+[a-zA-Z]+\b', protect_pattern, text)
    
    # Protect currency amounts (e.g., $12,144.32, $1,234.56, $123.45)
    text = re.sub(r'\$\d{1,3}(?:,\d{3})*(?:\.\d+)?', protect_pattern, text)
    
    # Protect numbers with commas and optional decimals (e.g., 567,481.6, 72,604.0, 1,234,567)
    text = re.sub(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?', protect_pattern, text)
    
    # Protect plain decimal numbers that might be part of data (e.g., 123.45, 0.123)
    # Only protect if they're not already part of a protected pattern and look like numeric data
    # This protects decimals that are standalone or followed by units/whitespace
    text = re.sub(r'\b\d+\.\d+\b', protect_pattern, text)
    
    # Apply the original cleaning logic (spacing after punctuation)
    text = re.sub(r'([.,!?:;])(?!\]d)([A-Za-z0-9])', r'\1 \2', text)
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    
    # Restore all protected patterns in reverse order to avoid conflicts
    for i in range(len(protected_patterns) - 1, -1, -1):
        text = text.replace(f"__PROTECTED_{i}__", protected_patterns[i])
    
    # Remove common AI response prefixes
    prefixes = ["Assistant:", "A:", "Model:", "AI:", "Gemma:", "Assistant: "]
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip()
    return text.strip()


# Precompiled patterns we treat as a hint that the response is Markdown.
MARKDOWN_PATTERNS = [
    re.compile(r"(^|\n)\s{0,3}#{1,6}\s+\S"),  # headings
    re.compile(r"```"),  # fenced code blocks
    re.compile(r"(^|\n)\s{0,3}[-*+]\s+\S"),  # unordered lists
    re.compile(r"(^|\n)\s{0,3}\d+\.\s+\S"),  # ordered lists
    re.compile(r"(^|\n)>\s+\S"),  # block quotes
    re.compile(r"`[^`]+`"),  # inline code
    re.compile(r"\|.+\|"),  # tables
    re.compile(r"\*\*[^*]+\*\*"),  # bold text
]


def contains_markdown(text: str) -> bool:
    """Returns True if the text contains Markdown syntax we want to render."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in MARKDOWN_PATTERNS)

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
            ("/clear-previous-messages", "Clear local prompt/history autocomplete cache"),
            ("/clear-server-history", "Clear server-side conversation history only"),
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
    
    elif cmd == "/clear-previous-messages":
        history_cleared = False
        try:
            if os.path.exists(HISTORY_FILE):
                open(HISTORY_FILE, 'w').close()
                if session and hasattr(session, 'history'):
                    session.history.store = []
                console.print("🗑️  Persistent command history cleared!", style="green")
                console.print("💡 Restart the client for complete history reset", style="dim cyan")
            else:
                console.print("ℹ️  No history file found to clear", style="yellow")
            history_cleared = True
        except Exception as e:
            console.print(f"❌ Error clearing history: {e}", style=ERROR_STYLE)

        return True, session_id, args, history_cleared

    elif cmd == "/clear-server-history":
        clear_server_history(session_id=session_id, args=args)
        return True, session_id, args, False
    
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
    """Streams a chat response from the server with rich formatting using httpx."""
    if not url.endswith('/v1/chat'):
        url = url.rstrip('/') + '/v1/chat'

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Session-ID": session_id,
        "Cache-Control": "no-cache",
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
        full_response = ""
        buffer = ""
        live_display = Live(
            Text("", style=ASSISTANT_STYLE),
            console=console,
            refresh_per_second=10,
            transient=False
        )
        live_started = False
        render_markdown = False

        # Use httpx for true streaming - it doesn't buffer like requests
        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream("POST", url, headers=headers, json=data) as response:
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

                    try:
                        line_buffer = ""
                        chunk_count = 0

                        # iter_text() yields text as it arrives - no buffering
                        for chunk in response.iter_text():
                            if not chunk:
                                continue

                            chunk_count += 1
                            if debug:
                                console.print(f"[dim]CHUNK #{chunk_count}: {len(chunk)} bytes[/dim]")

                            line_buffer += chunk

                            # Process complete lines (SSE format ends with \n)
                            while '\n' in line_buffer:
                                line, line_buffer = line_buffer.split('\n', 1)
                                line = line.strip()

                                if not line or not line.startswith('data: '):
                                    continue

                                data_text = line[6:].strip()
                                if not data_text or data_text == "[DONE]":
                                    continue

                                try:
                                    chunk_data = json.loads(data_text)
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                        # Stop the progress spinner immediately on first token
                                        if progress:
                                            progress.stop()
                                            progress = None

                                    if "response" in chunk_data:
                                        new_text = chunk_data.get("response", "")
                                        if new_text:
                                            buffer += new_text
                                            if not live_started:
                                                live_display.start()
                                                live_started = True
                                            render_markdown = render_markdown or contains_markdown(buffer)
                                            if render_markdown:
                                                live_display.update(Markdown(buffer))
                                            else:
                                                live_display.update(Text(buffer, style=ASSISTANT_STYLE))

                                    elif "error" in chunk_data:
                                        error_msg = chunk_data.get("error", "Unknown error")
                                        if isinstance(error_msg, dict):
                                            error_msg = error_msg.get("message", "Unknown error")
                                        console.print(f"\n❌ Error from server: {error_msg}", style=ERROR_STYLE)
                                        return error_msg, None

                                except json.JSONDecodeError as e:
                                    if debug:
                                        console.print(f"\n❌ JSON decode error: {e} for data: {data_text}", style=ERROR_STYLE)
                                    continue
                                except Exception as e:
                                    if debug:
                                        console.print(f"\n❌ Error processing chunk: {e}", style=ERROR_STYLE)
                                    continue

                        # Set the final cleaned response
                        full_response = clean_response(buffer)
                        if live_started and full_response:
                            final_markdown = contains_markdown(full_response)
                            if final_markdown:
                                live_display.update(Markdown(full_response))
                            else:
                                live_display.update(Text(full_response, style=ASSISTANT_STYLE))

                    except Exception as e:
                        if debug:
                            console.print(f"\n❌ Streaming error: {e}", style=ERROR_STYLE)
                        raise
        finally:
            if live_started:
                live_display.stop()

        end_time = time.time()
        total_time = end_time - start_time
        time_to_first_token = first_token_time - start_time if first_token_time else None
        return full_response, {"total_time": total_time, "time_to_first_token": time_to_first_token}

    except httpx.RequestError as e:
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
    
    # Validate API key if provided before starting the chat client
    if args.api_key:
        try:
            client = OrbitChatClient(
                api_url=args.url,
                api_key=args.api_key,
                timeout=30,
                verbose=args.debug
            )
            client.validate_api_key()
            if args.debug:
                console.print(f"[green]✓[/green] API key validated successfully", style="green")
        except ValueError as e:
            console.print(f"❌ {e}", style=ERROR_STYLE)
            sys.exit(1)
        except RuntimeError as e:
            console.print(f"❌ API key validation failed: {e}", style=ERROR_STYLE)
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Error validating API key: {e}", style=ERROR_STYLE)
            sys.exit(1)

    session_id = args.session_id if args.session_id else str(uuid.uuid4())
    session = PromptSession(
        history=FileHistory(HISTORY_FILE),
        completer=SlashCommandCompleter(),
        style=prompt_style,
        complete_style=CompleteStyle.COLUMN
    )
    setattr(session.default_buffer, "_orbit_completion_shift", -1)

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
                clear_server_history(session_id=session_id, args=args)
                break
            
            # Handle slash commands
            if user_input.startswith('/'):
                continue_chat, session_id, args, history_cleared = handle_slash_command(user_input, session_id, args, session)
                if not continue_chat:
                    clear_server_history(session_id=session_id, args=args)
                    break
                if history_cleared:
                    # Recreate the session with fresh history
                    session = PromptSession(
                        history=FileHistory(HISTORY_FILE),
                        completer=SlashCommandCompleter(),
                        style=prompt_style,
                        complete_style=CompleteStyle.COLUMN
                    )
                    setattr(session.default_buffer, "_orbit_completion_shift", -1)
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

            # If exiting, attempt to clear server history before goodbye
    console.print("\n[bold cyan]👋 Goodbye![/bold cyan]")

if __name__ == "__main__":
    main()
def clear_server_history(session_id: str, args) -> None:
    """Attempt to clear server-side conversation history for the current session."""
    if not session_id:
        console.print("❌ No active session ID available to clear on the server", style=ERROR_STYLE)
        return

    if not args.api_key:
        console.print(
            "⚠️  Set an API key to clear server-side conversation history",
            style=WARNING_STYLE
        )
        return

    try:
        client = OrbitChatClient(
            api_url=args.url,
            api_key=args.api_key,
            session_id=session_id,
            verbose=args.debug
        )
        result = client.clear_conversation_history()
        deleted_count = result.get('deleted_count', 0)
        console.print(
            f"🧹 Server history cleared for session {session_id}: {deleted_count} messages removed",
            style="green"
        )
    except Exception as exc:
        error_msg = str(exc)
        # Check if the error is due to adapter not supporting conversation history
        if "Chat history management is only available" in error_msg:
            # This is not an error - some adapters don't support history management
            if args.debug:
                console.print(f"ℹ️  Chat history not available for this adapter: {error_msg}", style="dim")
        else:
            # For other errors, show them as actual errors
            console.print(f"❌ Error clearing server history: {exc}", style=ERROR_STYLE)
