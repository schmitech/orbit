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
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta, UTC

from services.database_service import (
    DatabaseService,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseDuplicateKeyError,
    DatabaseTimeoutError
)
from auth.rbac import is_valid_role, permissions_for_roles
from services.common_passwords import load_common_passwords

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
        self.password_policy = config.get('auth', {}).get('password_policy', {}) or {}
        self.account_lockout_policy = self.normalize_account_lockout_policy(
            config.get('auth', {}).get('account_lockout')
        )

        # External identity provider (OIDC) configuration - built in initialize()
        self._oidc = None
        self._oidc_enabled = False
        self._oidc_default_role = 'user'

        # User blacklist service - built in initialize()
        self.blacklist = None

        # External-identity allowlist (pre-clearing) - built in initialize()
        self.allowlist = None

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

        # Backfill `roles` for users created before multi-role support existed
        await self._backfill_roles()

        # Set up external identity providers (Entra ID, Auth0) if enabled
        self._initialize_oidc()

        # Pattern-based identity denial, evaluated on every authentication
        from services.user_blacklist_service import UserBlacklistService
        self.blacklist = UserBlacklistService(self.config, self.database)
        # Compound unique index, so a duplicate rule is rejected by the database
        # on every backend rather than only by add_rule's find_one pre-check,
        # which two concurrent creates can both pass. Declared here rather than
        # in each SQL backend's _indexes map because MongoDB never reads those.
        await self.database.create_index(
            self.blacklist.collection_name,
            [("entry_type", 1), ("pattern", 1)],
            unique=True,
        )

        # Pre-clearing of external identities. Same index rationale as above.
        from services.user_allowlist_service import UserAllowlistService
        self.allowlist = UserAllowlistService(self.config, self.database)
        await self.database.create_index(
            self.allowlist.collection_name,
            [("entry_type", 1), ("pattern", 1)],
            unique=True,
        )
        await self._report_allowlist_posture()

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

        # A default_role with any permission at all hands every external identity
        # admin-panel access at first login, which is rarely what's intended and
        # is a one-word change away from a wide-open panel. It can be deliberate,
        # so warn rather than refuse.
        from auth.rbac import permissions_for_roles
        if permissions_for_roles([self._oidc_default_role]):
            logger.warning(
                "auth.providers.default_role is %r, which carries admin-panel "
                "permissions: EVERY externally authenticated user will be granted "
                "them at first login. Use a role with no permissions (e.g. 'user') "
                "unless this is intended.",
                self._oidc_default_role,
            )

    async def _report_allowlist_posture(self) -> None:
        """Log what the allowlist mode means for the users already in the database.

        Enabling deny-by-default on a running deployment cuts off every external
        user no rule covers. An operator should learn that from a startup line
        naming the count, not from support tickets.
        """
        if not self._oidc_enabled or not self.allowlist:
            return

        if not self.allowlist.enforcing:
            logger.warning(
                "auth.providers.access_control is 'open': any identity an enabled "
                "provider authenticates is provisioned an ORBIT account. Set it to "
                "'allowlist' to require pre-clearing."
            )
            return

        try:
            external = [
                u for u in await self.database.find_many(
                    self.users_collection_name, {}, limit=10000
                )
                if u.get("provider")
            ]
            denied = [
                u for u in external
                if not await self.allowlist.is_user_cleared(u)
            ]
        except Exception as e:
            logger.warning(f"Could not evaluate allowlist coverage at startup: {str(e)}")
            return

        if denied:
            logger.warning(
                "Identity allowlist is enforcing: %d of %d existing external users "
                "match no rule and can no longer sign in. Run 'orbit user allowlist "
                "seed-from-existing' to grandfather them, or add rules for the ones "
                "that should keep access.",
                len(denied), len(external),
            )
        else:
            logger.info(
                "Identity allowlist is enforcing (%d existing external users, all cleared)",
                len(external),
            )

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
    def normalize_password_policy(
        cls, policy: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Return the public, type-normalized form of a password policy."""
        policy = policy or {}
        min_length = policy.get("min_length", cls.PASSWORD_MIN_LENGTH)
        max_length = policy.get("max_length", cls.PASSWORD_MAX_LENGTH)
        try:
            min_length = min(cls.PASSWORD_MAX_LENGTH, max(1, int(min_length)))
            max_length = min(
                cls.PASSWORD_MAX_LENGTH, max(min_length, int(max_length))
            )
        except (TypeError, ValueError):
            min_length = cls.PASSWORD_MIN_LENGTH
            max_length = cls.PASSWORD_MAX_LENGTH

        def enabled(name: str) -> bool:
            value = policy.get(name, False)
            return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}

        return {
            "min_length": min_length,
            "max_length": max_length,
            "require_uppercase": enabled("require_uppercase"),
            "require_lowercase": enabled("require_lowercase"),
            "require_digit": enabled("require_digit"),
            "require_symbol": enabled("require_symbol"),
            "reject_common_passwords": enabled("reject_common_passwords"),
        }

    @classmethod
    def validate_password(
        cls, password: str, policy: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Validate a password, applying an optional configured complexity policy."""
        if password is None:
            return "Password is required"

        policy = cls.normalize_password_policy(policy)
        min_length = policy["min_length"]
        max_length = policy["max_length"]
        errors = []
        if len(password) < min_length:
            errors.append(f"Password must be at least {min_length} characters")
        if len(password) > max_length:
            errors.append(f"Password must be at most {max_length} characters")
        if any(ch.isspace() for ch in password):
            errors.append("Password cannot contain spaces or other whitespace")

        if policy["require_uppercase"] and not any(ch.isupper() for ch in password):
            errors.append("Password must include an uppercase letter")
        if policy["require_lowercase"] and not any(ch.islower() for ch in password):
            errors.append("Password must include a lowercase letter")
        if policy["require_digit"] and not any(ch.isdigit() for ch in password):
            errors.append("Password must include a digit")
        if policy["require_symbol"] and not any(not ch.isalnum() for ch in password):
            errors.append("Password must include a symbol")
        if policy["reject_common_passwords"] and password.casefold() in load_common_passwords():
            errors.append("Password is too common")

        return "; ".join(errors) if errors else None
    
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
    def normalize_account_lockout_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a safe, type-normalized account-lockout policy.

        Lockout is deliberately disabled when the configuration block is absent,
        preserving the behavior of deployments that have not opted in.
        """
        policy = policy if isinstance(policy, dict) else {}

        def positive_int(name: str, default: int) -> int:
            try:
                return max(1, int(policy.get(name, default)))
            except (TypeError, ValueError):
                return default

        def non_negative_int(name: str, default: int) -> int:
            try:
                return max(0, int(policy.get(name, default)))
            except (TypeError, ValueError):
                return default

        enabled = policy.get("enabled", False)
        return {
            "enabled": enabled is True or str(enabled).strip().lower() in {"1", "true", "yes", "on"},
            "max_failed_attempts": positive_int("max_failed_attempts", 5),
            "lockout_duration_minutes": non_negative_int("lockout_duration_minutes", 15),
            "reset_counter_after_minutes": non_negative_int("reset_counter_after_minutes", 30),
        }

    @staticmethod
    def _as_utc_datetime(value: Any) -> Optional[datetime]:
        """Parse database timestamps from all supported storage backends."""
        if isinstance(value, datetime):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
            except ValueError:
                return None
        return None

    def _is_account_locked(self, user: Dict[str, Any], now: datetime) -> bool:
        """Return whether an active durable lockout applies to this local user."""
        if not self.account_lockout_policy["enabled"] or user.get("provider"):
            return False
        locked_until = self._as_utc_datetime(user.get("locked_until"))
        return bool(locked_until and locked_until > now)

    async def _record_failed_login(self, user: Dict[str, Any], now: datetime) -> None:
        """Persist a failed local-password attempt and lock the account if needed."""
        if not self.account_lockout_policy["enabled"] or user.get("provider"):
            return

        policy = self.account_lockout_policy
        updated = await self.database.record_failed_login_attempt(
            self.users_collection_name,
            user["_id"],
            now,
            now - timedelta(minutes=policy["reset_counter_after_minutes"]),
            policy["max_failed_attempts"],
            now + timedelta(minutes=policy["lockout_duration_minutes"]),
        )
        if not updated:
            logger.error("Could not record failed login for local user: %s", user["username"])

    async def _reset_failed_logins(self, user: Dict[str, Any]) -> None:
        """Clear durable lockout state after a successful local-password login."""
        if not self.account_lockout_policy["enabled"] or user.get("provider"):
            return
        await self.database.update_one(
            self.users_collection_name,
            {"_id": user["_id"]},
            {"$set": {
                "failed_login_attempts": 0,
                "last_failed_login_at": None,
                "locked_until": None,
            }},
        )

    @staticmethod
    def _resolve_roles(user: Dict[str, Any]) -> List[str]:
        """Resolve a user's role list, falling back to the legacy single `role` field."""
        roles = user.get("roles")
        if roles:
            return list(roles)
        return [user.get("role", "user")]

    @staticmethod
    def _user_info(user: Dict[str, Any]) -> Dict[str, Any]:
        """Build the auth-context user dict (no password, no timestamps)."""
        roles = AuthService._resolve_roles(user)
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user.get("email"),
            "role": user.get("role", "user"),
            "roles": roles,
            "permissions": sorted(permissions_for_roles(roles)),
            "active": user.get("active", True),
            "provider": user.get("provider"),
        }

    @staticmethod
    def _user_record(user: Dict[str, Any]) -> Dict[str, Any]:
        """Build the full user record dict (no password)."""
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "role": user.get("role", "user"),
            "roles": AuthService._resolve_roles(user),
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
                password_error = self.validate_password(
                    self.default_admin_password, self.password_policy
                )
                if password_error:
                    raise ValueError(
                        "Default admin password does not satisfy auth.password_policy: "
                        f"{password_error}"
                    )

                # Create default admin user
                user_doc = {
                    "username": self.default_admin_username,
                    "password": self._hash_and_encode(self.default_admin_password),
                    "role": "admin",
                    "roles": ["admin"],
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

    async def _backfill_roles(self) -> None:
        """One-time migration: assign `roles = [role]` to any user created before
        multi-role support existed. Idempotent - only touches users missing `roles`."""
        try:
            users = await self.database.find_many(self.users_collection_name, {}, limit=10_000)
            for user in users:
                if user.get("roles"):
                    continue
                role = user.get("role", "user")
                await self.database.update_one(
                    self.users_collection_name,
                    {"_id": user["_id"]},
                    {"$set": {"roles": [role]}}
                )
                logger.info(f"Backfilled roles for user {user.get('username')}: [{role}]")
        except Exception as e:
            logger.error(f"Unexpected error backfilling user roles: {str(e)}")

    async def _is_blacklisted(self, user: Dict[str, Any]) -> bool:
        """Return whether a resolved user matches an active blacklist rule.

        Evaluated at every point that turns a credential into an identity, so a
        blocked user cannot authenticate through any surface. Errors inside the
        blacklist service are already swallowed there (falling back to the last
        known rule set); this wrapper only guards the not-yet-initialized case.
        """
        if not self.blacklist or not user:
            return False
        rule = await self.blacklist.match_user(user)
        if rule:
            logger.warning(
                f"Blocked blacklisted user {user.get('username')} "
                f"(rule: {rule.get('entry_type')}={rule.get('pattern')})"
            )
            return True
        return False

    async def _is_cleared(self, user: Dict[str, Any]) -> bool:
        """Return whether an external user is pre-cleared by the identity allowlist.

        Local password users carry no ``provider`` and are never gated, so the
        bootstrap admin can always sign in no matter what rules exist. Returns
        True when the allowlist isn't initialized yet, matching the blacklist
        wrapper's handling of that case.
        """
        if not self.allowlist or not user:
            return True
        if await self.allowlist.is_user_cleared(user):
            return True
        logger.warning(
            f"Denied external user {user.get('username')}: not on the identity allowlist"
        )
        return False

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

            # Password verification surfaces, including WebSocket HTTP Basic
            # authentication, must enforce the same local-account state.
            if user.get("provider"):
                return False, None

            now = datetime.now(UTC)
            if self._is_account_locked(user, now):
                logger.warning(f"Credential check for locked user: {username}")
                return False, None

            if not self._verify_password(password, user["password"]):
                await self._record_failed_login(user, now)
                return False, None

            if await self._is_blacklisted(user):
                return False, None

            await self._reset_failed_logins(user)

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

            now = datetime.now(UTC)
            # Check durable lockout before paying the PBKDF2 cost. The route
            # deliberately returns the same generic credential error here.
            if self._is_account_locked(user, now):
                logger.warning(f"Login attempt for locked user: {username}")
                return False, None, None

            # Verify password
            if not self._verify_password(password, user["password"]):
                logger.warning(f"Invalid password for user: {username}")
                await self._record_failed_login(user, now)
                return False, None, None

            if await self._is_blacklisted(user):
                return False, None, None

            await self._reset_failed_logins(user)

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
        """Set a user's single role. Used to promote allowlisted SSO users to admin."""
        return await self.set_roles(user_id, [role])

    async def set_roles(self, user_id: str, roles: List[str]) -> bool:
        """Set a user's role list. The first role is also stored as the legacy
        `role` field for display/backward compatibility."""
        if not roles or any(not is_valid_role(role) for role in roles):
            logger.warning(f"Rejected set_roles for invalid roles: {roles}")
            return False
        try:
            user_id_converted = await self.database.ensure_id_is_object_id(user_id)
            result = await self.database.update_one(
                self.users_collection_name,
                {"_id": user_id_converted},
                {"$set": {"role": roles[0], "roles": list(roles)}}
            )
            return bool(result)
        except (DatabaseConnectionError, DatabaseTimeoutError) as e:
            logger.error(f"Database connection error setting roles for {user_id}: {str(e)}")
            return False
        except (DatabaseOperationError, DatabaseDuplicateKeyError) as e:
            logger.error(f"Database operation error setting roles for {user_id}: {str(e)}")
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
            # Hardcoded, not auth.providers.default_role: this is the inference-surface
            # JIT-provisioning path (chat/files/voice/A2A clients like orbitchat), which
            # must never grant more than baseline access no matter how default_role is
            # configured. Admin-panel access is a separate path (provision_sso_user)
            # gated by the admin_users allowlist.
            user = await self._find_or_create_external_user(
                claims["provider"], claims["external_id"], claims.get("email"), role="user"
            )
            if not user or not user.get("active", True):
                return False, None
            if await self._is_blacklisted(user):
                return False, None
            # Re-checked per request, not just at provisioning: removing an
            # allowlist rule must deny an already-provisioned user, and does so
            # within the rule cache's TTL.
            if not await self._is_cleared(user):
                return False, None
            # Cap the *effective* role for this surface too, not just at creation:
            # an identity that already holds an elevated role (e.g. an admin
            # provisioned via provision_sso_user, or provisioned before this
            # guardrail existed under a misconfigured default_role) must still
            # only get baseline access when authenticating as a chat/API client.
            # Their stored role is untouched - admin-panel logins are unaffected.
            return True, self._user_info({**user, "role": "user", "roles": ["user"]})

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

            if await self._is_blacklisted(user):
                return False, None

            # Also enforced on this branch, not just the JWT one. An admin-SSO
            # login mints an *opaque* session, so a callback still in flight when
            # a rule is removed - or one served by a worker whose rule cache is
            # stale - can create a session after _revoke_uncleared has run. Only
            # a per-request check makes rule removal reliable for those.
            if not await self._is_cleared(user):
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
            password_error = self.validate_password(new_password, self.password_policy)
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
    
    async def create_user(
        self, username: str, password: str, role: str = "user", roles: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Create a new user

        Args:
            username: The username
            password: The password
            role: The user's primary role (default: user), stored for display/backward compat
            roles: The full list of roles to assign. Defaults to [role] when omitted.

        Returns:
            The new user's ID if successful, None otherwise
        """
        try:
            username_error = self.validate_username(username)
            if username_error:
                logger.warning(f"Rejected user creation for invalid username: {username_error}")
                return None

            password_error = self.validate_password(password, self.password_policy)
            if password_error:
                logger.warning(f"Rejected user creation for invalid password: {password_error}")
                return None

            assigned_roles = list(roles) if roles else [role]
            if not assigned_roles or any(not is_valid_role(r) for r in assigned_roles):
                logger.warning(f"Rejected user creation for invalid roles: {assigned_roles}")
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
                "role": assigned_roles[0],
                "roles": assigned_roles,
                "active": True,
                "created_at": datetime.now(UTC),
                "last_login": None
            }

            # Insert user
            user_id = await self.database.insert_one(self.users_collection_name, user_doc)

            logger.debug(f"Created new user: {username} with roles: {assigned_roles}")

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
                # Backfill email if it was missing at creation (e.g. the provider
                # didn't supply a claim yet, or email_claim was configured later).
                if email and not user.get("email"):
                    await self.database.update_one(
                        self.users_collection_name,
                        {"_id": user["_id"]},
                        {"$set": {"email": email}}
                    )
                    user["email"] = email
                return user

            # Refuse to provision a blacklisted identity at all, so a blocked
            # external user never gains a row in the users table. The user_id
            # dimension can't apply here - there is no id until insert.
            if self.blacklist and await self.blacklist.match_identity(
                email=email, username=username
            ):
                logger.warning(
                    f"Refused to provision blacklisted external user: {username}"
                )
                return None

            # Pre-clearing: under `access_control: allowlist` an unknown subject
            # gets no row at all, so an identity the operator never approved
            # never becomes an ORBIT user on any surface. Evaluated after the
            # blacklist so a deny rule always wins.
            if self.allowlist and not await self.allowlist.is_cleared(
                email=email, username=username
            ):
                logger.warning(
                    f"Refused to provision external user not on the identity "
                    f"allowlist: {username} (email={email!r})"
                )
                return None

            user_doc = {
                "username": username,
                "password": self._hash_and_encode(secrets.token_hex(32)),
                "role": create_role,
                "roles": [create_role],
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
                logger.debug(f"Provisioned external user: {username} (provider={provider})")
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
        the allowlist. When ``is_admin`` is False, any existing user's roles are
        left untouched (a non-allowlisted identity's admin-panel permissions are
        managed entirely via manual role assignment, not by this method).
        Returns the user document (including ``_id``) or None.
        """
        role = "admin" if is_admin else self._oidc_default_role
        user = await self._find_or_create_external_user(provider, external_id, email, role=role)
        if not user:
            return None

        # Promote an existing (previously non-admin) user now on the allowlist.
        if is_admin and user.get("role") != "admin":
            if await self.set_role(str(user["_id"]), "admin"):
                user["role"] = "admin"
                user["roles"] = ["admin"]
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
            password_error = self.validate_password(new_password, self.password_policy)
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

            # External users have no local password to reset
            if user.get("provider"):
                logger.warning(f"Password reset attempt for external user: {user['username']}")
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
