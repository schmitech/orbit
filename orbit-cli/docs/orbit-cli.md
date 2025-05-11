# ORBIT Manager CLI

An interactive command-line interface for the ORBIT Manager Utility, inspired by AWS CLI and Azure CLI.

## Features

- **Interactive Command Prompts**: User-friendly prompts to guide you through command execution
- **Command Completion**: Tab completion for commands and arguments
- **Command History**: Remembers previously executed commands
- **Colorful Output**: Rich, colorful output format for better readability
- **Subcommands Structure**: Organized command structure similar to AWS CLI/Azure CLI

## Installation

### Quick Install

1. Download the installation files:
   - `orbit_cli.py`
   - `install_orbit_cli.py` 
   - `orbit.py` (the original ORBIT Manager Utility script)

2. Run the installer:
   ```bash
   python install_orbit_cli.py
   ```

3. Add the ORBIT CLI directory to your PATH as instructed by the installer.

### Manual Installation

1. Ensure you have the required dependencies:
   ```bash
   pip install pyyaml sqlalchemy prompt_toolkit click rich
   ```

2. Copy `orbit_cli.py` and `orbit.py` to a directory of your choice.

3. Create an alias or add the directory to your PATH.

## Usage

### Getting Started

To start the interactive CLI:

```bash
orbit
```

You'll see a welcome screen with the ORBIT CLI banner and prompt:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃           ORBIT Manager Interactive CLI      ┃
┃           Version: 1.0.0                      ┃
┃                                              ┃
┃  Type 'help' or '?' for available commands   ┃
┃  Type 'exit' or 'quit' to exit               ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

orbit>
```

### Basic Commands

- `help` - Show available commands
- `exit` or `quit` - Exit the CLI

### API Key Management

- `api-key create` - Interactive prompt to create a new API key
- `api-key list` - List all API keys
- `api-key deactivate` - Deactivate an API key
- `api-key delete` - Delete an API key
- `api-key test` - Test an API key
- `api-key status` - Get the status of an API key

### System Prompt Management

- `prompt create` - Create a new system prompt
- `prompt list` - List all system prompts
- `prompt get` - Get a system prompt by ID
- `prompt update` - Update an existing system prompt
- `prompt delete` - Delete a system prompt
- `prompt associate` - Associate a system prompt with an API key

### Configuration Management

- `config edit` - Open the configuration file in your default editor
- `config show` - Show the current configuration

### Test Commands

- `test run` - Run the test suite
- `test report` - Open the latest test report in a web browser

## Configuration

The ORBIT CLI uses a YAML configuration file located at `~/.orbit/config.yaml`. The first time you run the CLI, a default configuration will be created.

### Default Configuration

```yaml
application:
  name: "API Key Manager"
  log_level: "info"
  log_file: "~/.orbit/logs/api_manager.log"

database:
  engine: "sqlite"
  connection:
    sqlite:
      database: "~/.orbit/data/api_keys.db"
    postgres:
      host: "localhost"
      port: 5432
      database: "api_keys"
      user: "postgres"
      password: "password"
      sslmode: "prefer"
    # Additional configurations for mysql, oracle, and mssql

  pool:
    min_size: 1
    max_size: 10
    timeout: 30
  
  retry:
    max_attempts: 3
    backoff_factor: 2

api_keys:
  prefix: "orbit_"
  length: 16
  characters: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

prompts:
  default_version: "1.0"
  templates_dir: "templates"
```

You can edit this configuration using the `config edit` command.

## Examples

### Creating a New API Key

```
orbit> api-key create
Collection name: customer_data
Client name: Customer Support
Notes (optional): For support portal
Associate with a system prompt? [y/N]: y
...
```

### Listing All API Keys

```
orbit> api-key list
╭─────────────────────────────────────────╮
│ Results                                  │
├──────┬─────────────┬──────────┬─────────┤
│ id   │ api_key     │ collection_name    │
├──────┼─────────────┼──────────┼─────────┤
│ 1    │ api_abc123  │ customer_data      │
│ 2    │ api_def456  │ analytics          │
╰──────┴─────────────┴──────────┴─────────╯
```

### Creating a System Prompt

```
orbit> prompt create
Prompt name: Customer Service
Version (1.0): 
Enter the prompt text (opens in editor):
...
```

## Advanced Usage

### Direct Command Execution

You can also execute commands directly without entering the interactive mode:

```bash
orbit api-key list
orbit prompt create
```

### Custom Configuration File

You can specify a custom configuration file:

```bash
orbit --config /path/to/config.yaml
```

### Test Mode

You can run the CLI in test mode:

```bash
orbit --test-mode
```

This will display a special test mode banner and prompt to remind you that you're working in a test environment.

### Database Selection

The ORBIT Manager supports multiple database engines:

- SQLite (default)
- PostgreSQL
- MySQL
- Oracle
- Microsoft SQL Server

To use a different database engine, edit the configuration file with `config edit` and change the `database.engine` value.

## Troubleshooting

### Command Not Found

If you get a `command not found` error, make sure you've added the ORBIT CLI directory to your PATH as instructed during installation.

### Missing Dependencies

If you see errors about missing packages, install them manually:

```bash
pip install prompt_toolkit click rich
```

### Configuration Issues

If you encounter configuration issues, you can reset to the default configuration:

```bash
rm ~/.orbit/config.yaml
orbit
```

A new default configuration will be created.

## License

This project is licensed under the MIT License.