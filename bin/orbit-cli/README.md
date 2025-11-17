# ORBIT CLI

Interactive command-line interface for managing ORBIT server.

## Features

- **REPL Mode**: Interactive REPL with `orbit>` prompt
- **API-Only**: All interactions via server APIs (no local config file reading)
- **Modern UX**: Colored output, progress indicators, interactive prompts
- **Full Feature Set**: Authentication, user management, API keys, prompts, admin operations

## Installation

1. Install dependencies:
```bash
cd bin/orbit-cli
npm install
```

2. Build the project:
```bash
npm run build
```

3. Use the CLI:
```bash
# Interactive mode
node ../orbit.js

# Or direct command
node ../orbit.js login
```

## Usage

### Interactive Mode

Start the REPL:
```bash
orbit
```

You'll see the `orbit>` prompt where you can type commands.

### Direct Commands

Run commands directly without entering REPL:
```bash
orbit login
orbit key list
orbit status
```

## Commands

### Authentication
- `login [--username] [--password]` - Login to the server
- `logout` - Logout and clear token
- `register --username --password [--role]` - Register a new user (admin only)
- `me` - Show current user information
- `auth-status` - Check authentication status

### User Management
- `user list [--role] [--active-only]` - List users
- `user reset-password --user-id|--username [--password]` - Reset user password
- `user change-password` - Change your password
- `user activate --user-id` - Activate a user
- `user deactivate --user-id` - Deactivate a user
- `user delete --user-id [--force]` - Delete a user

### API Keys
- `key create --adapter --name [--notes] [--prompt-id|--prompt-file]` - Create API key
- `key list [--active-only]` - List API keys
- `key status --key` - Get API key status
- `key test --key` - Test an API key
- `key rename --old-key --new-key` - Rename an API key
- `key deactivate --key` - Deactivate an API key
- `key delete --key [--force]` - Delete an API key
- `key list-adapters` - List available adapters

### System Prompts
- `prompt create --name --file [--version]` - Create a system prompt
- `prompt list [--name-filter]` - List prompts
- `prompt get --id [--save]` - Get a prompt
- `prompt update --id --file [--version]` - Update a prompt
- `prompt delete --id [--force]` - Delete a prompt
- `prompt associate --key --prompt-id` - Associate prompt with API key

### Admin
- `admin reload-adapters [--adapter]` - Reload adapter configurations

### Server
- `status [--watch]` - Check server status

### Configuration
- `config show [--key]` - Show configuration
- `config set <key> <value>` - Set configuration value
- `config reset [--force]` - Reset configuration

## Configuration

Configuration is stored in `~/.orbit/config.json`:
```json
{
  "serverUrl": "http://localhost:3000",
  "authToken": "your-token-here"
}
```

## Development

Run in development mode:
```bash
NODE_ENV=development node ../orbit.js
```

Or use ts-node directly:
```bash
cd bin/orbit-cli
npm run dev
```

## Requirements

- Node.js 18.0.0 or higher
- ORBIT server running and accessible

