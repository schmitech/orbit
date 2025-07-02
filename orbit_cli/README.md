# ORBIT CLI

**Enterprise-grade Open Inference Server management tool**

A command-line interface for managing the ORBIT server, providing server control, API key management, user administration, and system configuration capabilities.

## Features

- 🚀 **Server Management**: Start, stop, restart, and monitor ORBIT server instances
- 🔐 **Authentication**: Secure login/logout with token management
- 👥 **User Administration**: Complete user lifecycle management (admin only)
- 🔑 **API Key Management**: Create, manage, and monitor API keys with collection binding
- 📝 **System Prompts**: Manage and associate AI system prompts with API keys
- ⚙️ **Configuration**: Flexible configuration management with multiple sources
- 🎨 **Rich Output**: Beautiful table and JSON output formats with color support
- 🔒 **Secure Storage**: Keychain integration for secure credential storage

## Installation

```bash
# Install from the project root
pip install -e .

# Or run directly from source
python -m orbit_cli.main
```

## Quick Start

```bash
# Start the server
orbit start

# Login to the server
orbit login

# List API keys
orbit key list

# Show current configuration
orbit config show
```

## Architecture

The ORBIT CLI is built with a modular architecture:

```
orbit_cli/
├── cli.py              # Main CLI class with command orchestration
├── commands/           # Command implementations
│   ├── server.py       # Server management commands
│   ├── auth.py         # Authentication commands
│   ├── api_keys.py     # API key management
│   ├── users.py        # User management
│   ├── prompts.py      # System prompt management
│   └── config.py       # Configuration commands
├── api/                # API client components
├── server/             # Server management utilities
├── config/             # Configuration management
├── core/               # Core utilities and exceptions
└── utils/              # Helper utilities
```

## Global Options

All commands support these global options:

| Option | Description |
|--------|-------------|
| `--version` | Show version information |
| `--server-url URL` | Override server URL (default: from config or localhost:3000) |
| `--config PATH` | Path to configuration file |
| `-v, --verbose` | Enable verbose output with detailed logging |
| `--output {table,json}` | Output format (default: table) |
| `--no-color` | Disable colored output |
| `--log-file PATH` | Path to log file for debugging |

## Commands

### Server Management

Control the ORBIT server lifecycle:

```bash
# Start server with default settings
orbit start

# Start with custom configuration
orbit start --config /path/to/config.yaml --host 0.0.0.0 --port 8080

# Start in development mode with auto-reload
orbit start --reload

# Stop server gracefully
orbit stop

# Force stop with immediate termination
orbit stop --force

# Restart server with new configuration
orbit restart --config /path/to/new-config.yaml

# Check server status
orbit status

# Monitor server status continuously
orbit status --watch --interval 10

# View server logs
orbit logs --follow
```

### Authentication

Secure authentication and session management:

```bash
# Interactive login (prompts for credentials)
orbit login

# Login with credentials
orbit login --username admin --password secret123

# Check current user information
orbit me

# Check authentication status
orbit auth-status

# Logout and clear stored credentials
orbit logout

# Register new user (admin only)
orbit register --username newuser --role user
```

### User Management (Admin Only)

Comprehensive user administration:

```bash
# List all users
orbit user list

# Filter users by role
orbit user list --role admin

# Show only active users
orbit user list --active-only

# Reset user password by username
orbit user reset-password --username admin --password newpass

# Reset user password by ID
orbit user reset-password --user-id 507f1f77bcf86cd799439011

# Change your own password (interactive)
orbit user change-password

# Deactivate a user account
orbit user deactivate --user-id 507f1f77bcf86cd799439011

# Activate a previously deactivated user
orbit user activate --user-id 507f1f77bcf86cd799439011

# Delete a user permanently
orbit user delete --user-id 507f1f77bcf86cd799439011 --force
```

### API Key Management

Create and manage API keys with collection bindings:

```bash
# Create simple API key
orbit key create --collection docs --name "Customer Support"

# Create API key with system prompt
orbit key create --collection legal --name "Legal Team" \
  --prompt-file legal_prompt.txt --prompt-name "Legal Assistant"

# List all API keys
orbit key list

# Filter by collection
orbit key list --collection docs

# Show only active keys
orbit key list --active-only

# Test API key validity
orbit key test --key api_abcd1234

# Get detailed key status
orbit key status --key api_abcd1234

# Deactivate API key temporarily
orbit key deactivate --key api_abcd1234

# Delete API key permanently
orbit key delete --key api_abcd1234 --force
```

### System Prompt Management

Manage AI system prompts and associate them with API keys:

```bash
# Create system prompt from file
orbit prompt create --name "Support Assistant" --file support_prompt.txt

# List all prompts
orbit prompt list

# Filter prompts by name
orbit prompt list --name-filter "Support"

# Get specific prompt details
orbit prompt get --id 612a4b3c... 

# Save prompt to file
orbit prompt get --id 612a4b3c... --save downloaded_prompt.txt

# Update existing prompt
orbit prompt update --id 612a4b3c... --file updated_prompt.txt

# Delete prompt
orbit prompt delete --id 612a4b3c... --force

# Associate prompt with API key
orbit prompt associate --key api_123 --prompt-id 612a4b3c...
```

### Configuration Management

Manage CLI configuration with multiple source support:

```bash
# Show current configuration
orbit config show

# Show specific configuration key
orbit config show --key server.default_url

# Show effective configuration with sources
orbit config effective

# Check where specific setting comes from
orbit config effective --key auth.credential_storage

# Show only configuration sources
orbit config effective --sources-only

# Set configuration value
orbit config set server.timeout 60

# Reset configuration to defaults
orbit config reset --force

# Export configuration to file
orbit config export config_backup.json

# Import configuration from file
orbit config import config_backup.json --merge
```

## Configuration

### Configuration Sources

ORBIT CLI uses a smart configuration system with the following precedence:

1. **Command-line arguments** (highest priority)
2. **CLI configuration** (`~/.orbit/config.json`)
3. **Server configuration** (`config.yaml`) - for server-related settings
4. **Environment variables**
5. **Default values** (lowest priority)

### Configuration Files

#### CLI Configuration (`~/.orbit/config.json`)

```json
{
  "server": {
    "default_url": "http://localhost:3000",
    "timeout": 30,
    "retry_attempts": 3
  },
  "auth": {
    "credential_storage": "keyring",
    "use_keyring": true,
    "session_duration_hours": 12
  },
  "output": {
    "format": "table",
    "color": true,
    "verbose": false
  }
}
```

### Authentication Storage

ORBIT CLI supports multiple credential storage methods:

- **Keychain/Keyring** (default): Secure system credential storage
- **File storage**: Encrypted storage in `~/.orbit/.env`
- **Memory only**: No persistent storage (use `--no-save`)

Configure storage method:
```bash
orbit config set auth.credential_storage keyring
orbit config set auth.credential_storage file
```

## Output Formats

### Table Format (Default)

```bash
orbit key list
```
```
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┓
┃ API Key              ┃ Client         ┃ Collection ┃ Active ┃ Created    ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━┩
│ api_abcd1234...      │ Customer Sup…  │ docs       │ ✓      │ 2024-01-15 │
│ api_efgh5678...      │ Legal Team     │ legal      │ ✓      │ 2024-01-14 │
└──────────────────────┴────────────────┴────────────┴────────┴────────────┘
```

### JSON Format

```bash
orbit key list --output json
```
```json
[
  {
    "api_key": "api_abcd1234efgh5678",
    "client_name": "Customer Support",
    "collection": "docs",
    "active": true,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

## Examples

### Complete Workflow

```bash
# 1. Start the server
orbit start --config production.yaml

# 2. Login as admin
orbit login --username admin

# 3. Create a user
orbit register --username developer --role user

# 4. Create API key with prompt
orbit key create --collection support --name "Support Bot" \
  --prompt-file support_prompt.txt --prompt-name "Support Assistant"

# 5. Test the API key
orbit key test --key api_generated_key_here

# 6. Monitor server status
orbit status --watch
```

### Automation Scripts

```bash
#!/bin/bash
# Automated deployment script

# Start server and wait for health
orbit start --wait-healthy --timeout 60

# Create API keys for different services
orbit key create --collection docs --name "Documentation Bot"
orbit key create --collection support --name "Customer Support"

# List all keys for verification
orbit key list --output json > api_keys.json

echo "Deployment complete!"
```

## Development

### Project Structure

```
orbit_cli/
├── __init__.py         # Package initialization
├── __version__.py      # Version information
├── main.py            # Entry point
├── cli.py             # Main CLI orchestrator
├── commands/          # Command implementations
├── api/               # API client modules
├── server/            # Server management
├── config/            # Configuration management
├── core/              # Core utilities
├── output/            # Output formatting
└── utils/             # Helper utilities
```

### Adding New Commands

1. Create command class extending `BaseCommand`:

```python
from orbit_cli.commands.base import BaseCommand

class MyCommand(BaseCommand):
    name = "my-command"
    help = "My custom command"
    
    def add_arguments(self, parser):
        parser.add_argument('--option', help='My option')
    
    def execute(self, args):
        self.formatter.success("Command executed!")
        return 0
```

2. Register in `commands/__init__.py` or use the decorator:

```python
from orbit_cli.commands import register_command

@register_command
class MyCommand(BaseCommand):
    # ... implementation
```

### Testing

```bash
# Run tests
python -m pytest tests/

# Run specific test module
python -m pytest tests/test_commands.py

# Run with coverage
python -m pytest --cov=orbit_cli tests/
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   ```bash
   # Check auth status
   orbit auth-status
   
   # Clear and re-login
   orbit logout
   orbit login
   ```

2. **Server Connection Issues**
   ```bash
   # Check server status
   orbit status
   
   # Verify configuration
   orbit config effective --key server.default_url
   ```

3. **Configuration Problems**
   ```bash
   # Reset to defaults
   orbit config reset --force
   
   # Check effective configuration
   orbit config effective
   ```

### Debug Mode

Enable verbose logging for detailed debugging:

```bash
orbit --verbose --log-file debug.log command
```

## Security

- **Credentials**: Stored securely using system keychain by default
- **API Keys**: Never logged or displayed in full
- **Connections**: All API calls use HTTPS in production
- **Permissions**: File-based configurations use restrictive permissions (600)

## License

See the main project LICENSE file for licensing information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## Support

For issues and questions:
- GitHub Issues: https://github.com/schmitech/orbit/issues
- Documentation: Check `orbit <command> --help` for detailed help

---

**ORBIT CLI** - Enterprise-grade server management made simple.
