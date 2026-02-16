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
            # MongoDB: read collection names from config
            mongodb_config = config.get('internal_services', {}).get('mongodb', {})
            if not mongodb_config:
                # Fallback to root mongodb section for backward compatibility
                mongodb_config = config.get('mongodb', {})
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
        
        # Set initialized flag
        self._initialized = True
        
        logger.info("Authentication Service initialized successfully")
    
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
        """
        Encode salt and hash as a base64 string for storage
        
        Args:
            salt: The salt bytes
            hash_bytes: The hash bytes
            
        Returns:
            Base64 encoded string
        """
        return base64.b64encode(salt + hash_bytes).decode('utf-8')
    
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
                salt, hash_bytes = self._hash_password(self.default_admin_password)
                encoded_password = self._encode_password(salt, hash_bytes)

                user_doc = {
                    "username": self.default_admin_username,
                    "password": encoded_password,
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

            user_info = {
                "id": str(user["_id"]),
                "username": user["username"],
                "role": user.get("role", "user"),
                "active": user.get("active", True)
            }
            return True, user_info
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
            
            # Verify password
            if not self._verify_password(password, user["password"]):
                logger.warning(f"Invalid password for user: {username}")
                return False, None, None
            
            # Create session token
            # Use cryptographically secure random token generation
            token = secrets.token_hex(32)
            
            # Calculate expiration
            expires = datetime.now(UTC) + timedelta(hours=self.session_duration_hours)
            
            # Create session document
            session_doc = {
                "token": token,
                "user_id": user["_id"],
                "username": username,
                "expires": expires,
                "created_at": datetime.now(UTC)
            }
            
            # Insert session
            await self.database.insert_one(self.sessions_collection_name, session_doc)
            
            # Update last login
            await self.database.update_one(
                self.users_collection_name,
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.now(UTC)}}
            )
            
            logger.debug(f"User {username} logged in successfully")
            
            # Return user info without password
            user_info = {
                "id": str(user["_id"]),
                "username": user["username"],
                "role": user.get("role", "user"),
                "active": user.get("active", True)
            }
            
            return True, token, user_info

        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error authenticating user {username}: {str(e)}")
            return False, None, None
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error authenticating user {username}: {str(e)}")
            return False, None, None
        except Exception as e:
            logger.error(f"Unexpected error authenticating user {username}: {str(e)}")
            return False, None, None
    
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
            # Naive datetime - assume it's UTC
            return dt.replace(tzinfo=UTC)
        else:
            # Already timezone-aware
            return dt
    
    async def validate_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate a session token
        
        Args:
            token: The bearer token to validate
            
        Returns:
            Tuple of (is_valid, user_info)
        """
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
            
            user_info = {
                "id": str(user["_id"]),
                "username": user["username"],
                "role": user.get("role", "user"),
                "active": user.get("active", True)
            }
            
            return True, user_info
            
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
            # Get user
            # Use database service to ensure ID is in correct format for backend
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            user = await self.database.find_one(
                self.users_collection_name,
                {"_id": user_id_converted}
            )
            
            if not user:
                return False
            
            # Verify old password
            if not self._verify_password(old_password, user["password"]):
                logger.warning(f"Invalid old password for user: {user['username']}")
                return False
            
            # Hash new password
            salt, hash_bytes = self._hash_password(new_password)
            encoded_password = self._encode_password(salt, hash_bytes)
            
            # Update password
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user["_id"]},
                {"$set": {"password": encoded_password}}
            )
            
            if result:
                # Invalidate all sessions for this user
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
            # Check if username already exists
            existing = await self.database.find_one(
                self.users_collection_name,
                {"username": username}
            )
            
            if existing:
                logger.warning(f"Username already exists: {username}")
                return None
            
            # Hash password
            salt, hash_bytes = self._hash_password(password)
            encoded_password = self._encode_password(salt, hash_bytes)
            
            # Create user document
            user_doc = {
                "username": username,
                "password": encoded_password,
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
            
            # Convert to user records without passwords
            users = []
            for user in results:
                users.append({
                    "id": str(user["_id"]),
                    "username": user["username"],
                    "role": user.get("role", "user"),
                    "active": user.get("active", True),
                    "created_at": user.get("created_at"),
                    "last_login": user.get("last_login")
                })
            
            return users

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
            
            return {
                "id": str(user["_id"]),
                "username": user["username"],
                "role": user.get("role", "user"),
                "active": user.get("active", True),
                "created_at": user.get("created_at"),
                "last_login": user.get("last_login")
            }
            
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
            
            return {
                "id": str(user["_id"]),
                "username": user["username"],
                "role": user.get("role", "user"),
                "active": user.get("active", True),
                "created_at": user.get("created_at"),
                "last_login": user.get("last_login")
            }

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
                # Invalidate all sessions for deactivated user
                user = await self.database.find_one(
                    self.users_collection_name,
                    {"_id": user_id_converted}
                )
                if user:
                    await self.database.delete_many(
                        self.sessions_collection_name,
                        {"user_id": user["_id"]}
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
            
            # Hash new password
            salt, hash_bytes = self._hash_password(new_password)
            encoded_password = self._encode_password(salt, hash_bytes)
            
            # Update password
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user["_id"]},
                {"$set": {"password": encoded_password}}
            )
            
            if result:
                # Invalidate all sessions for this user
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
