# Migrate Python CLI to Node.js

## Overview

Migrate `bin/orbit.py` to a Node.js TypeScript CLI with REPL-style interactive mode. The CLI will interact exclusively with Orbit server APIs (no local config file reading) and provide a modern, pleasant user experience.

## Architecture

### Project Structure

```
bin/
  orbit.js (main entry point)
  orbit-cli/
    src/
      index.ts (REPL entry)
      commands/ (command handlers)
      api/ (API client)
      config/ (config manager)
      utils/ (formatters, validators)
    package.json
    tsconfig.json
```

### Core Components

1. **API Client** (`api/client.ts`)

   - HTTP client for all server endpoints
   - Authentication token management
   - Error handling and retry logic
   - Endpoints: `/auth/*`, `/admin/*`, `/health/*`

2. **Configuration Manager** (`config/manager.ts`)

   - Store/load from `~/.orbit/config.json`
   - Store: `serverUrl`, `authToken`
   - No server config reading (API-only)

3. **REPL Interface** (`index.ts`)

   - Interactive REPL with `orbit>` prompt
   - Command history (using readline)
   - Auto-completion for commands
   - Exit with `exit`, `quit`, or Ctrl+D

4. **Command Handlers** (`commands/*.ts`)

   - Authentication: login, logout, register, me, auth-status
   - User management: list, reset-password, change-password, activate, deactivate, delete
   - API keys: create, list, status, test, rename, deactivate, delete, list-adapters
   - Prompts: create, list, get, update, delete, associate
   - Admin: reload-adapters
   - Server: status (via `/health` API)
   - Config: show, effective, set, reset

5. **Output Formatters** (`utils/formatters.ts`)

   - Table formatting (using `cli-table3` or `table`)
   - JSON output option
   - Colored output (Chalk)
   - Progress indicators (Ora)

## Implementation Steps

### Phase 1: Project Setup

1. Create `bin/orbit-cli/` directory
2. Initialize npm project with `package.json`
3. Set up TypeScript configuration
4. Install dependencies:

   - `commander` - CLI framework
   - `inquirer` - Interactive prompts
   - `chalk` - Colored output
   - `ora` - Progress spinners
   - `axios` or `node-fetch` - HTTP client
   - `table` or `cli-table3` - Table formatting
   - `readline` - REPL interface (built-in)
   - `@types/node` - TypeScript types

### Phase 2: Core Infrastructure

1. **API Client** (`api/client.ts`)

   - Base HTTP client with axios/fetch
   - Token management (load from config, inject in headers)
   - Error handling (401 → auth error, 403 → permission error, etc.)
   - Retry logic for network errors
   - Methods for all endpoints from `admin_routes.py`, `auth_routes.py`, `health_routes.py`

2. **Configuration Manager** (`config/manager.ts`)

   - Read/write `~/.orbit/config.json`
   - Structure: `{ serverUrl: string, authToken?: string }`
   - Default server URL: `http://localhost:3000`
   - Secure token storage (file permissions 0o600)

3. **REPL Interface** (`index.ts`)

   - Readline interface with `orbit>` prompt
   - Command parsing (split by spaces, handle quotes)
   - Command routing to handlers
   - History support (up/down arrows)
   - Auto-completion for commands and subcommands
   - Help system (`help`, `help <command>`)

### Phase 3: Command Implementation

1. **Authentication Commands**

   - `login [--username] [--password]` - Interactive if missing
   - `logout` - Clear token
   - `register --username --password [--role]` - Admin only
   - `me` - Show current user
   - `auth-status` - Check auth state

2. **User Management Commands**

   - `user list [--role] [--active-only]`
   - `user reset-password --user-id|--username [--password]`
   - `user change-password` - Interactive
   - `user activate --user-id`
   - `user deactivate --user-id`
   - `user delete --user-id [--force]`

3. **API Key Commands**

   - `key create --adapter --name [--notes] [--prompt-id|--prompt-file]`
   - `key list [--active-only]`
   - `key status --key`
   - `key test --key`
   - `key rename --old-key --new-key`
   - `key deactivate --key`
   - `key delete --key [--force]`
   - `key list-adapters` - Read from server config API if available, or show message

4. **Prompt Commands**

   - `prompt create --name --file [--version]`
   - `prompt list [--name-filter]`
   - `prompt get --id [--save]`
   - `prompt update --id --file [--version]`
   - `prompt delete --id [--force]`
   - `prompt associate --key --prompt-id`

5. **Admin Commands**

   - `admin reload-adapters [--adapter]`

6. **Server Commands**

   - `status` - Call `/health` and `/health/system` APIs
   - `status --watch` - Poll and update display

7. **Config Commands**

   - `config show [--key]` - Show CLI config only
   - `config set <key> <value>` - Set CLI config
   - `config reset [--force]` - Reset to defaults

### Phase 4: Interactive Features

1. **REPL Enhancements**

   - Command history persistence
   - Tab completion for commands
   - Auto-complete for IDs (user-id, prompt-id, etc.) - fetch from server
   - Multi-line command support
   - Command aliases (e.g., `ls` for `list`)

2. **User Experience**

   - Progress spinners for long operations
   - Colored output (success=green, error=red, warning=yellow)
   - Interactive prompts for missing required args
   - Confirmation prompts for destructive operations
   - Table formatting for list commands
   - JSON output option (`--output json`)

3. **Error Handling**

   - Clear error messages
   - Suggestions for common errors (e.g., "Not authenticated. Run 'login' first")
   - Network error handling with retry
   - Graceful degradation (show partial data if some requests fail)

### Phase 5: Testing & Polish

1. Test all commands against running server
2. Error handling edge cases
3. Documentation (help text, README)
4. Installation script/setup
5. Remove old Python CLI (or keep as backup)

## Key Design Decisions

1. **No Server Control**: Only `status` command via `/health` API. Start/stop/restart removed (use systemd/docker).

2. **API-Only**: No reading of `config/adapters.yaml` or server config files. All data from APIs.

3. **REPL Mode**: Default interactive mode with `orbit>` prompt. Can also run commands directly: `orbit login`.

4. **Configuration**: Store only `serverUrl` and `authToken` in `~/.orbit/config.json`.

5. **TypeScript**: Use TypeScript for type safety and better developer experience.

6. **Error Messages**: Friendly, actionable error messages with suggestions.

## Files to Create/Modify

### New Files

- `bin/orbit-cli/package.json`
- `bin/orbit-cli/tsconfig.json`
- `bin/orbit-cli/src/index.ts` (REPL entry)
- `bin/orbit-cli/src/api/client.ts` (API client)
- `bin/orbit-cli/src/config/manager.ts` (Config manager)
- `bin/orbit-cli/src/commands/auth.ts`
- `bin/orbit-cli/src/commands/user.ts`
- `bin/orbit-cli/src/commands/key.ts`
- `bin/orbit-cli/src/commands/prompt.ts`
- `bin/orbit-cli/src/commands/admin.ts`
- `bin/orbit-cli/src/commands/server.ts`
- `bin/orbit-cli/src/commands/config.ts`
- `bin/orbit-cli/src/utils/formatters.ts`
- `bin/orbit-cli/src/utils/validators.ts`
- `bin/orbit-cli/README.md`

### Modified Files

- `bin/orbit.js` - Update to point to new Node.js CLI (or create new entry point)

## Dependencies

```json
{
  "dependencies": {
    "commander": "^11.0.0",
    "inquirer": "^9.2.0",
    "chalk": "^5.3.0",
    "ora": "^7.0.0",
    "axios": "^1.6.0",
    "table": "^6.8.1",
    "readline": "built-in"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.3.0",
    "ts-node": "^10.9.0"
  }
}
```

## Migration Notes

- Keep Python CLI as `orbit.py` (backup) or remove after migration
- Update `bin/orbit.sh` to use Node.js version
- Ensure backward compatibility for common commands (same command structure)
- Add migration guide for users