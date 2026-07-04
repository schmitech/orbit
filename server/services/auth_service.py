"""
Authentication Service
=====================

This service handles user authentication, session management, and password hashing
using only Python standard library dependencies. Implements a simple bearer token
system with database-backed sessions (supports both MongoDB and SQLite).
"""

import hashlib
import hmac
import secrets
import base64
import logging
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, UTC

from services.database_service import (
    DatabaseService,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseDuplicateKeyError,
    DatabaseTimeoutError
)

logger = logging.getLogger(__name__)


class AuthService:
    """Service for handling user authentication and session management"""

    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 50
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_MAX_LENGTH = 128
    USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

    def __init__(self, config: Dict[str, Any], database_service: Optional[DatabaseService] = None):
        """Initialize the authentication service with configuration"""
        self.config = config

        # Use provided database service or create a new one using factory
        if database_service is None:
            from services.database_service import create_database_service
            database_service = create_database_service(config)
        self.database = database_service

        # Collection/table names - read from backend-specific config or use defaults
        backend_type = config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')

        if backend_type == 'mongodb':
            mongodb_config = config.get('internal_services', {}).get('mongodb', {})
            self.users_collection_name = mongodb_config.get('users_collection', 'users')
            self.sessions_collection_name = mongodb_config.get('sessions_collection', 'sessions')
        else:
            # SQLite or other backends: use default table names
            self.users_collection_name = 'users'
            self.sessions_collection_name = 'sessions'
        
        # Session configuration
        self.session_duration_hours = config.get('auth', {}).get('session_duration_hours', 12)
        
        # Default admin configuration
        self.default_admin_username = config.get('auth', {}).get('default_admin_username', 'admin')
        self.default_admin_password = config.get('auth', {}).get('default_admin_password', 'admin123')

        # External identity provider (OIDC) configuration - built in initialize()
        self._oidc = None
        self._oidc_enabled = False
        self._oidc_default_role = 'user'

        # Initialize state
        self._initialized = False
        self.users_collection = None
        self.sessions_collection = None
        
    async def initialize(self) -> None:
        """Initialize the service and create default admin user if needed"""
        await self.database.initialize()

        # Set up collections
        self.users_collection = self.database.get_collection(self.users_collection_name)
        self.sessions_collection = self.database.get_collection(self.sessions_collection_name)

        # Create indexes
        await self.database.create_index(self.users_collection_name, "username", unique=True)
        await self.database.create_index(self.sessions_collection_name, "token", unique=True)
        await self.database.create_index(self.sessions_collection_name, "expires", ttl_seconds=0)

        logger.info("Created indexes for users and sessions collections")
        
        # Create default admin user if it doesn't exist
        await self._create_default_admin()

        # Set up external identity providers (Entra ID, Auth0) if enabled
        self._initialize_oidc()

        # Set initialized flag
        self._initialized = True

        logger.info("Authentication Service initialized successfully")

    def _initialize_oidc(self) -> None:
        """Build the external identity provider validator if configured.

        Fails fast (raises) when providers are enabled but misconfigured or the
        PyJWT dependency is missing, since the operator explicitly opted in.
        """
        providers_config = self.config.get('auth', {}).get('providers', {})
        if not providers_config.get('enabled'):
            return

        from services.oidc_validator import OIDCValidator
        validator = OIDCValidator(providers_config)
        if not validator.enabled:
            logger.warning("auth.providers.enabled is true but no provider is enabled")
            return

        self._oidc = validator
        self._oidc_enabled = True
        self._oidc_default_role = providers_config.get('default_role', 'user')

    def _hash_password(self, password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Hash a password using PBKDF2-SHA256
        
        Args:
            password: The password to hash
            salt: Optional salt to use (generates random if not provided)
            
        Returns:
            Tuple of (salt, hash)
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        
        # Read iterations from config, falling back to 100000 if not set.
        iterations = self.config.get('auth', {}).get('pbkdf2_iterations', 600000)

        # Use PBKDF2 with SHA256, with the configured number of iterations
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        
        return salt, dk

    @classmethod
    def validate_username(cls, username: str) -> Optional[str]:
        """Validate username rules for user creation."""
        if username is None:
            return "Username is required"
        if username != username.strip():
            return "Username cannot start or end with spaces"
        if len(username) < cls.USERNAME_MIN_LENGTH:
            return f"Username must be at least {cls.USERNAME_MIN_LENGTH} characters"
        if len(username) > cls.USERNAME_MAX_LENGTH:
            return f"Username must be at most {cls.USERNAME_MAX_LENGTH} characters"
        if not cls.USERNAME_PATTERN.fullmatch(username):
            return "Username may only contain letters, numbers, periods, underscores, and hyphens"
        return None

    @classmethod
    def validate_password(cls, password: str) -> Optional[str]:
        """Validate password rules without imposing composition requirements."""
        if password is None:
            return "Password is required"
        if len(password) < cls.PASSWORD_MIN_LENGTH:
            return f"Password must be at least {cls.PASSWORD_MIN_LENGTH} characters"
        if len(password) > cls.PASSWORD_MAX_LENGTH:
            return f"Password must be at most {cls.PASSWORD_MAX_LENGTH} characters"
        if any(ch.isspace() for ch in password):
            return "Password cannot contain spaces or other whitespace"
        return None
    
    def _verify_password(self, password: str, stored_password: str) -> bool:
        """
        Verify a password against a stored hash
        
        Args:
            password: The password to verify
            stored_password: Base64 encoded salt+hash
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            # Decode the stored password
            decoded = base64.b64decode(stored_password)
            
            # Extract salt (first 16 bytes) and hash (remaining bytes)
            salt = decoded[:16]
            stored_hash = decoded[16:]
            
            # Hash the provided password with the same salt
            _, computed_hash = self._hash_password(password, salt)
            
            # Use constant-time comparison
            return hmac.compare_digest(stored_hash, computed_hash)
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error decoding stored password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying password: {str(e)}")
            return False
    
    def _encode_password(self, salt: bytes, hash_bytes: bytes) -> str:
        """Encode salt and hash as a base64 string for storage."""
        return base64.b64encode(salt + hash_bytes).decode('utf-8')

    def _hash_and_encode(self, password: str) -> str:
        """Hash a password and return the base64-encoded salt+hash string."""
        salt, hash_bytes = self._hash_password(password)
        return self._encode_password(salt, hash_bytes)

    @staticmethod
    def _user_info(user: Dict[str, Any]) -> Dict[str, Any]:
        """Build the auth-context user dict (no password, no timestamps)."""
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "role": user.get("role", "user"),
            "active": user.get("active", True),
        }

    @staticmethod
    def _user_record(user: Dict[str, Any]) -> Dict[str, Any]:
        """Build the full user record dict (no password)."""
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "role": user.get("role", "user"),
            "active": user.get("active", True),
            "created_at": user.get("created_at"),
            "last_login": user.get("last_login"),
            "provider": user.get("provider"),
            "email": user.get("email"),
        }
    
    async def _create_default_admin(self) -> None:
        """Create default admin user if it doesn't exist"""
        try:
            # Check if admin user exists
            admin_user = await self.database.find_one(
                self.users_collection_name,
                {"username": self.default_admin_username}
            )

            if not admin_user:
                # Create default admin user
                user_doc = {
                    "username": self.default_admin_username,
                    "password": self._hash_and_encode(self.default_admin_password),
                    "role": "admin",
                    "active": True,
                    "created_at": datetime.now(UTC),
                    "last_login": None
                }

                await self.database.insert_one(self.users_collection_name, user_doc)
                logger.info(f"Created default admin user: {self.default_admin_username}")
                logger.warning("Please change the default admin password immediately!")
            else:
                logger.debug(f"Default admin user already exists: {self.default_admin_username}")

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error creating default admin user: {str(e)}")
            raise
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error creating default admin user: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating default admin user: {str(e)}")
            raise
    
    async def verify_credentials(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify username/password without creating a session token.
        """
        try:
            user = await self.database.find_one(
                self.users_collection_name,
                {"username": username}
            )

            if not user or not user.get("active", True):
                return False, None

            if not self._verify_password(password, user["password"]):
                return False, None

            return True, self._user_info(user)
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error verifying credentials for {username}: {str(e)}")
            return False, None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error verifying credentials for {username}: {str(e)}")
            return False, None
        except Exception as e:
            logger.error(f"Unexpected error verifying credentials for {username}: {str(e)}")
            return False, None
    
    async def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Authenticate a user and create a session
        
        Args:
            username: The username
            password: The password
            
        Returns:
            Tuple of (success, token, user_info)
        """
        try:
            # Find user
            user = await self.database.find_one(
                self.users_collection_name,
                {"username": username}
            )
            
            if not user:
                logger.warning(f"Login attempt for non-existent user: {username}")
                return False, None, None
            
            # Check if user is active
            if not user.get("active", True):
                logger.warning(f"Login attempt for inactive user: {username}")
                return False, None, None

            # External users authenticate only through their identity provider
            if user.get("provider"):
                logger.warning(f"Password login attempt for external user: {username}")
                return False, None, None

            # Verify password
            if not self._verify_password(password, user["password"]):
                logger.warning(f"Invalid password for user: {username}")
                return False, None, None

            token = await self.create_session(user)

            logger.debug(f"User {username} logged in successfully")
            return True, token, self._user_info(user)

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error authenticating user {username}: {str(e)}")
            return False, None, None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error authenticating user {username}: {str(e)}")
            return False, None, None
        except Exception as e:
            logger.error(f"Unexpected error authenticating user {username}: {str(e)}")
            return False, None, None

    async def create_session(self, user: Dict[str, Any]) -> str:
        """Mint a session token for an already-authenticated user.

        Used both by password login and by SSO (where the identity is verified
        by an external provider rather than a local password).
        """
        token = secrets.token_hex(32)
        session_doc = {
            "token": token,
            "user_id": user["_id"],
            "username": user["username"],
            "expires": datetime.now(UTC) + timedelta(hours=self.session_duration_hours),
            "created_at": datetime.now(UTC),
        }
        await self.database.insert_one(self.sessions_collection_name, session_doc)
        await self.database.update_one(
            self.users_collection_name,
            {"_id": user["_id"]},
            {"$set": {"last_login": datetime.now(UTC)}}
        )
        return token

    async def set_role(self, user_id: str, role: str) -> bool:
        """Set a user's role. Used to promote allowlisted SSO users to admin."""
        if role not in {"user", "admin"}:
            logger.warning(f"Rejected set_role for invalid role: {role}")
            return False
        try:
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user_id_converted},
                {"$set": {"role": role}}
            )
            return bool(result)
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error setting role for {user_id}: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error setting role for {user_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting role for {user_id}: {str(e)}")
            return False

    def _ensure_utc_datetime(self, dt):
        """
        Ensure a datetime is timezone-aware (UTC)
        
        Args:
            dt: A datetime object that might be naive or aware
            
        Returns:
            A timezone-aware datetime in UTC
        """
        if dt is None:
            return None
        
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    
    async def validate_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate a session token
        
        Args:
            token: The bearer token to validate
            
        Returns:
            Tuple of (is_valid, user_info)
        """
        # External-provider JWTs carry two dots; opaque session tokens (hex)
        # carry none. Route JWT-shaped tokens to OIDC validation when enabled;
        # everything else uses the database-backed session path below.
        if self._oidc_enabled and token.count(".") == 2:
            ok, claims = await self._oidc.validate(token)
            if not ok:
                return False, None
            user = await self._find_or_create_external_user(
                claims["provider"], claims["external_id"], claims.get("email")
            )
            if not user or not user.get("active", True):
                return False, None
            return True, self._user_info(user)

        try:
            # Find session
            session = await self.database.find_one(
                self.sessions_collection_name,
                {"token": token}
            )
            
            if not session:
                return False, None
            
            # Check if expired - ensure both datetimes are timezone-aware
            expires = self._ensure_utc_datetime(session["expires"])
            now = datetime.now(UTC)
            
            if expires < now:
                # Clean up expired session
                await self.database.delete_one(
                    self.sessions_collection_name,
                    {"_id": session["_id"]}
                )
                return False, None
            
            # Get user info
            user = await self.database.find_one(
                self.users_collection_name,
                {"_id": session["user_id"]}
            )
            
            if not user or not user.get("active", True):
                return False, None

            return True, self._user_info(user)

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error validating token: {str(e)}")
            return False, None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error validating token: {str(e)}")
            return False, None
        except Exception as e:
            logger.error(f"Unexpected error validating token: {str(e)}")
            return False, None
    
    async def logout(self, token: str) -> bool:
        """
        Logout a user by invalidating their token
        
        Args:
            token: The bearer token to invalidate
            
        Returns:
            True if successful, False otherwise
        """
        # External-provider JWTs are stateless - there is no local session row
        # to delete. Logout is a no-op success; the client discards the token.
        if self._oidc_enabled and token.count(".") == 2:
            return True

        try:
            result = await self.database.delete_one(
                self.sessions_collection_name,
                {"token": token}
            )

            if result:
                logger.debug("User logged out successfully")

            return result
            
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error during logout: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error during logout: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during logout: {str(e)}")
            return False
    
    async def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """
        Change a user's password
        
        Args:
            user_id: The user's ID
            old_password: The current password
            new_password: The new password
            
        Returns:
            True if successful, False otherwise
        """
        try:
            password_error = self.validate_password(new_password)
            if password_error:
                logger.warning(f"Rejected password change for invalid new password: {password_error}")
                return False

            # Get user
            # Use database service to ensure ID is in correct format for backend
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            user = await self.database.find_one(
                self.users_collection_name,
                {"_id": user_id_converted}
            )
            
            if not user:
                return False

            # External users have no local password to change
            if user.get("provider"):
                logger.warning(f"Password change attempt for external user: {user['username']}")
                return False

            # Verify old password
            if not self._verify_password(old_password, user["password"]):
                logger.warning(f"Invalid old password for user: {user['username']}")
                return False
            
            # Update password and invalidate all sessions
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user["_id"]},
                {"$set": {"password": self._hash_and_encode(new_password)}}
            )

            if result:
                await self.database.delete_many(
                    self.sessions_collection_name,
                    {"user_id": user["_id"]}
                )
                logger.debug(f"Password changed for user: {user['username']}")
            
            return result
            
        except ValueError as e:
            logger.error(f"Invalid user ID format: {str(e)}")
            return False
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error changing password: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error changing password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error changing password: {str(e)}")
            return False
    
    async def create_user(self, username: str, password: str, role: str = "user") -> Optional[str]:
        """
        Create a new user
        
        Args:
            username: The username
            password: The password
            role: The user role (default: user)
            
        Returns:
            The new user's ID if successful, None otherwise
        """
        try:
            username_error = self.validate_username(username)
            if username_error:
                logger.warning(f"Rejected user creation for invalid username: {username_error}")
                return None

            password_error = self.validate_password(password)
            if password_error:
                logger.warning(f"Rejected user creation for invalid password: {password_error}")
                return None

            if role not in {"user", "admin"}:
                logger.warning(f"Rejected user creation for invalid role: {role}")
                return None

            # Check if username already exists
            existing = await self.database.find_one(
                self.users_collection_name,
                {"username": username}
            )
            
            if existing:
                logger.warning(f"Username already exists: {username}")
                return None
            
            # Create user document
            user_doc = {
                "username": username,
                "password": self._hash_and_encode(password),
                "role": role,
                "active": True,
                "created_at": datetime.now(UTC),
                "last_login": None
            }
            
            # Insert user
            user_id = await self.database.insert_one(self.users_collection_name, user_doc)
            
            logger.debug(f"Created new user: {username} with role: {role}")
            
            return str(user_id)

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error creating user {username}: {str(e)}")
            return None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error creating user {username}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating user {username}: {str(e)}")
            return None

    async def _find_or_create_external_user(
        self, provider: str, external_id: str, email: Optional[str], role: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Look up a JIT-provisioned external user, creating one on first sight.

        The stored username is ``"{provider}:{external_id}"`` which is unique per
        subject, so this reuses the existing UNIQUE(username) index. External
        users get a random unusable password (they authenticate only via their
        provider). The creation role defaults to the configured provider default;
        callers (e.g. admin SSO) may pass an explicit role. The role is assigned
        at creation and never overwritten on subsequent logins here, so ORBIT-side
        role changes are preserved.
        """
        create_role = role or self._oidc_default_role
        username = f"{provider}:{external_id}"
        try:
            user = await self.database.find_one(
                self.users_collection_name, {"username": username}
            )
            if user:
                # Respect deactivation - do not silently reactivate on re-login.
                return user

            user_doc = {
                "username": username,
                "password": self._hash_and_encode(secrets.token_hex(32)),
                "role": create_role,
                "active": True,
                "provider": provider,
                "external_id": external_id,
                "email": email,
                "created_at": datetime.now(UTC),
                "last_login": datetime.now(UTC),
            }
            try:
                user_id = await self.database.insert_one(self.users_collection_name, user_doc)
                user_doc["_id"] = user_id
                logger.info(f"Provisioned external user: {username} (provider={provider})")
                return user_doc
            except DatabaseDuplicateKeyError:
                # Concurrent first-login created the row; fetch the winner.
                return await self.database.find_one(
                    self.users_collection_name, {"username": username}
                )
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error provisioning external user {username}: {str(e)}")
            return None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error provisioning external user {username}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error provisioning external user {username}: {str(e)}")
            return None

    async def provision_sso_user(
        self, provider: str, external_id: str, email: Optional[str], is_admin: bool
    ) -> Optional[Dict[str, Any]]:
        """Provision (or fetch) an SSO user and reconcile admin role.

        Called by the admin-panel SSO callback after the id_token is validated
        and the admin allowlist is checked. Creates the user with the right role
        on first login, and promotes an existing user to admin when they are on
        the allowlist. Returns the user document (including ``_id``) or None.
        """
        role = "admin" if is_admin else self._oidc_default_role
        user = await self._find_or_create_external_user(provider, external_id, email, role=role)
        if not user:
            return None

        # Promote an existing (previously non-admin) user now on the allowlist.
        if is_admin and user.get("role") != "admin":
            if await self.set_role(str(user["_id"]), "admin"):
                user["role"] = "admin"
        return user

    async def list_users(self, filter_query: Optional[Dict[str, Any]] = None, limit: int = 100, offset: int = 0) -> list:
        """
        List all users with optional filtering and pagination
        
        Args:
            filter_query: Optional MongoDB filter query
            limit: Maximum number of users to return
            offset: Number of users to skip for pagination
            
        Returns:
            List of user records (without passwords)
        """
        try:
            # Use the provided filter query or default to empty dict
            query = filter_query or {}
            
            # Use database service abstraction for backend-agnostic querying
            results = await self.database.find_many(
                self.users_collection_name,
                query,
                limit=limit,
                skip=offset,
                sort=[("created_at", -1)]  # Sort by created_at descending
            )
            
            return [self._user_record(u) for u in results]

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error listing users: {str(e)}")
            return []
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error listing users: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing users: {str(e)}")
            return []
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single user by ID with full details
        
        Args:
            user_id: The user's ID
            
        Returns:
            User record with full details (without password) or None if not found
        """
        try:
            # Use database service to ensure ID is in correct format for backend
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            
            user = await self.database.find_one(
                self.users_collection_name,
                {"_id": user_id_converted}
            )
            
            if not user:
                return None

            return self._user_record(user)

        except ValueError as e:
            logger.error(f"Invalid user ID format: {str(e)}")
            return None
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error getting user by ID: {str(e)}")
            return None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error getting user by ID: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting user by ID: {str(e)}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get a single user by username with efficient database lookup
        
        Args:
            username: The username to search for
            
        Returns:
            User record with basic details (without password) or None if not found
        """
        try:
            user = await self.database.find_one(
                self.users_collection_name,
                {"username": username}
            )
            
            if not user:
                return None

            return self._user_record(user)

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error getting user by username: {str(e)}")
            return None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error getting user by username: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting user by username: {str(e)}")
            return None
    
    async def update_user_status(self, user_id: str, active: bool) -> bool:
        """
        Activate or deactivate a user
        
        Args:
            user_id: The user's ID
            active: Whether the user should be active
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use database service to ensure ID is in correct format for backend
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user_id_converted},
                {"$set": {"active": active}}
            )
            
            if result and not active:
                await self.database.delete_many(
                    self.sessions_collection_name,
                    {"user_id": user_id_converted}
                )
            
            return result
            
        except ValueError as e:
            logger.error(f"Invalid user ID format: {str(e)}")
            return False
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error updating user status: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error updating user status: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating user status: {str(e)}")
            return False
    
    async def reset_user_password(self, user_id: str, new_password: str) -> bool:
        """
        Reset a user's password (admin function - doesn't require old password)
        
        Args:
            user_id: The user's ID
            new_password: The new password
            
        Returns:
            True if successful, False otherwise
        """
        try:
            password_error = self.validate_password(new_password)
            if password_error:
                logger.warning(f"Rejected password reset for invalid new password: {password_error}")
                return False

            # Use database service to ensure ID is in correct format for backend
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            
            # Get user
            user = await self.database.find_one(
                self.users_collection_name,
                {"_id": user_id_converted}
            )
            
            if not user:
                logger.warning(f"User not found for password reset: {user_id}")
                return False
            
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user["_id"]},
                {"$set": {"password": self._hash_and_encode(new_password)}}
            )

            if result:
                await self.database.delete_many(
                    self.sessions_collection_name,
                    {"user_id": user["_id"]}
                )
                logger.debug(f"Password reset for user: {user['username']} (ID: {user_id})")
            
            return result
            
        except ValueError as e:
            logger.error(f"Invalid user ID format: {str(e)}")
            return False
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error resetting password: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error resetting password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error resetting password: {str(e)}")
            return False
    
    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user and all associated sessions
        
        Args:
            user_id: The user's ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use database service to ensure ID is in correct format for backend
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            
            # Get user first to check if exists
            user = await self.database.find_one(
                self.users_collection_name,
                {"_id": user_id_converted}
            )
            
            if not user:
                logger.warning(f"User not found for deletion: {user_id}")
                return False
            
            # Don't allow deletion of default admin user
            if user["username"] == self.default_admin_username:
                logger.warning(f"Cannot delete default admin user: {user['username']}")
                return False
            
            # Delete all sessions for this user first
            await self.database.delete_many(
                self.sessions_collection_name,
                {"user_id": user["_id"]}
            )
            
            # Delete the user
            result = await self.database.delete_one(
                self.users_collection_name,
                {"_id": user_id_converted}
            )

            if result:
                logger.debug(f"Deleted user: {user['username']} (ID: {user_id})")

            return result
            
        except ValueError as e:
            logger.error(f"Invalid user ID format: {str(e)}")
            return False
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error deleting user: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error deleting user: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting user: {str(e)}")
            return False
    
    async def close(self) -> None:
        """Close the authentication service"""
        # MongoDB service will be closed by the main shutdown process
        logger.info("Authentication service closed")
