#!/usr/bin/env python3
"""
ORBIT Control CLI - Entry Point
================================

A command-line tool to manage the ORBIT server.
Provides server control, API key management, system prompt management, and authentication.

This tool combines server management with API administration features.

Global Options:
    --version                    Show version information
    --server-url URL            Server URL (default: from config or localhost:3000)
    --config PATH               Path to configuration file (for server start/restart)
    -v, --verbose               Enable verbose output
    --output {table,json}       Output format (default: table)
    --no-color                  Disable colored output
    --log-file PATH             Path to log file

Server Control Commands:
    orbit start [--config CONFIG_PATH] [--host HOST] [--port PORT] [--reload] [--delete-logs]
        Start the ORBIT server
        
    orbit stop [--timeout SECONDS] [--delete-logs] [--force]
        Stop the ORBIT server gracefully
        
    orbit restart [--config CONFIG_PATH] [--host HOST] [--port PORT] [--delete-logs]
        Restart the ORBIT server
        
    orbit status [--watch] [--interval SECONDS]
        Check ORBIT server status

Authentication Commands:
    orbit login [--username USERNAME] [--password PASSWORD] [--no-save]
        Login to the ORBIT server (will prompt if credentials not provided)
        Token stored based on config (keychain or ~/.orbit/.env)
        
    orbit logout [--all]
        Logout from the ORBIT server (clears token from storage)
        
    orbit register --username USERNAME [--password PASSWORD] [--role {user,admin}]
        Register a new user (admin only)
        
    orbit me
        Show current user information
        
    orbit auth-status
        Check authentication status

User Management Commands (Admin Only):
    orbit user list [--role {user,admin}] [--active-only] [--limit LIMIT] [--offset OFFSET]
        List all users
        
    orbit user reset-password --user-id ID [--password PASSWORD]
        Reset a user's password (generates random password if not provided)
        
    orbit user reset-password --username USERNAME [--password PASSWORD]
        Reset a user's password by username
        
    orbit user change-password [--current-password PASSWORD] [--new-password PASSWORD]
        Change your own password (interactive prompts if not provided)
        
    orbit user deactivate --user-id ID [--force]
        Deactivate a user
        
    orbit user activate --user-id ID [--force]
        Activate a user
        
    orbit user delete --user-id ID [--force]
        Delete a user

API Key Management Commands:
    orbit key create --adapter ADAPTER --name NAME [--notes NOTES] [--prompt-id ID] [--prompt-name NAME] [--prompt-file FILE]
        Create a new API key for an adapter
        
    orbit key list [--active-only] [--limit LIMIT] [--offset OFFSET]
        List all API keys
        
    orbit key test --key API_KEY
        Test an API key
        
    orbit key status --key API_KEY
        Get API key status
        
    orbit key rename --old-key OLD_KEY --new-key NEW_KEY
        Rename an API key
        
    orbit key deactivate --key API_KEY
        Deactivate an API key
        
    orbit key delete --key API_KEY [--force]
        Delete an API key
        
    orbit key list-adapters
        List available adapters

System Prompt Management Commands:
    orbit prompt create --name NAME --file FILE [--version VERSION]
        Create a new system prompt
        
    orbit prompt list [--name-filter FILTER] [--limit LIMIT] [--offset OFFSET]
        List all system prompts
        
    orbit prompt get --id PROMPT_ID [--save FILE]
        Get a system prompt by ID
        
    orbit prompt update --id PROMPT_ID --file FILE [--version VERSION]
        Update an existing system prompt
        
    orbit prompt delete --id PROMPT_ID [--force]
        Delete a system prompt
        
    orbit prompt associate --key API_KEY --prompt-id PROMPT_ID
        Associate a system prompt with an API key

CLI Configuration Commands:
    orbit config show [--key KEY]
        Show CLI configuration
        
    orbit config effective [--key KEY] [--sources-only]
        Show effective CLI configuration with sources
        
    orbit config set KEY VALUE
        Set a CLI configuration value (dot notation, e.g., "server.timeout")
        
    orbit config reset [--force]
        Reset CLI configuration to defaults

Admin Operations Commands:
    orbit admin reload-adapters [--adapter ADAPTER_NAME]
        Reload adapter configurations from adapters.yaml without server restart

    orbit admin reload-templates [--adapter ADAPTER_NAME]
        Reload intent templates from template library files without server restart
        Re-indexes templates in the associated vector store

Examples:
    # Authentication
    orbit login --username admin --password secret123  # Or just 'orbit login' to be prompted
    orbit me
    orbit register --username newuser --password pass123 --role user
    orbit logout
    orbit auth-status                                   # Check authentication status

    # User Management
    orbit user list                                     # List all users
    orbit user list --role admin                        # List only admin users
    orbit user list --active-only                       # List only active users
    orbit user reset-password --username admin --password newpass
    orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass
    orbit user change-password                          # Change your password (interactive)
    orbit user deactivate --user-id 507f1f77bcf86cd799439011  # Deactivate a user
    orbit user activate --user-id 507f1f77bcf86cd799439011   # Activate a user
    orbit user delete --user-id 507f1f77bcf86cd799439011  # Delete a user
    orbit user delete --user-id 507f1f77bcf86cd799439011 --force  # Skip confirmation

    # Server Management
    orbit start                                         # Start the server
    orbit start --reload                                # Start with auto-reload
    orbit start --host 0.0.0.0 --port 8080             # Start on specific host/port
    orbit stop                                          # Stop the server
    orbit stop --force                                  # Force stop without graceful shutdown
    orbit stop --delete-logs                            # Stop and delete logs
    orbit restart                                       # Restart the server
    orbit status                                        # Check server status
    orbit status --watch                                # Continuously monitor status
    orbit status --watch --interval 10                  # Monitor with custom interval

    # API Key Management
    orbit key create --adapter city --name "City Assistant" --notes "For city queries"
    orbit key create --adapter city --name "City Assistant" --prompt-file prompts/city.txt --prompt-name "City Prompt"
    orbit key list                                      # List all API keys
    orbit key list --active-only                        # List only active keys
    orbit key test --key YOUR_API_KEY                   # Test an API key
    orbit key status --key YOUR_API_KEY                 # Get API key status
    orbit key rename --old-key OLD_KEY --new-key NEW_KEY
    orbit key deactivate --key YOUR_API_KEY             # Deactivate an API key
    orbit key delete --key YOUR_API_KEY                # Delete an API key (with confirmation)
    orbit key delete --key YOUR_API_KEY --force         # Delete without confirmation
    orbit key list-adapters                             # List available adapters

    # System Prompt Management
    orbit prompt create --name "Support Assistant" --file prompts/support.txt --version "1.0"
    orbit prompt list                                   # List all prompts
    orbit prompt list --name-filter "Support"          # Filter prompts by name
    orbit prompt get --id PROMPT_ID                     # Get a prompt
    orbit prompt get --id PROMPT_ID --save prompt.txt   # Get and save to file
    orbit prompt update --id PROMPT_ID --file updated.txt --version "1.1"
    orbit prompt delete --id PROMPT_ID                 # Delete a prompt (with confirmation)
    orbit prompt delete --id PROMPT_ID --force          # Delete without confirmation
    orbit prompt associate --key API_KEY --prompt-id PROMPT_ID

    # CLI Configuration
    orbit config show                                   # Show all CLI configuration
    orbit config show --key server.timeout              # Show specific key
    orbit config effective                              # Show effective config with sources
    orbit config set server.timeout 60                  # Set configuration value
    orbit config set output.format json                 # Change output format
    orbit config reset                                  # Reset to defaults (with confirmation)
    orbit config reset --force                          # Reset without confirmation

    # Admin Operations
    orbit admin reload-adapters                         # Reload all adapters
    orbit admin reload-adapters --adapter city          # Reload specific adapter
    orbit admin reload-templates                        # Reload templates for all intent adapters
    orbit admin reload-templates --adapter intent-sql-sqlite-hr  # Reload templates for specific adapter

    # Using different output formats
    orbit user list --output json                       # Output as JSON
    orbit key list --output json                        # Output as JSON
    orbit status --output json                          # Output as JSON

    # Using different server URLs
    orbit --server-url http://remote-server:3000 status
    orbit --server-url http://remote-server:3000 login

    # Verbose mode for debugging
    orbit -v start                                      # Start with verbose logging
    orbit -v login                                      # Login with verbose logging

For more information about a specific command, use:
    orbit <command> --help

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
