# ORBIT CLI

A command-line interface for managing the Open Inference Server, similar to AWS CLI or Azure CLI.

## Overview

- Server lifecycle (start, stop, restart, status)
- API key management
- System prompt management
- Integration between API keys and prompts

## Installation

1. Install dependencies:
   ```bash
   pip install psutil requests python-dotenv
   ```

2. Make the scripts executable:
   ```bash
   chmod +x orbit.py
   chmod +x orbit
   ```

3. (Optional) Create a symlink for system-wide access:
   ```bash
   sudo ln -s $(pwd)/orbit /usr/local/bin/orbit
   ```

## Configuration

Create a `.env` file for default configuration:
```bash
API_SERVER_URL=http://localhost:3000
API_ADMIN_TOKEN=your_admin_token_here
```

## Usage

### Server Management

Control the server lifecycle:

```bash
# Start the server
orbit start

# Start with custom configuration
orbit start --config custom_config.yaml

# Start with specific host/port
orbit start --host 0.0.0.0 --port 8080

# Start with auto-reload (development mode)
orbit start --reload

# Start and delete existing logs
orbit start --delete-logs

# Stop the server
orbit stop

# Stop and delete logs
orbit stop --delete-logs

# Restart the server
orbit restart

# Restart and delete logs
orbit restart --delete-logs

# Check server status
orbit status
```

### API Key Management

Manage API keys for client authentication:

```bash
# Create a new API key
orbit key create --collection documents --name "Customer Support"

# Create API key with notes
orbit key create --collection legal --name "Legal Team" --notes "For legal department use"

# List all API keys
orbit key list

# Test an API key
orbit key test --key api_abcd1234

# Check API key status
orbit key status --key api_abcd1234

# Deactivate an API key
orbit key deactivate --key api_abcd1234

# Delete an API key
orbit key delete --key api_abcd1234
```

### System Prompt Management

Manage system prompts (templates that guide LLM responses):

```bash
# Create a new prompt from file
orbit prompt create --name "Support Assistant" --file prompts/support.txt

# Create with version
orbit prompt create --name "Legal Assistant" --file prompts/legal.txt --version "2.0"

# List all prompts
orbit prompt list

# Get a specific prompt
orbit prompt get --id 612a4b3c78e9f25d3e1f42a7

# Update an existing prompt
orbit prompt update --id 612a4b3c78e9f25d3e1f42a7 --file prompts/updated.txt

# Update with new version
orbit prompt update --id 612a4b3c78e9f25d3e1f42a7 --file prompts/v2.txt --version "2.0"

# Delete a prompt
orbit prompt delete --id 612a4b3c78e9f25d3e1f42a7

# Associate prompt with API key
orbit prompt associate --key api_abcd1234 --prompt-id 612a4b3c78e9f25d3e1f42a7
```

### Integrated Operations

Create API keys with prompts in one command:

```bash
# Create API key with a new prompt
orbit key create --collection support_docs --name "Support Team" \
  --prompt-file prompts/support.txt --prompt-name "Support Assistant"

# Create API key with an existing prompt
orbit key create --collection legal_docs --name "Legal Team" \
  --prompt-id 612a4b3c78e9f25d3e1f42a7
```

## Command Structure

The ORBIT CLI follows a hierarchical command structure:

```
orbit <command> <subcommand> [options]
```

Main commands:
- **Server control**: `start`, `stop`, `restart`, `status`
- **API key management**: `key <subcommand>`
- **System prompt management**: `prompt <subcommand>`

## Examples

### Complete Workflow Example

1. Start the server:
   ```bash
   orbit start
   ```

2. Create a system prompt:
   ```bash
   orbit prompt create --name "Customer Support" --file support_prompt.txt
   ```

3. Create an API key with the prompt:
   ```bash
   orbit key create --collection support_docs --name "Support Team" \
     --prompt-name "Customer Support" --prompt-file support_prompt.txt
   ```

4. Test the API key:
   ```bash
   orbit key test --key api_generated_key_here
   ```

5. When config changes are needed:
   ```bash
   orbit restart --config new_config.yaml
   ```

### Development Workflow

For development with auto-reload:
```bash
# Start with auto-reload
orbit start --reload

# Start fresh with deleted logs
orbit start --delete-logs

# Make code changes - server auto-restarts

# When done, stop the server
orbit stop

# Stop and clean up logs
orbit stop --delete-logs
```

### Production Deployment

For production environments:
```bash
# Start with specific configuration
orbit start --config production.yaml

# Start fresh with deleted logs
orbit start --config production.yaml --delete-logs

# Monitor status
orbit status

# Graceful restart for updates
orbit restart --config production.yaml

# Restart and clean logs
orbit restart --config production.yaml --delete-logs
```

## Environment Variables

- `API_SERVER_URL`: Default server URL for API operations
- `API_ADMIN_TOKEN`: Admin authentication token (if required)
- `OIS_HOST`: Override host for server start
- `OIS_PORT`: Override port for server start

## File Structure

ORBIT creates/uses these files:
- `../server.pid`: Process ID file for server management
- `../logs/orbit.log`: Server output and logs
- `.env`: Optional configuration file

## Error Handling

ORBIT provides clear error messages and exit codes:
- Exit code 0: Success
- Exit code 1: Error occurred

Check logs for detailed error information:
```bash
tail -f ../logs/orbit.log
```

## Tips

1. Use tab completion (if configured) for faster command entry
2. Set up aliases for frequently used commands:
   ```bash
   alias os='orbit status'
   alias or='orbit restart'
   ```

3. Use the `--server-url` flag to manage remote servers:
   ```bash
   orbit --server-url https://api.example.com key list
   ```

## Security Notes

- Keep API admin tokens secure
- Use HTTPS for production deployments
- Regularly rotate API keys
- Monitor API key usage through logs

## Contributing

ORBIT is designed to be extensible. New commands can be added by:
1. Adding new subparser in the appropriate section
2. Implementing the handler in the `execute` method
3. Following the existing pattern for consistency