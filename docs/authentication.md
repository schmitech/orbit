# Authentication Technical Details

## Overview

ORBIT's authentication leverages PBKDF2-SHA256 (600k iterations) for password security and cryptographically secure bearer tokens for session management. The modular architecture integrates MongoDB for persistent session storage, implements role-based access control (RBAC), and provides both programmatic and CLI interfaces for comprehensive user lifecycle management. 

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
6. **Token Persistence**: CLI stores token locally for future requests
7. **Request Authorization**: Subsequent requests include bearer token
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
orbit auth-status
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

## Implementation Details

### Service Layer (AuthService)

Located in `server/services/auth_service.py`

#### Key Methods:

- `authenticate_user()`: Validate credentials and create session
- `validate_token()`: Check token validity and return user info
- `change_password()`: Update password with verification
- `reset_user_password()`: Admin password reset without verification
- `create_user()`: Create new user account
- `delete_user()`: Remove user and all sessions
- `list_users()`: Get all user accounts

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
- Persistent token storage in `~/.orbit/.env`
- Comprehensive error handling and user feedback
- Support for both interactive and scripted usage

## Security Best Practices

### Implemented

✅ **Strong Password Hashing**: PBKDF2-SHA256 with 100k iterations  
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

### Troubleshooting

```bash
# Check authentication status
orbit auth-status

# Force logout and clear local token
orbit logout
rm ~/.orbit/.env

# Check server logs for auth issues
tail -f logs/orbit.log | grep auth
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