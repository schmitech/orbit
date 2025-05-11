#!/usr/bin/env python3
"""
ORBIT Manager Interactive CLI
=========================================

An interactive CLI wrapper for the ORBIT Manager Utility.
Provides a more user-friendly interface similar to AWS CLI or Azure CLI.

Features:
- Interactive prompts for all commands
- Command completion
- Colorful output
- Command history
- Help documentation

Usage:
  python orbit_cli.py

Examples:
  > orbit api-key create
  > orbit prompt list
  > orbit help
"""

import os
import sys
import json
import yaml
import argparse
import cmd
import shutil
import tempfile
from pathlib import Path
from textwrap import dedent
from datetime import datetime
import subprocess
import re

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.styles import Style
    import click
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("For the best experience, install additional packages:")
    print("pip install prompt_toolkit click rich")

# Constants
DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_CONFIG_PATH = Path.home() / ".orbit" / DEFAULT_CONFIG_FILE
CLI_HISTORY_FILE = Path.home() / ".orbit" / "history"
ORBIT_SCRIPT_PATH = __file__
VERSION = "0.0.1"

# Ensure all required directories exist
orbit_dir = Path.home() / ".orbit"
for subdir in ["data", "logs", "backups"]:
    (orbit_dir / subdir).mkdir(exist_ok=True, parents=True)

# Initialize rich console if available
if RICH_AVAILABLE:
    console = Console()
else:
    # Mock console with print
    class MockConsole:
        def print(self, *args, **kwargs):
            print(*args)
    console = MockConsole()

def create_default_config():
    """Create a default configuration file if none exists"""
    if not DEFAULT_CONFIG_PATH.exists():
        default_config = {
            "application": {
                "name": "API Key Manager",
                "log_level": "info",
                "log_file": str(Path.home() / ".orbit" / "logs" / "api_manager.log")
            },
            "database": {
                "engine": "sqlite",
                "connection": {
                    "sqlite": {
                        "database": str(Path.home() / ".orbit" / "data" / "api_keys.db")
                    },
                    "postgres": {
                        "host": "localhost",
                        "port": 5432,
                        "database": "api_keys",
                        "user": "postgres",
                        "password": "password",
                        "sslmode": "prefer"
                    },
                    "mysql": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "api_keys",
                        "user": "root",
                        "password": "password",
                        "charset": "utf8mb4"
                    },
                    "oracle": {
                        "host": "localhost",
                        "port": 1521,
                        "service_name": "XEPDB1",
                        "user": "system",
                        "password": "password"
                    },
                    "mssql": {
                        "host": "localhost",
                        "port": 1433,
                        "database": "api_keys",
                        "user": "sa",
                        "password": "password",
                        "driver": "ODBC Driver 17 for SQL Server"
                    }
                },
                "pool": {
                    "min_size": 1,
                    "max_size": 10,
                    "timeout": 30
                },
                "retry": {
                    "max_attempts": 3,
                    "backoff_factor": 2
                }
            },
            "api_keys": {
                "prefix": "orbit_",
                "length": 16,
                "characters": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            },
            "prompts": {
                "default_version": "1.0",
                "templates_dir": "templates"
            }
        }
        
        DEFAULT_CONFIG_PATH.parent.mkdir(exist_ok=True)
        with open(DEFAULT_CONFIG_PATH, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        
        console.print(f"Created default configuration at {DEFAULT_CONFIG_PATH}")

def find_orbit_script():
    """Find the orbit.py script, check current directory first"""
    # Look in the current directory for orbit.py
    current_dir_script = Path("orbit.py")
    if current_dir_script.exists():
        return str(current_dir_script.absolute())
    
    # If not found, check if it's in the same directory as this script
    script_dir = Path(__file__).parent
    script_dir_orbit = script_dir / "orbit.py"
    if script_dir_orbit.exists():
        return str(script_dir_orbit)
    
    # Check in the src directory
    src_dir = script_dir / "src"
    src_dir_orbit = src_dir / "orbit.py"
    if src_dir_orbit.exists():
        return str(src_dir_orbit)
    
    # Check in the parent directory
    parent_dir = script_dir.parent
    parent_dir_orbit = parent_dir / "orbit.py"
    if parent_dir_orbit.exists():
        return str(parent_dir_orbit)
    
    # Return the name only and hope it's in PATH
    return "orbit.py"

def run_orbit_command(orbit_script, config_file, command_parts):
    """Run the orbit.py script with the specified command"""
    cmd = [sys.executable, orbit_script, "--config", config_file] + command_parts
    
    try:
        # Check if the script exists
        if not os.path.exists(orbit_script):
            return False, f"Error: Could not find orbit.py script at {orbit_script}"
        
        # Check if the config file exists
        if not os.path.exists(config_file):
            return False, f"Error: Configuration file not found at {config_file}"
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return False, f"Error executing command: {error_msg}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def display_result(success, output, as_table=False, title="Result"):
    """Display the command result in a nice format"""
    if not RICH_AVAILABLE:
        print(output)
        return
    
    if not success:
        console.print(Panel(output, title="Error", border_style="red"))
        return
    
    # Try to parse JSON output
    try:
        if as_table:
            # Parse the JSON output
            json_data = None
            # Find JSON part in the output
            json_match = re.search(r'(\[.*\]|\{.*\})', output, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group(0))
            
            if json_data:
                if isinstance(json_data, list) and len(json_data) > 0:
                    # Create a table for list outputs
                    table = Table(title=title)
                    
                    # Add columns based on the first item
                    first_item = json_data[0]
                    for key in first_item.keys():
                        # Skip prompt_text column for table display as it's usually very large
                        if key == "prompt_text":
                            continue
                        table.add_column(key, style="cyan")
                    
                    # Add rows
                    for item in json_data:
                        row = []
                        for key in first_item.keys():
                            # Skip prompt_text column for table display
                            if key == "prompt_text":
                                continue
                                
                            value = item.get(key, "")
                            if value is None:
                                value = ""
                            elif isinstance(value, bool):
                                value = "✓" if value else "✗"
                            elif isinstance(value, str) and len(value) > 50 and key != "api_key":
                                # Truncate long text fields for better display
                                value = value[:47] + "..."
                            elif not isinstance(value, str):
                                value = str(value)
                            row.append(value)
                        table.add_row(*row)
                    
                    console.print(table)
                    
                    # Print the count message if present
                    count_match = re.search(r'Found (\d+) .*', output)
                    if count_match:
                        console.print(count_match.group(0), style="bold green")
                    return
                elif isinstance(json_data, dict):
                    # Display dictionary as a panel
                    panel_content = ""
                    for key, value in json_data.items():
                        if key == "prompt_text" and isinstance(value, str) and len(value) > 100:
                            # Truncate long prompt texts for display
                            value = value[:100] + "..."
                        panel_content += f"[bold cyan]{key}[/bold cyan]: {value}\n"
                    
                    console.print(Panel(panel_content, title="Result", border_style="green"))
                    return
        
        # If we couldn't create a table or for non-table output
        syntax = Syntax(output, "json", theme="monokai", line_numbers=False)
        console.print(syntax)
    except (json.JSONDecodeError, Exception) as e:
        # If parsing failed, just print the output
        console.print(output)

class OrbitShell(cmd.Cmd):
    intro = """
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃           ORBIT Manager Interactive CLI      ┃
    ┃           Version: {0}                      ┃
    ┃                                              ┃
    ┃  Type 'help' or '?' for available commands   ┃
    ┃  Type 'exit' or 'quit' to exit               ┃
    ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
    """.format(VERSION)
    
    test_intro = """
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃           ORBIT Manager Interactive CLI      ┃
    ┃                 TEST MODE                    ┃
    ┃           Version: {0}                      ┃
    ┃                                              ┃
    ┃  Type 'help' or '?' for available commands   ┃
    ┃  Type 'exit' or 'quit' to exit               ┃
    ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
    """.format(VERSION)
    
    prompt = "orbit> "
    
    def __init__(self, orbit_script=None, config_file=None):
        super().__init__()
        self.orbit_script = orbit_script or find_orbit_script()
        self.config_file = config_file or str(DEFAULT_CONFIG_PATH)
        
        # Create prompt toolkit session if available
        if 'prompt_toolkit' in sys.modules:
            # Create command completer
            orbit_commands = [
                'api-key create', 'api-key list', 'api-key deactivate', 
                'api-key delete', 'api-key test', 'api-key status',
                'prompt create', 'prompt list', 'prompt get', 
                'prompt update', 'prompt delete', 'prompt associate',
                'config edit', 'config show', 
                'test run', 'test report',
                'help', 'exit', 'quit'
            ]
            self.completer = WordCompleter(orbit_commands, ignore_case=True)
            
            # Create history file if it doesn't exist
            CLI_HISTORY_FILE.parent.mkdir(exist_ok=True, parents=True)
            if not CLI_HISTORY_FILE.exists():
                CLI_HISTORY_FILE.touch(mode=0o600)  # Secure permissions
            
            # Initialize prompt session
            self.session = PromptSession(
                history=FileHistory(str(CLI_HISTORY_FILE)),
                auto_suggest=AutoSuggestFromHistory(),
                complete_in_thread=True,
                complete_while_typing=True
            )
    
    def cmdloop(self, intro=None):
        """Overridden cmdloop to handle keyboard interrupts"""
        if intro is not None:
            self.intro = intro
        if self.intro:
            if RICH_AVAILABLE:
                console.print(self.intro)
            else:
                print(self.intro)
        
        while True:
            try:
                # Use prompt_toolkit if available
                if hasattr(self, 'session'):
                    try:
                        line = self.session.prompt(
                            self.prompt,
                            completer=self.completer
                        )
                    except KeyboardInterrupt:
                        print("\nOperation cancelled.")
                        continue
                    except EOFError:
                        print("\nExiting...")
                        sys.exit(0)
                else:
                    try:
                        line = input(self.prompt)
                    except KeyboardInterrupt:
                        print("\nOperation cancelled.")
                        continue
                    except EOFError:
                        print("\nExiting...")
                        sys.exit(0)
                    
                if line == 'EOF':
                    break
                
                # Handle the command
                if line.lower() in ['exit', 'quit']:
                    print("Exiting...")
                    sys.exit(0)
                
                self.onecmd(line)
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
            except EOFError:
                print("\nExiting...")
                sys.exit(0)
            except Exception as e:
                print(f"Error: {e}")
                if isinstance(e, SystemExit):
                    raise  # Re-raise SystemExit to ensure the program exits
    
    def default(self, line):
        """Handle unknown commands"""
        if line.lower() in ['exit', 'quit']:
            return self.do_exit(line)
        
        # Split the command into parts
        parts = line.split()
        if not parts:
            return
            
        # Handle api-key commands
        if parts[0] == 'api-key' and len(parts) > 1:
            return self.do_api_key(' '.join(parts[1:]))
            
        # Handle prompt commands
        if parts[0] == 'prompt' and len(parts) > 1:
            return self.do_prompt(' '.join(parts[1:]))
            
        # Handle config commands
        if parts[0] == 'config' and len(parts) > 1:
            return self.do_config(' '.join(parts[1:]))
            
        # Handle test commands
        if parts[0] == 'test' and len(parts) > 1:
            return self.do_test(' '.join(parts[1:]))
            
        print(f"Unknown command: {line}")
        print("Type 'help' for a list of commands.")
    
    def emptyline(self):
        """Do nothing on empty line"""
        pass
    
    def do_exit(self, arg):
        """Exit the program"""
        print("Exiting...")
        sys.exit(0)  # Force exit
    
    def do_quit(self, arg):
        """Exit the program (alias for exit)"""
        return self.do_exit(arg)
    
    def do_help(self, arg):
        """Show help information"""
        if not arg:
            # Show general help
            help_text = """
            ORBIT Manager Interactive CLI
            =============================
            
            API Key Commands:
              api-key create      Create a new API key
              api-key list        List all API keys
              api-key deactivate  Deactivate an API key
              api-key delete      Delete an API key
              api-key test        Test an API key
              api-key status      Get the status of an API key
            
            System Prompt Commands:
              prompt create       Create a new system prompt
              prompt list         List all system prompts
              prompt get          Get a system prompt by ID
              prompt update       Update an existing system prompt
              prompt delete       Delete a system prompt
              prompt associate    Associate a system prompt with an API key
            
            Configuration Commands:
              config edit         Edit the configuration file
              config show         Show the current configuration
            
            Test Commands:
              test run            Run the test suite
              test report         Show the most recent test report
            
            General Commands:
              help                Show this help information
              exit/quit           Exit the program
            
            For more help on a specific command, type: help <command>
            
            Examples:
              # Create a new API key
              orbit> api-key create
              Collection name: customer_data
              Client name: Customer Support
              Notes (optional): For support portal
              Associate with a system prompt? [y/N]: y
              
              # List all API keys
              orbit> api-key list
              ╭─────────────────────────────────────────╮
              │ Results                                 │
              ├──────┬─────────────┬──────────┬─────────┤
              │ id   │ api_key     │ collection_name    │
              ├──────┼─────────────┼──────────┼─────────┤
              │ 1    │ api_abc123  │ customer_data      │
              │ 2    │ api_def456  │ analytics          │
              ╰──────┴─────────────┴──────────┴─────────╯
              
              # Create a system prompt
              orbit> prompt create
              Prompt name: Customer Service
              Version (1.0): 
              Enter the prompt text (opens in editor):
              
              # Test an API key
              orbit> api-key test
              Enter API key to test: api_abc123
            """
            
            if RICH_AVAILABLE:
                console.print(Panel(dedent(help_text), title="Help", border_style="blue"))
            else:
                print(dedent(help_text))
        else:
            # Show help for a specific command
            if arg == "api-key create":
                help_text = """
                api-key create - Create a new API key
                
                Interactive command that will prompt for:
                - Collection name to associate with the key
                - Client name
                - Optional notes about this API key
                - Optional association with a system prompt
                
                Example:
                  orbit> api-key create
                  Collection name: customer_data
                  Client name: Customer Support
                  Notes (optional): For support portal
                  Associate with a system prompt? [y/N]: y
                """
                console.print(Panel(dedent(help_text), title="Help: api-key create", border_style="blue"))
            
            elif arg == "api-key list":
                help_text = """
                api-key list - List all API keys
                
                Shows all API keys in the database with their details.
                
                Example:
                  orbit> api-key list
                  ╭─────────────────────────────────────────╮
                  │ Results                                 │
                  ├──────┬─────────────┬──────────┬─────────┤
                  │ id   │ api_key     │ collection_name    │
                  ├──────┼─────────────┼──────────┼─────────┤
                  │ 1    │ api_abc123  │ customer_data      │
                  │ 2    │ api_def456  │ analytics          │
                  ╰──────┴─────────────┴──────────┴─────────╯
                """
                console.print(Panel(dedent(help_text), title="Help: api-key list", border_style="blue"))
            
            elif arg == "prompt create":
                help_text = """
                prompt create - Create a new system prompt
                
                Interactive command that will prompt for:
                - Prompt name
                - Version (defaults to 1.0)
                - Prompt text (opens in your default editor)
                
                Example:
                  orbit> prompt create
                  Prompt name: Customer Service
                  Version (1.0): 
                  Enter the prompt text (opens in editor):
                """
                console.print(Panel(dedent(help_text), title="Help: prompt create", border_style="blue"))
            
            elif arg == "config edit":
                help_text = """
                config edit - Edit the configuration file
                
                Opens the configuration file in your default text editor.
                After saving and closing, the configuration will be reloaded.
                
                The configuration file is located at ~/.orbit/config.yaml
                and contains settings for:
                - Database connection
                - API key settings
                - Prompt templates
                - Logging configuration
                
                Example:
                  orbit> config edit
                  # Opens your default editor with the config file
                """
                console.print(Panel(dedent(help_text), title="Help: config edit", border_style="blue"))
            
            elif arg == "test run":
                help_text = """
                test run - Run the test suite
                
                Executes the test suite and generates a detailed HTML report.
                The report will be saved in the test_reports directory.
                
                Example:
                  orbit> test run
                  Running tests...
                  Test report generated: ./test_reports/test_report_20240311_123456.html
                """
                console.print(Panel(dedent(help_text), title="Help: test run", border_style="blue"))
            
            else:
                print(f"No detailed help available for '{arg}'")
    
    def do_api_key(self, arg):
        """Handle API key commands"""
        args = arg.split()
        
        if not args:
            print("Missing API key command. Use 'api-key create|list|deactivate|delete|test|status'")
            return
        
        command = args[0]
        
        # Map the interactive subcommand to the backend script command
        if command == "create":
            self._handle_api_key_create()
        elif command == "list":
            success, output = run_orbit_command(self.orbit_script, self.config_file, ["list"])
            display_result(success, output, as_table=True)
        elif command == "deactivate":
            self._handle_api_key_deactivate()
        elif command == "delete":
            self._handle_api_key_delete()
        elif command == "test":
            self._handle_api_key_test()
        elif command == "status":
            self._handle_api_key_status()
        else:
            print(f"Unknown API key command: {command}")
            print("Available commands: create, list, deactivate, delete, test, status")
    
    def _handle_api_key_create(self):
        """Handle API key create command interactively"""
        if RICH_AVAILABLE:
            collection = click.prompt("Collection name", type=str)
            name = click.prompt("Client name", type=str)
            notes = click.prompt("Notes (optional)", default="", show_default=False)
            
            # Check if we should associate with a prompt
            associate_prompt = click.confirm("Associate with a system prompt?", default=False)
            
            prompt_args = []
            if associate_prompt:
                # Get available prompts
                success, output = run_orbit_command(self.orbit_script, self.config_file, ["prompt", "list"])
                
                if success:
                    try:
                        # Parse the JSON output
                        json_match = re.search(r'(\[.*\])', output, re.DOTALL)
                        if json_match:
                            prompts = json.loads(json_match.group(0))
                            
                            if prompts:
                                # Display available prompts
                                table = Table(title="Available Prompts")
                                table.add_column("ID", style="cyan")
                                table.add_column("Name", style="green")
                                table.add_column("Version", style="yellow")
                                
                                for prompt in prompts:
                                    table.add_row(
                                        str(prompt["id"]),
                                        prompt["name"],
                                        prompt["version"]
                                    )
                                
                                console.print(table)
                                
                                # Get prompt ID from user
                                prompt_id = click.prompt(
                                    "Enter prompt ID to associate (or 'new' to create a new prompt)", 
                                    type=str
                                )
                                
                                if prompt_id.lower() == 'new':
                                    # Create a new prompt
                                    prompt_name = click.prompt("Prompt name", type=str)
                                    
                                    # Create a temporary file for the prompt text
                                    with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp:
                                        temp_file = temp.name
                                        console.print("Enter the prompt text (Ctrl+D when done):")
                                        
                                        # Use an editor for the prompt text
                                        click.edit(filename=temp_file)
                                    
                                    try:
                                        # Create the prompt
                                        success, output = run_orbit_command(
                                            self.orbit_script, 
                                            self.config_file, 
                                            ["prompt", "create", "--name", prompt_name, "--file", temp_file]
                                        )
                                        
                                        if success:
                                            # Parse the prompt ID from the output
                                            prompt_data = json.loads(re.search(r'(\{.*\})', output, re.DOTALL).group(0))
                                            prompt_id = str(prompt_data["id"])
                                            prompt_args = ["--prompt-id", prompt_id]
                                        else:
                                            console.print("Failed to create prompt:", style="red")
                                            console.print(output)
                                            return
                                    finally:
                                        # Clean up the temporary file
                                        if os.path.exists(temp_file):
                                            os.unlink(temp_file)
                                else:
                                    # Use existing prompt
                                    prompt_args = ["--prompt-id", prompt_id]
                    except (json.JSONDecodeError, Exception) as e:
                        console.print(f"Error parsing prompts: {e}", style="red")
                        return
                else:
                    console.print("Failed to retrieve prompts:", style="red")
                    console.print(output)
                    return
        else:
            # Fallback for when rich/click is not available
            collection = input("Collection name: ")
            name = input("Client name: ")
            notes = input("Notes (optional): ")
            
            # Check if we should associate with a prompt
            associate_prompt = input("Associate with a system prompt? (y/n): ").lower() == 'y'
            
            prompt_args = []
            if associate_prompt:
                prompt_id = input("Enter prompt ID to associate: ")
                prompt_args = ["--prompt-id", prompt_id]
        
        # Construct the command
        cmd_args = ["create", "--collection", collection, "--name", name]
        
        if notes:
            cmd_args.extend(["--notes", notes])
        
        cmd_args.extend(prompt_args)
        
        # Execute the command
        success, output = run_orbit_command(self.orbit_script, self.config_file, cmd_args)
        display_result(success, output)
    
    def _handle_api_key_deactivate(self):
        """Handle API key deactivate command interactively"""
        if RICH_AVAILABLE:
            api_key = click.prompt("Enter API key to deactivate", type=str)
        else:
            api_key = input("Enter API key to deactivate: ")
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["deactivate", "--key", api_key]
        )
        display_result(success, output)
    
    def _handle_api_key_delete(self):
        """Handle API key delete command interactively"""
        if RICH_AVAILABLE:
            api_key = click.prompt("Enter API key to delete", type=str)
            confirm = click.confirm(f"Are you sure you want to delete API key {api_key}?", default=False)
            
            if not confirm:
                console.print("Operation cancelled.")
                return
        else:
            api_key = input("Enter API key to delete: ")
            confirm = input(f"Are you sure you want to delete API key {api_key}? (y/n): ").lower() == 'y'
            
            if not confirm:
                print("Operation cancelled.")
                return
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["delete", "--key", api_key]
        )
        display_result(success, output)
    
    def _handle_api_key_test(self):
        """Handle API key test command interactively"""
        if RICH_AVAILABLE:
            api_key = click.prompt("Enter API key to test", type=str)
        else:
            api_key = input("Enter API key to test: ")
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["test", "--key", api_key]
        )
        display_result(success, output)
    
    def _handle_api_key_status(self):
        """Handle API key status command interactively"""
        if RICH_AVAILABLE:
            api_key = click.prompt("Enter API key to check", type=str)
        else:
            api_key = input("Enter API key to check: ")
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["status", "--key", api_key]
        )
        display_result(success, output)
    
    def do_prompt(self, arg):
        """Handle prompt commands"""
        args = arg.split()
        
        if not args:
            print("Missing prompt command. Use 'prompt create|list|get|update|delete|associate'")
            return
        
        command = args[0]
        
        if command == "create":
            self._handle_prompt_create()
        elif command == "list":
            success, output = run_orbit_command(
                self.orbit_script, 
                self.config_file, 
                ["prompt", "list"]
            )
            display_result(success, output, as_table=True)
        elif command == "get":
            self._handle_prompt_get()
        elif command == "update":
            self._handle_prompt_update()
        elif command == "delete":
            self._handle_prompt_delete()
        elif command == "associate":
            self._handle_prompt_associate()
        else:
            print(f"Unknown prompt command: {command}")
            print("Available commands: create, list, get, update, delete, associate")
    
    def _handle_prompt_create(self):
        """Handle prompt create command interactively"""
        if RICH_AVAILABLE:
            name = click.prompt("Prompt name", type=str)
            version = click.prompt("Version (optional)", default="1.0", show_default=True)
            
            # Create a temporary file for the prompt text
            with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp:
                temp_file = temp.name
                console.print("Enter the prompt text (opens in editor):")
                
                # Use an editor for the prompt text
                click.edit(filename=temp_file)
        else:
            name = input("Prompt name: ")
            version = input("Version (default 1.0): ") or "1.0"
            
            # Create a temporary file for the prompt text
            with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp:
                temp_file = temp.name
                print("Enter the prompt text (end with Ctrl+D):")
                
                # Simple multi-line input
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                
                temp.write("\n".join(lines))
                temp.flush()
        
        try:
            # Construct the command
            cmd_args = ["prompt", "create", "--name", name, "--file", temp_file]
            
            if version and version != "1.0":
                cmd_args.extend(["--version", version])
            
            # Execute the command
            success, output = run_orbit_command(self.orbit_script, self.config_file, cmd_args)
            display_result(success, output)
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def _handle_prompt_get(self):
        """Handle prompt get command interactively"""
        if RICH_AVAILABLE:
            prompt_id = click.prompt("Enter prompt ID", type=int)
        else:
            prompt_id = int(input("Enter prompt ID: "))
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["prompt", "get", "--id", str(prompt_id)]
        )
        display_result(success, output)
    
    def _handle_prompt_update(self):
        """Handle prompt update command interactively"""
        if RICH_AVAILABLE:
            prompt_id = click.prompt("Enter prompt ID to update", type=int)
            version = click.prompt("New version (optional, leave empty to keep current)", default="", show_default=False)
            
            # Get current prompt to edit
            success, output = run_orbit_command(
                self.orbit_script, 
                self.config_file, 
                ["prompt", "get", "--id", str(prompt_id)]
            )
            
            if not success:
                console.print(f"Error retrieving prompt: {output}", style="red")
                return
            
            try:
                # Parse the JSON output to get current prompt text
                prompt_data = json.loads(re.search(r'(\{.*\})', output, re.DOTALL).group(0))
                current_text = prompt_data.get("prompt_text", "")
                
                # Create a temporary file with the current text
                with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp:
                    temp_file = temp.name
                    temp.write(current_text)
                    temp.flush()
                
                console.print("Edit the prompt text (opens in editor):")
                
                # Use an editor for the prompt text
                click.edit(filename=temp_file)
            except (json.JSONDecodeError, Exception) as e:
                console.print(f"Error parsing prompt data: {e}", style="red")
                return
        else:
            prompt_id = int(input("Enter prompt ID to update: "))
            version = input("New version (optional, leave empty to keep current): ")
            
            # Create a temporary file for the prompt text
            with tempfile.NamedTemporaryFile(mode='w+', suffix=".txt", delete=False) as temp:
                temp_file = temp.name
                print("Enter the new prompt text (end with Ctrl+D):")
                
                # Simple multi-line input
                lines = []
                try:
                    while True:
                        line = input()
                        lines.append(line)
                except EOFError:
                    pass
                
                temp.write("\n".join(lines))
                temp.flush()
        
        try:
            # Construct the command
            cmd_args = ["prompt", "update", "--id", str(prompt_id), "--file", temp_file]
            
            if version:
                cmd_args.extend(["--version", version])
            
            # Execute the command
            success, output = run_orbit_command(self.orbit_script, self.config_file, cmd_args)
            display_result(success, output)
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def _handle_prompt_delete(self):
        """Handle prompt delete command interactively"""
        if RICH_AVAILABLE:
            prompt_id = click.prompt("Enter prompt ID to delete", type=int)
            confirm = click.confirm(f"Are you sure you want to delete prompt with ID {prompt_id}?", default=False)
            
            if not confirm:
                console.print("Operation cancelled.")
                return
        else:
            prompt_id = int(input("Enter prompt ID to delete: "))
            confirm = input(f"Are you sure you want to delete prompt with ID {prompt_id}? (y/n): ").lower() == 'y'
            
            if not confirm:
                print("Operation cancelled.")
                return
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["prompt", "delete", "--id", str(prompt_id)]
        )
        display_result(success, output)
    
    def _handle_prompt_associate(self):
        """Handle prompt associate command interactively"""
        if RICH_AVAILABLE:
            api_key = click.prompt("Enter API key", type=str)
            prompt_id = click.prompt("Enter prompt ID to associate", type=int)
        else:
            api_key = input("Enter API key: ")
            prompt_id = int(input("Enter prompt ID to associate: "))
        
        # Execute the command
        success, output = run_orbit_command(
            self.orbit_script, 
            self.config_file, 
            ["prompt", "associate", "--key", api_key, "--prompt-id", str(prompt_id)]
        )
        display_result(success, output)
    
    def do_config(self, arg):
        """Handle configuration commands"""
        args = arg.split()
        
        if not args:
            print("Missing config command. Use 'config edit|show'")
            return
        
        command = args[0]
        
        if command == "edit":
            self._handle_config_edit()
        elif command == "show":
            self._handle_config_show()
        else:
            print(f"Unknown config command: {command}")
            print("Available commands: edit, show")
            
    def do_test(self, arg):
        """Handle test commands"""
        args = arg.split()
        
        if not args:
            print("Missing test command. Use 'test run|report'")
            return
        
        command = args[0]
        
        if command == "run":
            self._handle_test_run()
        elif command == "report":
            self._handle_test_report()
        else:
            print(f"Unknown test command: {command}")
            print("Available commands: run, report")
            
    def _handle_test_run(self):
        """Handle test run command"""
        if RICH_AVAILABLE:
            # Ask for confirmation
            if not click.confirm("This will run the test suite. Continue?", default=True):
                console.print("Operation cancelled.")
                return
                
            with console.status("Running tests..."):
                # Import the test runner
                script_dir = Path(__file__).parent
                sys.path.insert(0, str(script_dir))
                
                try:
                    import test_commands
                    success, output = test_commands.run_tests(self.config_file)
                    
                    if success:
                        console.print(Panel(output, title="Tests Passed", border_style="green"))
                    else:
                        console.print(Panel(output, title="Tests Failed", border_style="red"))
                except ImportError:
                    console.print("Error: test_commands.py not found", style="red")
                except Exception as e:
                    console.print(f"Error running tests: {str(e)}", style="red")
        else:
            # Simpler version without rich
            print("Running tests...")
            
            try:
                script_dir = Path(__file__).parent
                sys.path.insert(0, str(script_dir))
                
                import test_commands
                success, output = test_commands.run_tests(self.config_file)
                
                print("\n" + "=" * 40)
                print(output)
                print("=" * 40)
                
                if success:
                    print("\nTests passed successfully.")
                else:
                    print("\nTests failed.")
            except ImportError:
                print("Error: test_commands.py not found")
            except Exception as e:
                print(f"Error running tests: {str(e)}")
                
    def _handle_test_report(self):
        """Handle test report command"""
        try:
            script_dir = Path(__file__).parent
            sys.path.insert(0, str(script_dir))
            
            import test_commands
            success, message = test_commands.show_latest_report()
            
            if RICH_AVAILABLE:
                if success:
                    console.print(message, style="green")
                else:
                    console.print(message, style="yellow")
            else:
                print(message)
        except ImportError:
            if RICH_AVAILABLE:
                console.print("Error: test_commands.py not found", style="red")
            else:
                print("Error: test_commands.py not found")
        except Exception as e:
            if RICH_AVAILABLE:
                console.print(f"Error showing test report: {str(e)}", style="red")
            else:
                print(f"Error showing test report: {str(e)}")
    
    def _handle_config_edit(self):
        """Handle config edit command"""
        # Create default config if it doesn't exist
        if not os.path.exists(self.config_file):
            create_default_config()
        
        if RICH_AVAILABLE:
            # Open the config file in the default editor
            click.edit(filename=self.config_file)
            console.print(f"Configuration file updated: {self.config_file}", style="green")
        else:
            print(f"Please edit the configuration file manually: {self.config_file}")
    
    def _handle_config_show(self):
        """Handle config show command"""
        try:
            with open(self.config_file, 'r') as f:
                config_content = f.read()
                
            if RICH_AVAILABLE:
                syntax = Syntax(config_content, "yaml", theme="monokai", line_numbers=True)
                console.print(Panel(syntax, title=f"Configuration: {self.config_file}", border_style="blue"))
            else:
                print(f"Configuration ({self.config_file}):")
                print("-" * 40)
                print(config_content)
                print("-" * 40)
        except FileNotFoundError:
            if RICH_AVAILABLE:
                console.print(f"Configuration file not found: {self.config_file}", style="red")
                create = click.confirm("Create default configuration?", default=True)
                if create:
                    create_default_config()
                    self._handle_config_show()
            else:
                print(f"Configuration file not found: {self.config_file}")
                create = input("Create default configuration? (y/n): ").lower() == 'y'
                if create:
                    create_default_config()
                    self._handle_config_show()
        except Exception as e:
            if RICH_AVAILABLE:
                console.print(f"Error reading configuration: {e}", style="red")
            else:
                print(f"Error reading configuration: {e}")

def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(description="ORBIT Manager Interactive CLI")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the YAML configuration file")
    parser.add_argument("--orbit-script", help="Path to the orbit.py script")
    parser.add_argument("--test-mode", action="store_true", help="Run in test mode")
    parser.add_argument("command", nargs="*", help="Command to execute directly (non-interactive mode)")
    
    args = parser.parse_args()
    
    # Create default config if it doesn't exist
    if not os.path.exists(args.config):
        create_default_config()
        
    # Create required directories
    config_dir = Path(args.config).parent
    data_dir = config_dir / "data"
    logs_dir = config_dir / "logs"
    
    for directory in [data_dir, logs_dir]:
        directory.mkdir(exist_ok=True)
    
    # If we have direct commands, execute them
    if args.command:
        orbit_script = args.orbit_script or find_orbit_script()
        
        # Convert "api-key create" style commands to the backend format
        backend_cmd = []
        
        if args.command[0] == "api-key" and len(args.command) > 1:
            # Map the first part of the command
            if args.command[1] in ["create", "list", "deactivate", "delete", "test", "status"]:
                backend_cmd = [args.command[1]] + args.command[2:]
        elif args.command[0] == "prompt" and len(args.command) > 1:
            # Map prompt commands
            backend_cmd = ["prompt", args.command[1]] + args.command[2:]
        else:
            # Unknown command format
            print(f"Unknown command format: {' '.join(args.command)}")
            return
        
        # Execute the command
        success, output = run_orbit_command(orbit_script, args.config, backend_cmd)
        display_result(success, output, as_table=args.command[1] == "list")
    else:
        # Start interactive shell
        shell = OrbitShell(args.orbit_script, args.config)
        if args.test_mode:
            shell.intro = shell.test_intro
            shell.prompt = "orbit(test)> "
        shell.cmdloop()

if __name__ == "__main__":
    main()