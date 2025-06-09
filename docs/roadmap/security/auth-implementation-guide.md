# ORBIT Authentication Strategies

## Key Changes from Original Design

1. **Simpler Token System**: Uses UUID-based bearer tokens instead of JWT
2. **Minimal Dependencies**: Only uses standard library for password hashing
3. **File-based Token Storage**: Stores auth token in `~/.orbit/.env`
4. **Streamlined CLI**: Simple `login` and `logout` commands
5. **MongoDB Collections**: Uses `users` and `sessions` collections

## Architecture Overview

### 1. Authentication Service (`services/auth_service.py`)
- Uses PBKDF2-SHA256 for password hashing (stdlib only)
- UUID tokens with MongoDB-based sessions
- Simple user management (create, list, activate/deactivate)
- Automatic creation of default admin user

### 2. Server Endpoints (Add to `server.py`)
- `/auth/register` - Register new admin users
- `/auth/login` - Login and receive bearer token
- `/auth/logout` - Logout and invalidate token
- `/auth/me` - Get current user info
- `/auth/change-password` - Change password
- `/admin/users/*` - User management endpoints

### 3. CLI Authentication (`orbit.py`)
- `orbit login --username admin` - Login and save token
- `orbit logout` - Logout and clear token
- Token stored in `~/.orbit/.env` as `API_ADMIN_TOKEN`
- All admin commands require authentication

## MongoDB Schema

### users collection
```json
{
  "_id": ObjectId,
  "username": "admin",
  "password": "base64_encoded_salt_and_hash",
  "role": "admin",
  "active": true,
  "created_at": ISODate,
  "last_login": ISODate
}
```

### sessions collection
```json
{
  "_id": ObjectId,
  "token": "uuid_hex_string",
  "user_id": ObjectId,
  "username": "admin",
  "expires": ISODate,
  "created_at": ISODate
}
```

## Implementation Steps

1. **Add auth_service.py** to `services/` directory
2. **Update server.py**:
   - Add authentication routes
   - Add `get_current_user` dependency
   - Protect all `/admin/*` endpoints with auth
   - Initialize auth service in `_initialize_services`
3. **Replace orbit.py** with simplified version
4. **Update config.yaml** to include user and session collections

## Usage Examples

### First Time Setup
```bash
# Server will create default admin user on first start
orbit start

# Login with default credentials
orbit login --username admin
Password: admin123

# Change default password immediately
curl -X POST http://localhost:3000/auth/change-password \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"old_password": "admin123", "new_password": "new_secure_password"}'
```

### Daily Usage
```bash
# Login
orbit login --username admin
Password: ********

# Now you can use admin commands
orbit key create --collection docs --name "Production"
orbit key list

# Logout when done
orbit logout
```

### Creating Additional Admin Users
```bash
# After logging in as admin
curl -X POST http://localhost:3000/auth/register \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username": "john", "password": "secure_password"}'
```

## Security Features

1. **Password Security**:
   - PBKDF2-SHA256 with 100,000 iterations
   - Random 16-byte salt per password
   - Constant-time comparison

2. **Session Management**:
   - 12-hour session expiration
   - Token invalidation on logout
   - Sessions removed when password changes

3. **File Security**:
   - Token file created with user-only permissions
   - Stored in user's home directory

4. **User Management**:
   - Account activation/deactivation
   - Prevent self-deactivation
   - Audit trail via logs

## Benefits of Simplified Approach

1. **Zero External Dependencies**: Only uses Python stdlib and MongoDB
2. **Easier to Deploy**: No JWT secrets or complex configuration
3. **Familiar Pattern**: Similar to AWS/Azure CLI token storage
4. **Maintainable**: Less code, clearer flow
5. **Self-Contained**: Everything runs within ORBIT infrastructure

## Migration from Existing System

If you have existing API keys, they continue to work. The auth system is only for admin operations. Regular API clients still use the existing `X-API-Key` header system.

## Environment Variables

- `API_ADMIN_TOKEN`: Bearer token saved by `orbit login`
- `ORBIT_DEFAULT_ADMIN_PASSWORD`: Initial admin password (default: admin123)
- `API_SERVER_URL`: Server URL for CLI operations

## Troubleshooting

### Cannot Login
- Ensure MongoDB is running and accessible
- Check server logs for auth service initialization
- Verify username exists and is active

### Token Expired
- Sessions expire after 12 hours
- Run `orbit login` again to get new token

### Permission Denied
- Ensure you're logged in: check `~/.orbit/.env`
- Verify user has admin role
- Check if account is active
