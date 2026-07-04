# Authentication Technical Details

## Overview

ORBIT's authentication leverages PBKDF2-SHA256 (600k iterations) for password security and cryptographically secure bearer tokens for session management. The modular architecture integrates MongoDB for persistent session storage, implements role-based access control (RBAC), and provides both programmatic and CLI interfaces for comprehensive user lifecycle management.

In addition to this built-in username/password system, ORBIT can **validate access tokens issued by external identity providers** — Microsoft Entra ID (Azure AD) and Auth0 — presented as bearer tokens. This lets browser clients such as `orbitchat` sign users in via OAuth 2.0 / OIDC and call the ORBIT API with the resulting JWT, while the built-in admin/CLI login continues to work unchanged. See [External Identity Providers](#external-identity-providers-oidc).

## Architecture

### Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│   CLI Client    │◄──►│  API Routes     │◄──►│  Auth Service   │
│   (orbit.py)    │    │ (auth_routes.py)│    │(auth_service.py)│
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         v                       v                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│ Token Storage   │    │  FastAPI        │    │   MongoDB       │
│ (~/.orbit/.env) │    │  Middleware     │    │  Collections    │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow

1. **Authentication Request**: Client sends credentials to API
2. **Credential Verification**: Service validates against MongoDB
3. **Token Generation**: Cryptographically secure token created
4. **Session Storage**: Token and user info stored in MongoDB
5. **Token Response**: Bearer token returned to client
6. **Token Persistence**: CLI stores token in secure storage (keyring/file) and loads into session variable
7. **Request Authorization**: Subsequent requests include bearer token from session variable
8. **Token Validation**: Service validates token against active sessions

## Database Schema

### Users Collection

```javascript
{
  "_id": ObjectId("..."),
  "username": "admin",
  "password": "base64_encoded_pbkdf2_hash",  // salt + hash
  "role": "admin|user",
  "active": true,
  "created_at": ISODate("2025-01-01T00:00:00Z"),
  "last_login": ISODate("2025-01-01T12:00:00Z")
}
```

### Sessions Collection

```javascript
{
  "_id": ObjectId("..."),
  "token": "cryptographically_secure_hex_string",
  "user_id": ObjectId("..."),  // Reference to users collection
  "username": "admin",
  "expires": ISODate("2025-01-01T24:00:00Z"),  // TTL index
  "created_at": ISODate("2025-01-01T12:00:00Z")
}
```

### Indexes

- **users.username**: Unique index for fast user lookup
- **sessions.token**: Unique index for token validation
- **sessions.expires**: TTL index for automatic session cleanup

## Security Features

### Password Security

- **Algorithm**: PBKDF2-SHA256 (Password-Based Key Derivation Function 2 with SHA-256)
- **Iterations**: 600,000 (configurable via `pbkdf2_iterations` setting)
- **Salt Length**: 16 bytes (128 bits) of cryptographically secure random data
- **Key Length**: 32 bytes (256 bits)
- **Salt Generation**: Using Python's `secrets.token_bytes(16)` for cryptographically secure randomness
- **Storage Format**: Base64-encoded concatenation of salt + hash
- **Constant-time comparison**: Using `hmac.compare_digest()` to prevent timing attacks

```python
# Actual password hashing implementation
salt = secrets.token_bytes(16)  # 128 bits of entropy
dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
encoded_password = base64.b64encode(salt + dk).decode('utf-8')
```

### Token Security

- **Token Generation**: Using `secrets.token_hex(32)` 
- **Token Length**: 64 hexadecimal characters (256 bits of entropy)
- **Token Type**: Opaque bearer tokens (not JWT)
- **Entropy Source**: Python's `secrets` module (cryptographically secure)
- **Session Storage**: Server-side in MongoDB with indexed lookups
- **No Token Refresh**: New login required after expiration

### Security Standards Compliance

- **NIST SP 800-63B Compliant**: Meets NIST guidelines for authentication
- **OWASP Standards**: Follows OWASP Authentication Cheat Sheet recommendations
  - 600,000 iterations exceeds OWASP 2023 minimum (600,000 for PBKDF2-SHA256)
  - Secure random generation for all tokens and salts
  - No password logging even in verbose mode
- **FIPS 140-2 Compatible**: Uses approved cryptographic algorithms

## Cryptographic Implementation Details

### Password Hashing Process

1. **Input Validation**: Password encoded to UTF-8
2. **Salt Generation**: 16 bytes from `secrets.token_bytes()`
3. **Key Derivation**: PBKDF2-HMAC-SHA256 with 600,000 iterations
4. **Storage**: Base64(salt || hash) stored in database

### Token Generation Process

1. **Entropy Collection**: 32 bytes from system CSPRNG
2. **Encoding**: Hexadecimal encoding for URL-safe tokens
3. **Uniqueness**: Verified against existing sessions
4. **Storage**: Indexed in MongoDB for O(1) lookups

### Security Considerations

- **No Client-Side Hashing**: All hashing done server-side
- **No Password Hints**: No password recovery without admin intervention
- **No Security Questions**: Only password-based authentication
- **No Remember Me**: Each session requires full authentication

### Additional Security Measures

- **MongoDB Connection Security**: Supports TLS/SSL encrypted connections
- **Exception Handling**: Specific handling for MongoDB errors to prevent info leakage
- **Token Isolation**: Each token is unique and cannot be derived from user info
- **No Password History**: Previous passwords are not stored
- **Secure Defaults**: Default admin password must be changed on first use

### Session Management

- **Bearer token authentication**: Standard HTTP authorization
- **Stateful sessions**: Server-side session storage in MongoDB
- **Session isolation**: Each login creates a new session
- **Forced logout**: Password changes invalidate all sessions
- **Graceful expiration**: Expired tokens automatically cleaned up

## API Endpoints

### Authentication Endpoints

#### POST /auth/login
Authenticate user and create session.

**Request:**
```json
{
  "username": "admin",
  "password": "password123"
}
```

**Response:**
```json
{
  "token": "abc123...",
  "user": {
    "id": "507f1f77bcf86cd799439011",
    "username": "admin", 
    "role": "admin",
    "active": true
  }
}
```

#### POST /auth/logout
Invalidate current session.

**Headers:**
```
Authorization: Bearer abc123...
```

**Response:**
```json
{
  "message": "Logout successful"
}
```

#### GET /auth/me
Get current user information.

**Headers:**
```
Authorization: Bearer abc123...
```

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "username": "admin",
  "role": "admin", 
  "active": true
}
```

### User Management Endpoints

#### POST /auth/register
Create new user (admin only).

**Headers:**
```
Authorization: Bearer abc123...
```

**Request:**
```json
{
  "username": "newuser",
  "password": "password123",
  "role": "user"
}
```

#### GET /auth/users
List all users (admin only).

**Headers:**
```
Authorization: Bearer abc123...
```

**Response:**
```json
[
  {
    "id": "507f1f77bcf86cd799439011",
    "username": "admin",
    "role": "admin",
    "active": true,
    "created_at": "2025-01-01T00:00:00Z",
    "last_login": "2025-01-01T12:00:00Z"
  }
]
```

#### DELETE /auth/users/{user_id}
Delete user (admin only).

**Headers:**
```
Authorization: Bearer abc123...
```

### Password Management Endpoints

#### POST /auth/change-password
Change current user's password.

**Headers:**
```
Authorization: Bearer abc123...
```

**Request:**
```json
{
  "current_password": "oldpassword",
  "new_password": "newpassword123"
}
```

#### POST /auth/reset-password
Reset user password (admin only).

**Headers:**
```
Authorization: Bearer abc123...
```

**Request:**
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "new_password": "newpassword123" 
}
```

## Credential Storage

### Overview

ORBIT CLI stores authentication credentials using configurable storage methods with a simplified state management approach:

- **Keyring (Default)**: Uses system's native credential management
  - **macOS**: macOS Keychain Access
  - **Linux**: Secret Service API (GNOME Keyring, KWallet, etc.)
- **File Storage**: Plain text file in `~/.orbit/.env` (less secure but visible)
- **Fallback**: Base64 encoded file storage when keyring fails

### Authentication State Management

The CLI uses a simplified authentication state management approach:

1. **Secure Storage**: Single source of truth for persistence (keyring or file)
2. **Session Token**: `self.admin_token` instance variable for current CLI session
3. **No Environment Variables**: Tokens are not stored in `os.environ`

**Authentication Flow:**
- **Initialization**: Load token from secure storage → `self.admin_token`
- **Login**: Server → `self.admin_token` + save to secure storage
- **Logout**: Clear `self.admin_token` + clear secure storage
- **API Calls**: Use `self.admin_token` for authorization

### Storage Methods

#### Keyring Storage (Recommended)
- **Security**: High - uses system's encrypted credential storage
- **Visibility**: Hidden - tokens not visible in plain text
- **Configuration**: `auth.credential_storage: keyring` (default)
- **Storage**: System keychain with service "orbit-cli" and account "auth-token"

#### File Storage (User Choice)
- **Security**: Medium - plain text file with restricted permissions (600)
- **Visibility**: High - tokens visible in `~/.orbit/.env`
- **Configuration**: `auth.credential_storage: file`
- **Use Case**: Development, debugging, or when keyring is not available
- **Format**: Direct file reading (no environment variable loading)

### Storage Locations

#### macOS Keychain
```
~/Library/Keychains/login.keychain-db
```

#### Linux Secret Service
```
~/.local/share/keyrings/ (GNOME Keyring)
~/.kde/share/apps/kwallet/ (KDE Wallet)
```

#### Fallback File Storage
```
~/.orbit/.env (base64 encoded, chmod 600)
```

### Managing Stored Credentials

#### Retrieve Bearer Token

After logging in with `orbit login`, the bearer token is stored in the system keychain (or file fallback). To retrieve it for use with admin API endpoints, scripts, or tools like `test_template_query.py`:

##### macOS

Tokens are stored in macOS Keychain via the `security` command:

```bash
# Print the raw bearer token value
security find-generic-password -s "orbit-cli" -a "auth-token" -w
```

Inline usage:
```bash
TOKEN=$(security find-generic-password -s "orbit-cli" -a "auth-token" -w)
```

##### Ubuntu / Debian Linux

Tokens are stored via GNOME Keyring (Secret Service API). Requires `libsecret-tools`:

```bash
# Install if needed
sudo apt-get install libsecret-tools

# Retrieve the token
secret-tool lookup service "orbit-cli" account "auth-token"
```

Inline usage:
```bash
TOKEN=$(secret-tool lookup service "orbit-cli" account "auth-token")
```

> **Note:** On headless servers without a desktop session, GNOME Keyring may not be running. In this case ORBIT falls back to file storage (see below).

##### KDE Linux

Tokens are stored in KDE Wallet:

```bash
kwallet-query kdewallet -f "orbit-cli" -r "auth-token"
```

##### Amazon Linux / AWS EC2 / Headless Servers

Headless environments typically don't have a keyring daemon. ORBIT automatically falls back to file-based storage at `~/.orbit/.env`. Retrieve the token:

```bash
# If stored in plain text (auth.credential_storage: file)
grep 'API_ADMIN_TOKEN=' ~/.orbit/.env | cut -d'=' -f2

# If stored as base64 fallback (default when keyring is unavailable)
grep 'API_ADMIN_TOKEN_B64=' ~/.orbit/.env | cut -d'=' -f2 | base64 --decode
```

Inline usage:
```bash
# Plain text storage
TOKEN=$(grep 'API_ADMIN_TOKEN=' ~/.orbit/.env | cut -d'=' -f2)

# Base64 fallback storage
TOKEN=$(grep 'API_ADMIN_TOKEN_B64=' ~/.orbit/.env | cut -d'=' -f2 | base64 --decode)
```

> **Tip:** To force file storage instead of keyring on any platform, set `auth.credential_storage: file` in your config or run `orbit config set auth.credential_storage file`.

##### Windows

Tokens are stored in Windows Credential Manager via the `keyring` Python library:

```powershell
# Using Python directly
python -c "import keyring; print(keyring.get_password('orbit-cli', 'auth-token'))"
```

Or via PowerShell with the `CredentialManager` module:
```powershell
# Install module if needed
Install-Module -Name CredentialManager

# Retrieve the token
(Get-StoredCredential -Target "orbit-cli:auth-token").Password
```

If keyring is not installed, check the fallback file:
```powershell
Get-Content "$env:USERPROFILE\.orbit\.env" | Select-String "API_ADMIN_TOKEN"
```

##### Using the Token

Once retrieved, the token works the same on all platforms:

```bash
# With the template diagnostics CLI tool
python server/tools/test_template_query.py \
  --query "salary stats" \
  --adapter intent-sql-sqlite-hr \
  --api-key "$TOKEN"

# With curl
curl -H "Authorization: Bearer $TOKEN" http://localhost:3000/admin/adapters/info
```

##### Cross-Platform Helper Script

A convenience script at `utils/scripts/get-auth-token.sh` auto-detects the platform and credential storage method:

```bash
# Print the token (with platform detection info on stderr)
./utils/scripts/get-auth-token.sh

# Quiet mode - token only, no status messages
./utils/scripts/get-auth-token.sh --quiet

# Export as shell variable
eval "$(./utils/scripts/get-auth-token.sh --export)"
echo $ORBIT_TOKEN

# Use directly with tools
python server/tools/test_template_query.py \
  --query "salary stats" --adapter intent-sql-sqlite-hr \
  --api-key "$(./utils/scripts/get-auth-token.sh --quiet)"
```

The script tries these methods in order based on detected platform:
- **macOS**: Keychain → Python keyring → file fallback
- **Linux**: GNOME Keyring → KDE Wallet → Python keyring → file fallback
- **AWS/cloud/headless**: Python keyring → file fallback
- **Windows (Git Bash)**: Python keyring → file fallback

##### Verifying Storage Method

To check which storage method is active:
```bash
orbit config show --key auth.credential_storage
```

#### View Stored Credentials

**macOS:**
```bash
# View auth token entry (full metadata)
security find-generic-password -s "orbit-cli" -a "auth-token"

# View server URL entry
security find-generic-password -s "orbit-cli" -a "server-url"

# List all orbit-cli entries
security find-generic-password -s "orbit-cli"
```

**Linux:**
```bash
# Using secret-tool (GNOME Keyring)
secret-tool search service "orbit-cli"

# Using kwallet (KDE)
kwallet-query kdewallet -r "orbit-cli"

# Using dbus (generic)
dbus-send --session --dest=org.freedesktop.secrets \
  --print-reply /org/freedesktop/secrets \
  org.freedesktop.Secret.Service.SearchItems \
  dict:string:string:"service","orbit-cli"
```

**GUI Method (macOS):**
1. Open "Keychain Access" app
2. Search for "orbit-cli"
3. View entries for "auth-token" and "server-url"

**GUI Method (Linux):**
- **GNOME**: Open "Passwords and Keys" (seahorse)
- **KDE**: Open "KDE Wallet Manager"

#### Delete Stored Credentials

**macOS:**
```bash
# Delete auth token
security delete-generic-password -s "orbit-cli" -a "auth-token"

# Delete server URL
security delete-generic-password -s "orbit-cli" -a "server-url"

# Delete all orbit-cli entries
security delete-generic-password -s "orbit-cli"
```

**Linux:**
```bash
# Using secret-tool (GNOME Keyring)
secret-tool remove service "orbit-cli" account "auth-token"
secret-tool remove service "orbit-cli" account "server-url"

# Using kwallet (KDE)
kwallet-query kdewallet -d "orbit-cli"
```

**Fallback File:**
```bash
# Remove fallback file storage
rm ~/.orbit/.env
```

#### Troubleshooting Credential Storage

**Check if keyring is available:**
```bash
python -c "import keyring; print('Keyring available:', keyring.get_keyring())"
```

**Force fallback storage:**
```bash
# Clear keyring and force file storage
orbit logout
rm ~/.orbit/.env  # if exists
# Next login will use fallback storage
```

**Reset all credentials:**
```bash
# Complete credential reset
orbit logout
rm -rf ~/.orbit/
# Re-login to recreate storage
```

### Security Considerations

#### Keyring vs File Storage

- **Keyring (Recommended)**: Uses system's encrypted credential storage
- **File Storage (Fallback)**: Base64 encoded, file permissions 600
- **Migration**: Automatically migrates from file to keyring when available

#### Security Best Practices

1. **Use Keyring**: Install `keyring` package for enhanced security
2. **Regular Rotation**: Change passwords periodically
3. **Session Management**: Use `orbit logout` to clear credentials
4. **Access Control**: Keep `~/.orbit/` directory secure (chmod 700)

#### Installation Requirements

**macOS:**
```bash
# Keyring support is built-in
pip install keyring
```

**Linux:**
```bash
# GNOME Keyring
sudo apt-get install python3-keyring gnome-keyring

# KDE Wallet
sudo apt-get install python3-keyring kwallet

# Generic Secret Service
sudo apt-get install python3-keyring libsecret-1-dev
```

#### Configuring Storage Method

**Set storage method in config.yaml:**
```yaml
auth:
  credential_storage: keyring  # or "file"
```

**Change storage method:**
```bash
# Switch to file storage (plain text)
orbit config set auth.credential_storage file

# Switch back to keyring storage
orbit config set auth.credential_storage keyring

# Clear existing credentials after changing method
orbit logout
```

**Check current storage method:**
```bash
orbit config show --key auth.credential_storage
```

## CLI Commands

### Authentication Commands

#### Login
```bash
# Interactive login (recommended)
orbit login

# With credentials (less secure)
orbit login --username admin --password secret123
```

#### Logout
```bash
orbit logout
```

#### Current User Info
```bash
orbit me
```

#### Check Authentication Status
```bash
# Check if authenticated and show user info
orbit auth-status

# Check with JSON output for scripting
orbit auth-status --output json

# Check authentication and credential storage
orbit auth-status
# Shows:
# - Authentication status
# - User information
# - Security storage method (keyring vs file)
```

### Password Management

#### Change Password (Self-Service)
```bash
# Interactive (recommended)
orbit change-password

# With arguments (less secure)
orbit change-password --current-password old --new-password new
```

### User Management (Admin Only)

#### List Users
```bash
orbit user list
```

#### Register New User
```bash
orbit register --username newuser --password pass123 --role user
```

#### Delete User
```bash
orbit user delete --user-id 507f1f77bcf86cd799439011
```

#### Reset User Password
```bash
orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass123
```

## Configuration

### Security Configuration

```yaml
auth:
  # Enable/disable authentication system
  enabled: true
  
  # Password hashing configuration
  pbkdf2_iterations: 600000  # OWASP 2023 recommended minimum
  
  # Session configuration
  session_duration_hours: 12
  
  # Default admin (change immediately!)
  default_admin_username: "admin"
  default_admin_password: "${ORBIT_DEFAULT_ADMIN_PASSWORD}"
  
  # Credential storage method: "keyring" (default) or "file"
  # - keyring: Uses system keychain (macOS Keychain, Linux Secret Service) - more secure
  # - file: Uses plain text file in ~/.orbit/.env - less secure but visible
  credential_storage: keyring
```

### MongoDB Settings

```yaml
internal_services:
  mongodb:
    # Collection names
    users_collection: "users"
    sessions_collection: "sessions"
    
    # Connection settings
    connection_string: "mongodb://localhost:27017"
    database_name: "orbit"
```

## External Identity Providers (OIDC)

ORBIT can validate access tokens issued by **Microsoft Entra ID** and **Auth0** on top of the built-in username/password system. This is a **validation-only** integration: the client (e.g. `orbitchat`) performs the OAuth 2.0 Authorization Code + PKCE login and sends the resulting access token to ORBIT as `Authorization: Bearer <jwt>`. ORBIT verifies the JWT and maps it to a local user. ORBIT itself never initiates an OAuth flow — there is no CLI browser login.

### How it works

The bearer token presented on every request is inspected by `AuthService.validate_token()`:

- **Opaque session tokens** (issued by `orbit login`, 64 hex characters, no dots) → validated against the database `sessions` table as before.
- **JWTs** (external-provider access tokens, always contain two dots) → routed to the OIDC validator when `auth.providers.enabled` is true.

For a JWT, ORBIT:

1. Reads the unverified `iss` claim only to select the matching provider (routing).
2. Fetches the provider's signing key from its JWKS endpoint (cached in memory) and fully verifies the token: **RS256** signature, `iss`, `aud`, and `exp` (60s leeway). `sub` is required.
3. **Just-in-time provisions** a local user on first login, keyed by subject. The stored username is `"{provider}:{sub}"` (e.g. `entra:00000000-...` or `auth0|abc123`), with the email captured for display. On later logins the existing user is reused.
4. Returns the same user context (`id`, `username`, `role`, `active`) as a normal login, so RBAC, admin routes, and audit logging all work identically.

Any invalid, expired, mis-issued, or wrong-audience token is rejected (401) — the validator fails closed and never raises.

Notes:
- **Role assignment**: a JIT-provisioned user receives `auth.providers.default_role` **at creation only**. Roles are managed in ORBIT thereafter (e.g. promote to admin via `orbit user ...`) and are **not** overwritten on subsequent logins.
- **External users cannot password-login**: they have no usable local password. `orbit login` and `change-password` reject them.
- **Deactivation is honored**: deactivating a JIT-provisioned user blocks re-login; it is not silently reactivated.

### Installation

The OIDC libraries are not part of the default install. Add the `auth-providers` profile:

```bash
./install/setup.sh --profile auth-providers   # installs PyJWT[crypto]
```

If `auth.providers.enabled` is true but the profile is not installed, the server **fails fast at startup** with an install hint.

### Configuration

In `config/config.yaml`, under the `auth:` block:

```yaml
auth:
  # ... existing username/password settings ...
  providers:
    enabled: false                 # Master switch for external-provider validation
    default_role: "user"           # Role assigned to users provisioned on first login
    entra:
      enabled: false
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID:-}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID:-}   # Expected token audience
    auth0:
      enabled: false
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN:-}          # e.g. your-tenant.us.auth0.com
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE:-}      # API identifier = expected audience
```

Secrets are supplied via environment variables:

| Variable | Provider | Purpose |
|----------|----------|---------|
| `ORBIT_AUTH_ENTRA_TENANT_ID` | Entra | Directory (tenant) ID — used to build issuer and JWKS URLs |
| `ORBIT_AUTH_ENTRA_CLIENT_ID` | Entra | Application (client) ID — the expected token `aud` |
| `ORBIT_AUTH_AUTH0_DOMAIN` | Auth0 | Tenant domain, e.g. `your-tenant.us.auth0.com` |
| `ORBIT_AUTH_AUTH0_AUDIENCE` | Auth0 | API identifier registered in Auth0 — the expected token `aud` |

Derived endpoints (no configuration needed):

| Provider | Issuer (`iss`) | JWKS |
|----------|----------------|------|
| Entra | `https://login.microsoftonline.com/{tenant_id}/v2.0` | `https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys` |
| Auth0 | `https://{domain}/` | `https://{domain}/.well-known/jwks.json` |

Accepted audience: Auth0 → the configured `audience`; Entra → either the bare `client_id` or `api://{client_id}`.

### Provider setup

**Microsoft Entra ID**
1. Register an application in Entra ID (Azure AD) → copy the **Application (client) ID** and **Directory (tenant) ID**.
2. Under **Expose an API**, set the Application ID URI (`api://{client_id}`) and add a scope (e.g. `access_as_user`). The client must request this scope so the issued access token's `aud` targets ORBIT.
3. Set `ORBIT_AUTH_ENTRA_TENANT_ID` / `ORBIT_AUTH_ENTRA_CLIENT_ID` and enable the provider.

**Auth0**
1. Create an **API** in Auth0 → its **Identifier** is the audience (`ORBIT_AUTH_AUTH0_AUDIENCE`).
2. Create/register the SPA application the client uses; note the tenant **domain** (`ORBIT_AUTH_AUTH0_DOMAIN`).
3. The client requests tokens with `audience` set to the API identifier so the access token's `aud` matches ORBIT.

> **Important — Entra audience caveat.** Entra only issues a token whose `aud` equals your app when the client requests a scope for *your* API (`api://{client_id}/...`). If the client only requests Microsoft Graph scopes (e.g. `User.Read`), it receives a **Graph** access token whose audience is Graph — ORBIT cannot and must not validate that token. Ensure the client (e.g. the `orbitchat` MSAL scopes) requests ORBIT's own API scope, not just Graph scopes.

### Admin Panel SSO

The bearer-token validation above is for API clients that already hold a provider token. ORBIT's **own admin panel** (`/admin`) can additionally offer "Sign in with Microsoft / Auth0" using a **server-side OAuth 2.0 Authorization Code + PKCE** flow. On success it mints the same `dashboard_token` session cookie the username/password login uses, so the rest of the admin panel is unchanged.

**Flow**

1. The login page shows a button per enabled provider linking to `GET /admin/auth/{provider}/login`.
2. That route generates `state`, a PKCE `code_verifier`/`code_challenge`, and a `nonce`, stashes them in a short-lived httponly cookie (`admin_sso_flow`, ~5 min, `SameSite=Lax`), and redirects to the provider's authorize endpoint.
3. The provider redirects back to `GET /admin/auth/{provider}/callback`. ORBIT verifies `state`, exchanges the `code` at the token endpoint, and validates the returned **id_token** (RS256 via JWKS, `aud == client_id`, `iss`, `exp`, and matching `nonce`).
4. The user's email/subject is checked against the **admin allowlist**. If authorized, the user is JIT-provisioned (or promoted) as an `admin` and a `dashboard_token` session cookie is set. Otherwise the login page shows an error.

**Configuration**

```yaml
auth:
  providers:
    entra:
      enabled: true
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID}
      client_secret: ${ORBIT_AUTH_ENTRA_CLIENT_SECRET:-}   # optional (confidential client)
    auth0:
      enabled: true
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN}
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE}
      client_id: ${ORBIT_AUTH_AUTH0_CLIENT_ID}             # required for SSO (id_token audience)
      client_secret: ${ORBIT_AUTH_AUTH0_CLIENT_SECRET:-}   # optional (confidential client)
    admin_sso:
      enabled: true
      base_url: ${ORBIT_ADMIN_BASE_URL:-}   # optional; set when behind a proxy so the redirect URI is correct
      admin_users:                          # emails and/or "provider:subject" granted admin at login
        - "alice@example.com"
        - "entra:00000000-0000-0000-0000-000000000000"
```

Additional environment variables: `ORBIT_AUTH_AUTH0_CLIENT_ID`, `ORBIT_AUTH_ENTRA_CLIENT_SECRET`, `ORBIT_AUTH_AUTH0_CLIENT_SECRET`, `ORBIT_ADMIN_BASE_URL`.

- **`client_secret` is optional.** With PKCE alone the flow works as a public client (you can reuse an SPA app registration). Supplying a secret upgrades the code exchange to a confidential client.
- **Admin access is granted only by `admin_users`.** A matching user is created/promoted to `admin` at login; a non-matching authenticated user is rejected. There's no need for a bootstrap password admin.

**Redirect URI to register** with each provider (must match exactly):

```
{base_url or auto-detected origin}/admin/auth/entra/callback
{base_url or auto-detected origin}/admin/auth/auth0/callback
```

For Auth0, add these to the application's **Allowed Callback URLs**; for Entra, add them as **Web** redirect URIs on the app registration. Set `base_url` when ORBIT sits behind a reverse proxy/TLS terminator so the callback URL matches what was registered.

**Security notes**

- `state` (CSRF), PKCE `code_challenge` (S256), and `nonce` (replay) are all enforced; the flow secrets live only in a short-lived httponly cookie.
- The id_token is validated against `client_id` as audience (distinct from the API-audience used for bearer access tokens), plus issuer, expiry, and nonce; validation fails closed.
- Buttons are plain links — no client-side JS SDK is loaded, so the admin panel's Content-Security-Policy is unaffected.

### Consistency with the orbitchat client

Provider names (`entra`, `auth0`) and the token model match the `orbitchat` client, which already implements these logins (MSAL for Entra, `@auth0/auth0-react` for Auth0) and sends the access token as a bearer token. The server maps identity from the validated JWT `sub` claim (the same immutable subject the client uses), so server and client agree on user identity.

### Adding a new provider

Any OpenID Connect provider (Okta, Keycloak, Google, Ping, etc.) can be added with a small, well-contained change. Because both the bearer path and admin SSO are driven by config-selected provider metadata, the work is mostly "teach ORBIT this provider's endpoint URLs." The example below adds a provider named `okta`.

The core assumption to preserve: tokens are **RS256-signed OIDC JWTs** validated against the provider's **JWKS** by `issuer`/`audience`/`exp`/`sub`. Providers that don't fit that model (opaque tokens, non-OIDC OAuth) need more than these steps.

#### 1. Add the endpoint derivation

Both services build their provider metadata from a single helper per provider in `server/services/oidc_validator.py`. Add one for the new provider next to `entra_endpoints()` / `auth0_endpoints()`:

```python
def okta_endpoints(domain: str) -> Dict[str, str]:
    domain = domain.rstrip('/')
    return {
        "issuer": f"https://{domain}",                       # some Okta orgs use /oauth2/default
        "jwks_uri": f"https://{domain}/oauth2/v1/keys",
        "authorize_url": f"https://{domain}/oauth2/v1/authorize",
        "token_url": f"https://{domain}/oauth2/v1/token",
    }
```

> Prefer fetching these from the provider's discovery document (`/.well-known/openid-configuration`) if you don't want to hardcode paths. Keep the four keys (`issuer`, `jwks_uri`, `authorize_url`, `token_url`) — that's the shape both services consume.

#### 2. Register it for bearer validation

In `OIDCValidator.__init__` (`server/services/oidc_validator.py`), add a block mirroring the `entra`/`auth0` ones, and a `_build_okta()` that returns `{issuer, audiences, jwks_client}`:

```python
okta = providers_config.get('okta', {})
if okta.get('enabled'):
    self._providers['okta'] = self._build_okta(okta)
```

`validate()` needs no change: it already routes by matching the token's `iss` to a registered provider's `issuer`, verifies RS256 against that provider's JWKS, and normalizes claims to `{provider, external_id=sub, email}`. Provisioning, the `provider:sub` username scheme, and the `validate_token` shape-branch are all provider-agnostic.

#### 3. (Optional) Register it for admin panel SSO

In `AdminSSOService.__init__` (`server/services/admin_sso_service.py`), add the same enable-check calling `self._build(okta_cfg, okta_endpoints(...), label="Okta")`. `build_authorize_url` / `exchange_code` / `validate_id_token` / `is_admin` are generic and need no change. The login route `/admin/auth/{provider}/login` accepts any provider name the service knows, and the login page renders a button for each via `provider_labels()`.

#### 4. Add config keys

Extend `auth.providers` in `config/config.yaml`:

```yaml
auth:
  providers:
    okta:
      enabled: false
      domain: ${ORBIT_AUTH_OKTA_DOMAIN:-}          # e.g. dev-12345.okta.com
      audience: ${ORBIT_AUTH_OKTA_AUDIENCE:-}      # bearer-path access-token audience
      client_id: ${ORBIT_AUTH_OKTA_CLIENT_ID:-}    # admin-SSO id_token audience
      client_secret: ${ORBIT_AUTH_OKTA_CLIENT_SECRET:-}  # optional (confidential SSO client)
```

Use the `${VAR:-}` optional form so a disabled provider produces no startup warnings, and document the new env vars in `env.example`.

#### 5. Test it

Mirror `server/tests/test_auth/test_external_auth.py` and `test_admin_sso.py`: sign tokens with a local RSA keypair and monkeypatch the provider's `PyJWKClient.get_signing_key_from_jwt` to return the test public key — no network. Cover a valid token (provisions `okta:<sub>`), wrong audience, bad signature, expired, and missing `sub`.

#### Checklist

| Step | File | Required for |
|------|------|--------------|
| `*_endpoints()` helper | `server/services/oidc_validator.py` | both |
| `__init__` enable-block + `_build_*` | `server/services/oidc_validator.py` | bearer validation |
| `__init__` enable-block | `server/services/admin_sso_service.py` | admin SSO (optional) |
| `auth.providers.<name>` block | `config/config.yaml` | both |
| env vars | `env.example` | both |
| tests | `server/tests/test_auth/` | both |

What you do **not** touch: `AuthService.validate_token` (routes by `iss`), the `provider:sub` provisioning, `auth_dependencies.py`, any route, or the login-page template — they're all provider-agnostic by design.

### Security notes

- Signatures are verified with **RS256 only** (no algorithm downgrade, no `none`).
- `exp`, `iss`, `aud`, and `sub` are all required; tokens missing any are rejected.
- Signing keys are fetched from JWKS over TLS and cached; the blocking fetch runs off the event loop.
- Identity is taken **only** from the verified JWT — the `X-User-ID` header is used for chat-history attribution, never for authorization.

## Implementation Details

### Service Layer (AuthService)

Located in `server/services/auth_service.py`

#### Key Methods:

- `authenticate_user()`: Validate credentials and create session
- `validate_token()`: Check token validity and return user info (routes JWTs to OIDC validation — see [External Identity Providers](#external-identity-providers-oidc))
- `change_password()`: Update password with verification
- `reset_user_password()`: Admin password reset without verification
- `create_user()`: Create new user account
- `delete_user()`: Remove user and all sessions
- `list_users()`: Get all user accounts

External-provider (OIDC) token verification lives in `server/services/oidc_validator.py` (`OIDCValidator`), built by `AuthService` during `initialize()` when `auth.providers.enabled` is set.

#### Security Features:

- Password hashing with PBKDF2-SHA256
- Cryptographically secure token generation
- Session management with automatic cleanup
- Comprehensive error handling and logging

### API Layer (auth_routes.py)

Located in `server/routes/auth_routes.py`

#### Features:

- FastAPI-based REST endpoints
- Pydantic models for request/response validation
- Dependency injection for service access
- Role-based authorization decorators
- Comprehensive error handling

### CLI Layer (orbit.py)

Located in `bin/orbit.py`

#### Features:

- Interactive password prompts with `getpass`
- Simplified token storage using secure storage (keyring/file) as single source of truth
- Session token management via `self.admin_token` instance variable
- Comprehensive error handling and user feedback
- Support for both interactive and scripted usage
- Automatic migration from legacy storage formats

## Security Best Practices

### Implemented

✅ **Strong Password Hashing**: PBKDF2-SHA256 with 600k iterations  
✅ **Secure Token Generation**: Cryptographically random tokens  
✅ **Session Expiration**: Automatic timeout and cleanup  
✅ **Password Confirmation**: Interactive CLI prompts confirmation  
✅ **Session Invalidation**: Password changes clear all sessions  
✅ **Role-Based Access**: Admin-only endpoints protected  
✅ **Input Validation**: Pydantic models validate all inputs  
✅ **Error Handling**: Secure error messages, no info leakage  
✅ **Audit Logging**: Authentication events logged  

### Recommended Additional Security

🔸 **Rate Limiting**: Implement login attempt throttling  
🔸 **Account Lockout**: Temporary lockout after failed attempts  
🔸 **Password Complexity**: Enforce minimum password requirements  
🔸 **Session Monitoring**: Track active sessions per user  
🔸 **IP Whitelisting**: Restrict admin access by IP  
🔸 **2FA Support**: Two-factor authentication for admin accounts  
🔸 **Audit Trail**: Detailed logging of all user actions  

## Error Handling

### Common Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Invalid username or password"
}
```

#### 403 Forbidden  
```json
{
  "detail": "Only administrators can create new users"
}
```

#### 404 Not Found
```json
{
  "detail": "User not found or could not be deleted"
}
```

#### 400 Bad Request
```json
{
  "detail": "Current password is incorrect or password change failed"
}
```

### CLI Error Handling

The CLI provides user-friendly error messages and proper exit codes:

```bash
# Example error output
$ orbit login --username invalid --password wrong
Login failed: Login failed: 401 {"detail":"Invalid username or password"}

# Exit codes
0 = Success
1 = Error/Failure
```

## Usage Examples

### Initial Setup

```bash
# 1. Start the server (creates default admin)
orbit start

# 2. Login with default credentials
orbit login --username admin --password admin123

# 3. Change default password immediately
orbit change-password
# Enter current password: admin123
# Enter new password: [secure_password]
# Confirm new password: [secure_password]

# 4. Create additional users
orbit register --username developer --password devpass123 --role user
orbit register --username manager --password mgmtpass123 --role admin
```

### Daily Operations

```bash
# Login
orbit login --username developer

# Check current user
orbit me

# Change your password
orbit change-password

# List all users (admin only)
orbit user list

# Reset forgotten password (admin only)
orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password temppass123

# Logout
orbit logout
```

## Monitoring and Maintenance

### Session Monitoring

Monitor active sessions in MongoDB:

```javascript
// Count active sessions
db.sessions.countDocuments({expires: {$gt: new Date()}})

// List active sessions
db.sessions.find({expires: {$gt: new Date()}}).pretty()

// Clean up expired sessions (automatic via TTL)
db.sessions.deleteMany({expires: {$lt: new Date()}})
```

### User Management

```javascript
// List all users
db.users.find({}, {password: 0}).pretty()

// Find inactive users
db.users.find({active: false})

// Count users by role
db.users.aggregate([
  {$group: {_id: "$role", count: {$sum: 1}}}
])
```

### Security Audit

```bash
# Check for default passwords
orbit user list | grep -i admin

# Monitor failed login attempts in logs
grep "Invalid password" logs/orbit.log

# Check session duration configuration
grep -r "session_duration_hours" config/
```

## Development Notes

### Adding New Authentication Features

1. **Service Layer**: Add method to `AuthService`
2. **API Layer**: Add endpoint to `auth_routes.py` 
3. **CLI Layer**: Add command to `orbit.py`
4. **Documentation**: Update this document
5. **Testing**: Add integration tests

### Testing Authentication

```bash
# Run authentication tests
cd server/tests
python -m pytest test_auth_*.py -v

# Manual API testing
curl -X POST http://localhost:3000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### Database Migration

When modifying user/session schema:

1. **Backup**: Export existing users/sessions
2. **Update**: Modify service layer schema
3. **Migrate**: Convert existing data
4. **Test**: Verify authentication still works
5. **Deploy**: Update production systems