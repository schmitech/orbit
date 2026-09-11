#!/usr/bin/env python3
r"""
ORBIT Control CLI - Entry Point
================================

A command-line tool to manage the ORBIT server.
Provides server control, API key management, system prompt management, and authentication.

This tool combines server management with API administration features.

Invocation:
    The CLI is not installed on PATH - it is run through the wrapper in bin/,
    which activates the virtual environment and checks the Python version.
    Examples below use the Unix wrapper; on Windows use bin\orbit.bat:
        ./bin/orbit.sh status       (Linux/macOS)
        bin\orbit.bat status        (Windows)

Global Options:
    --version                    Show version information
    --server-url URL            Server URL (default: from config or localhost:3000)
    --config PATH               Path to configuration file (for server start/restart)
    -v, --verbose               Enable verbose output
    --output {table,json}       Output format (default: table)
    --no-color                  Disable colored output
    --log-file PATH             Path to log file

Server Control Commands:
    ./bin/orbit.sh start [--config CONFIG_PATH] [--host HOST] [--port PORT] [--reload] [--delete-logs]
        Start the ORBIT server
        
    ./bin/orbit.sh stop [--timeout SECONDS] [--delete-logs] [--force]
        Stop the ORBIT server gracefully
        
    ./bin/orbit.sh restart [--config CONFIG_PATH] [--host HOST] [--port PORT] [--delete-logs]
        Restart the ORBIT server
        
    ./bin/orbit.sh status [--watch] [--interval SECONDS]
        Check ORBIT server status

Authentication Commands:
    ./bin/orbit.sh login [--username USERNAME] [--password PASSWORD] [--no-save]
        Login to the ORBIT server (will prompt if credentials not provided)
        Token stored based on config (keychain or ~/.orbit/.env)
        
    ./bin/orbit.sh logout [--all]
        Logout from the ORBIT server (clears token from storage)
        
    ./bin/orbit.sh register --username USERNAME [--password PASSWORD] [--role {user,admin}]
        Register a new user (admin only)
        
    ./bin/orbit.sh me
        Show current user information
        
    ./bin/orbit.sh auth-status
        Check authentication status

User Management Commands (Admin Only):
    ./bin/orbit.sh user list [--role {user,admin}] [--active-only] [--limit LIMIT] [--offset OFFSET]
        List all users
        
    ./bin/orbit.sh user reset-password --user-id ID [--password PASSWORD]
        Reset a user's password (generates random password if not provided)
        
    ./bin/orbit.sh user reset-password --username USERNAME [--password PASSWORD]
        Reset a user's password by username
        
    ./bin/orbit.sh user change-password [--current-password PASSWORD] [--new-password PASSWORD]
        Change your own password (interactive prompts if not provided)
        
    ./bin/orbit.sh user deactivate --user-id ID [--force]
        Deactivate a user
        
    ./bin/orbit.sh user activate --user-id ID [--force]
        Activate a user
        
    ./bin/orbit.sh user delete --user-id ID [--force]
        Delete a user

API Key Management Commands:
    ./bin/orbit.sh key create --adapter ADAPTER --name NAME [--notes NOTES] [--notes-file FILE] [--prompt-id ID] [--prompt-name NAME] [--prompt-file FILE]
        Create a new API key for an adapter
        
    ./bin/orbit.sh key list [--active-only] [--limit LIMIT] [--offset OFFSET]
        List all API keys
        
    ./bin/orbit.sh key test --key API_KEY
        Test an API key
        
    ./bin/orbit.sh key status --key API_KEY
        Get API key status
        
    ./bin/orbit.sh key rename --old-key OLD_KEY --new-key NEW_KEY
        Rename an API key
        
    ./bin/orbit.sh key deactivate --key API_KEY
        Deactivate an API key
        
    ./bin/orbit.sh key delete --key API_KEY [--force]
        Delete an API key
        
    ./bin/orbit.sh key list-adapters
        List available adapters

System Prompt Management Commands:
    ./bin/orbit.sh prompt create --name NAME --file FILE [--version VERSION]
        Create a new system prompt
        
    ./bin/orbit.sh prompt list [--name-filter FILTER] [--limit LIMIT] [--offset OFFSET]
        List all system prompts
        
    ./bin/orbit.sh prompt get --id PROMPT_ID [--save FILE]
        Get a system prompt by ID
        
    ./bin/orbit.sh prompt update --id PROMPT_ID --file FILE [--version VERSION]
        Update an existing system prompt
        
    ./bin/orbit.sh prompt delete --id PROMPT_ID [--force]
        Delete a system prompt
        
    ./bin/orbit.sh prompt associate --key API_KEY --prompt-id PROMPT_ID
        Associate a system prompt with an API key

CLI Configuration Commands:
    ./bin/orbit.sh config show [--key KEY]
        Show CLI configuration
        
    ./bin/orbit.sh config effective [--key KEY] [--sources-only]
        Show effective CLI configuration with sources
        
    ./bin/orbit.sh config set KEY VALUE
        Set a CLI configuration value (dot notation, e.g., "server.timeout")
        
    ./bin/orbit.sh config reset [--force]
        Reset CLI configuration to defaults

Admin Operations Commands:
    ./bin/orbit.sh admin reload-adapters [--adapter ADAPTER_NAME]
        Reload adapter configurations from adapters.yaml without server restart

    ./bin/orbit.sh admin reload-templates [--adapter ADAPTER_NAME]
        Reload intent templates from template library files without server restart
        Re-indexes templates in the associated vector store

Examples:
    # Authentication
    ./bin/orbit.sh login --username admin --password secret123  # Or omit both to be prompted
    ./bin/orbit.sh me
    ./bin/orbit.sh register --username newuser --password pass123 --role user
    ./bin/orbit.sh logout
    ./bin/orbit.sh auth-status  # Check authentication status

    # User Management
    ./bin/orbit.sh user list                # List all users
    ./bin/orbit.sh user list --role admin   # List only admin users
    ./bin/orbit.sh user list --active-only  # List only active users
    ./bin/orbit.sh user reset-password --username admin --password newpass
    ./bin/orbit.sh user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass
    ./bin/orbit.sh user change-password                                    # Change your password (interactive)
    ./bin/orbit.sh user deactivate --user-id 507f1f77bcf86cd799439011      # Deactivate a user
    ./bin/orbit.sh user activate --user-id 507f1f77bcf86cd799439011        # Activate a user
    ./bin/orbit.sh user delete --user-id 507f1f77bcf86cd799439011          # Delete a user
    ./bin/orbit.sh user delete --user-id 507f1f77bcf86cd799439011 --force  # Skip confirmation

    # Server Management
    ./bin/orbit.sh start                             # Start the server
    ./bin/orbit.sh start --reload                    # Start with auto-reload
    ./bin/orbit.sh start --host 0.0.0.0 --port 8080  # Start on specific host/port
    ./bin/orbit.sh stop                              # Stop the server
    ./bin/orbit.sh stop --force                      # Force stop without graceful shutdown
    ./bin/orbit.sh stop --delete-logs                # Stop and delete logs
    ./bin/orbit.sh restart                           # Restart the server
    ./bin/orbit.sh status                            # Check server status
    ./bin/orbit.sh status --watch                    # Continuously monitor status
    ./bin/orbit.sh status --watch --interval 10      # Monitor with custom interval

    # API Key Management
    ./bin/orbit.sh key create --adapter city --name "City Assistant" --notes "For city queries"
    ./bin/orbit.sh key create --adapter city --name "City Assistant" --notes-file notes/city.txt
    ./bin/orbit.sh key create --adapter city --name "City Assistant" --prompt-file prompts/city.txt --prompt-name "City Prompt"
    ./bin/orbit.sh key list                       # List all API keys
    ./bin/orbit.sh key list --active-only         # List only active keys
    ./bin/orbit.sh key test --key YOUR_API_KEY    # Test an API key
    ./bin/orbit.sh key status --key YOUR_API_KEY  # Get API key status
    ./bin/orbit.sh key rename --old-key OLD_KEY --new-key NEW_KEY
    ./bin/orbit.sh key deactivate --key YOUR_API_KEY      # Deactivate an API key
    ./bin/orbit.sh key delete --key YOUR_API_KEY          # Delete an API key (with confirmation)
    ./bin/orbit.sh key delete --key YOUR_API_KEY --force  # Delete without confirmation
    ./bin/orbit.sh key list-adapters                      # List available adapters

    # System Prompt Management
    ./bin/orbit.sh prompt create --name "Support Assistant" --file prompts/support.txt --version "1.0"
    ./bin/orbit.sh prompt list                                  # List all prompts
    ./bin/orbit.sh prompt list --name-filter "Support"          # Filter prompts by name
    ./bin/orbit.sh prompt get --id PROMPT_ID                    # Get a prompt
    ./bin/orbit.sh prompt get --id PROMPT_ID --save prompt.txt  # Get and save to file
    ./bin/orbit.sh prompt update --id PROMPT_ID --file updated.txt --version "1.1"
    ./bin/orbit.sh prompt delete --id PROMPT_ID          # Delete a prompt (with confirmation)
    ./bin/orbit.sh prompt delete --id PROMPT_ID --force  # Delete without confirmation
    ./bin/orbit.sh prompt associate --key API_KEY --prompt-id PROMPT_ID

    # CLI Configuration
    ./bin/orbit.sh config show                       # Show all CLI configuration
    ./bin/orbit.sh config show --key server.timeout  # Show specific key
    ./bin/orbit.sh config effective                  # Show effective config with sources
    ./bin/orbit.sh config set server.timeout 60      # Set configuration value
    ./bin/orbit.sh config set output.format json     # Change output format
    ./bin/orbit.sh config reset                      # Reset to defaults (with confirmation)
    ./bin/orbit.sh config reset --force              # Reset without confirmation

    # Admin Operations
    ./bin/orbit.sh admin reload-adapters                                  # Reload all adapters
    ./bin/orbit.sh admin reload-adapters --adapter city                   # Reload specific adapter
    ./bin/orbit.sh admin reload-templates                                 # Reload templates for all intent adapters
    ./bin/orbit.sh admin reload-templates --adapter intent-sql-sqlite-hr  # Reload templates for specific adapter

    # Using different output formats
    ./bin/orbit.sh user list --output json  # Output as JSON
    ./bin/orbit.sh key list --output json   # Output as JSON
    ./bin/orbit.sh status --output json     # Output as JSON

    # Using different server URLs
    ./bin/orbit.sh --server-url http://remote-server:3000 status
    ./bin/orbit.sh --server-url http://remote-server:3000 login

    # Verbose mode for debugging
    ./bin/orbit.sh -v start  # Start with verbose logging
    ./bin/orbit.sh -v login  # Login with verbose logging

For more information about a specific command, use:
    ./bin/orbit.sh <command> --help

Configuration:
    Configuration files are stored in ~/.orbit/
    Authentication tokens are stored based on config (keychain or ~/.orbit/.env)
    Server settings must be managed through server API endpoints.

Report issues at: https://github.com/schmitech/orbit/issues
"""

import sys
from pathlib import Path

# Add the project root to sys.path so that 'bin.orbit' can be imported
# when this script is run directly (e.g., python bin/orbit.py)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from bin.orbit.cli import main

if __name__ == "__main__":
    main()
