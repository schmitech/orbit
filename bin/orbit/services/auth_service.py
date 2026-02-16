"""
Authentication service for ORBIT CLI.

This service handles authentication token management, including secure storage
using keyring or file-based storage.
"""

import base64
import logging
from typing import Optional

from bin.orbit.services.config_service import DEFAULT_ENV_FILE
from bin.orbit.utils.exceptions import AuthenticationError

# Secure credential storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Keyring configuration
KEYRING_SERVICE = "orbit-cli"
KEYRING_TOKEN_KEY = "auth-token"
KEYRING_SERVER_KEY = "server-url"

logger = logging.getLogger(__name__)


class AuthService:
    """
    Service for managing authentication tokens.
    
    Handles secure storage and retrieval of authentication tokens using
    either system keychain (keyring) or file-based storage.
    """
    
    def __init__(self, config_service, server_url: str):
        """
        Initialize the auth service.
        
        Args:
            config_service: ConfigService instance for getting storage preferences
            server_url: Server URL for storing with token
        """
        self.config_service = config_service
        self.server_url = server_url
        self._legacy_warning_shown = False
        self._token: Optional[str] = None
    
    @property
    def token(self) -> Optional[str]:
        """Get the current authentication token."""
        if self._token is None:
            self._token = self.load_token()
        return self._token
    
    @token.setter
    def token(self, value: Optional[str]) -> None:
        """Set the authentication token."""
        self._token = value
    
    def save_token(self, token: str) -> None:
        """
        Save token securely using system keychain or file storage.
        
        Args:
            token: The authentication token to save
        """
        storage_method = self.config_service.get_auth_storage_method()
        
        if storage_method == 'file':
            self._save_token_to_file_plain(token)
            return
        
        # Try keyring if available and not explicitly disabled
        if KEYRING_AVAILABLE and storage_method == 'keyring':
            try:
                # Store token in system keychain
                keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, token)
                # Also store server URL for consistency
                keyring.set_password(KEYRING_SERVICE, KEYRING_SERVER_KEY, self.server_url)
                logger.debug("Saved authentication token to system keychain")
                
                # Clean up old plain text file if it exists
                if DEFAULT_ENV_FILE.exists():
                    try:
                        DEFAULT_ENV_FILE.unlink()
                        logger.debug("Removed legacy plain text token file")
                    except Exception as e:
                        logger.warning(f"Failed to remove legacy token file: {e}")
                
                return
            except Exception as e:
                logger.warning(f"Failed to save token to keychain: {e}")
                logger.info("Falling back to file storage")
        
        # Fallback to file-based storage (with improved security)
        self._save_token_to_file_fallback(token)
    
    def _save_token_to_file_plain(self, token: str) -> None:
        """Save token to file in plain text (less secure but visible)."""
        DEFAULT_ENV_FILE.parent.mkdir(exist_ok=True, mode=0o700)
        
        with open(DEFAULT_ENV_FILE, 'w') as f:
            f.write('# ORBIT CLI Configuration - Plain text storage\n')
            f.write('# Set auth.credential_storage: keyring in config.yaml for enhanced security\n')
            f.write(f'API_ADMIN_TOKEN={token}\n')
            f.write(f'API_SERVER_URL={self.server_url}\n')
        
        # Set secure permissions on the file
        DEFAULT_ENV_FILE.chmod(0o600)
        logger.debug("Saved authentication token to plain text file storage")
    
    def _save_token_to_file_fallback(self, token: str) -> None:
        """Fallback: Save token to file with improved security measures."""
        DEFAULT_ENV_FILE.parent.mkdir(exist_ok=True, mode=0o700)
        
        # Basic obfuscation - not encryption but better than plain text
        obfuscated_token = base64.b64encode(token.encode()).decode()
        obfuscated_url = base64.b64encode(self.server_url.encode()).decode()
        
        with open(DEFAULT_ENV_FILE, 'w') as f:
            f.write('# ORBIT CLI Configuration - Token is base64 encoded\n')
            f.write('# For security, consider installing the keyring library: pip install keyring\n')
            f.write(f'API_ADMIN_TOKEN_B64={obfuscated_token}\n')
            f.write(f'API_SERVER_URL_B64={obfuscated_url}\n')
        
        # Set secure permissions on the file
        DEFAULT_ENV_FILE.chmod(0o600)
        logger.debug("Saved authentication token to secure file storage")
        if not KEYRING_AVAILABLE:
            logger.warning("For enhanced security, install keyring: pip install keyring")
    
    def load_token(self, suppress_legacy_warning: bool = False) -> Optional[str]:
        """
        Load token securely from system keychain or fallback storage.
        
        Args:
            suppress_legacy_warning: If True, don't show legacy token warnings
            
        Returns:
            The authentication token if found, None otherwise
        """
        # Reset warning flag on each new token load attempt
        if not suppress_legacy_warning:
            self._legacy_warning_shown = False
        
        storage_method = self.config_service.get_auth_storage_method()
        
        if storage_method == 'file':
            return self._load_token_from_file()
        
        # Try keyring if available and not explicitly disabled
        if KEYRING_AVAILABLE and storage_method == 'keyring':
            token = self._load_token_from_keyring()
            if token:
                return token
        
        # Fallback to file-based storage
        return self._load_token_from_file(suppress_legacy_warning)
    
    def _load_token_from_keyring(self) -> Optional[str]:
        """Load token from system keychain."""
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
            if token:
                # Also try to get server URL
                server_url = keyring.get_password(KEYRING_SERVICE, KEYRING_SERVER_KEY)
                if server_url:
                    self.server_url = server_url
                logger.debug("Loaded authentication token from system keychain")
                return token
        except Exception as e:
            logger.warning(f"Failed to load token from keychain: {e}")
            logger.info("Falling back to file storage")
        return None
    
    def _load_token_from_file(self, suppress_legacy_warning: bool = False) -> Optional[str]:
        """Load token from file storage."""
        if not DEFAULT_ENV_FILE.exists():
            return None
        
        try:
            encoded_token = None
            encoded_url = None
            plain_token = None
            plain_url = None
            
            # Read file directly to find tokens
            with open(DEFAULT_ENV_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('API_ADMIN_TOKEN_B64='):
                        encoded_token = line.split('=', 1)[1]
                    elif line.startswith('API_SERVER_URL_B64='):
                        encoded_url = line.split('=', 1)[1]
                    elif line.startswith('API_ADMIN_TOKEN='):
                        plain_token = line.split('=', 1)[1]
                    elif line.startswith('API_SERVER_URL='):
                        plain_url = line.split('=', 1)[1]
            
            # Check for base64 encoded token (new format)
            if encoded_token:
                try:
                    token = base64.b64decode(encoded_token.encode()).decode()
                    if encoded_url:
                        self.server_url = base64.b64decode(encoded_url.encode()).decode()
                    logger.debug("Loaded authentication token from secure file storage")
                    return token
                except Exception as e:
                    logger.warning(f"Failed to decode token: {e}")
            
            # Fallback to old plain text format for backward compatibility
            if plain_token:
                if plain_url:
                    self.server_url = plain_url
                
                # Try to automatically migrate if this is a fresh load (not suppressed)
                if not suppress_legacy_warning:
                    self._migrate_legacy_token_if_needed(plain_token, plain_url)
                
                # Only show the warning if migration didn't happen and if not suppressed
                if not self._legacy_warning_shown and not suppress_legacy_warning:
                    if DEFAULT_ENV_FILE.exists():
                        logger.warning("Found legacy plain text token in ~/.orbit/.env")
                        if KEYRING_AVAILABLE:
                            logger.info("To migrate to secure storage: orbit config set auth.credential_storage keyring && orbit logout && orbit login")
                        else:
                            logger.info("For enhanced security: pip install keyring && orbit config set auth.credential_storage keyring && orbit logout && orbit login")
                    self._legacy_warning_shown = True
                
                return plain_token
                
        except Exception as e:
            logger.error(f"Failed to load token from file: {e}")
        
        return None
    
    def _migrate_legacy_token_if_needed(self, plain_token: str, plain_url: Optional[str]) -> None:
        """Automatically migrate from legacy plain text storage to secure storage if possible."""
        storage_method = self.config_service.get_auth_storage_method()
        
        # Check if keyring is available and we're not explicitly using file storage
        if KEYRING_AVAILABLE and storage_method != 'file':
            # Automatically migrate to keyring
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, plain_token)
                if plain_url:
                    keyring.set_password(KEYRING_SERVICE, KEYRING_SERVER_KEY, plain_url)
                
                # Remove the legacy file
                DEFAULT_ENV_FILE.unlink()
                
                logger.info("Automatically migrated from legacy plain text storage to secure keychain")
                return
            except Exception as e:
                logger.debug(f"Failed to migrate to keyring: {e}")
        
        # If we can't use keyring, migrate to base64 encoded file storage
        if storage_method != 'file':
            try:
                obfuscated_token = base64.b64encode(plain_token.encode()).decode()
                obfuscated_url = base64.b64encode((plain_url or self.server_url).encode()).decode()
                
                with open(DEFAULT_ENV_FILE, 'w') as f:
                    f.write('# ORBIT CLI Configuration - Token is base64 encoded\n')
                    f.write('# Migrated from legacy plain text storage\n')
                    f.write(f'API_ADMIN_TOKEN_B64={obfuscated_token}\n')
                    f.write(f'API_SERVER_URL_B64={obfuscated_url}\n')
                
                DEFAULT_ENV_FILE.chmod(0o600)
                logger.info("Automatically migrated from legacy plain text storage to base64 encoded storage")
                return
            except Exception as e:
                logger.debug(f"Failed to migrate to base64 storage: {e}")
    
    def clear_token(self) -> None:
        """Clear token from secure storage."""
        storage_method = self.config_service.get_auth_storage_method()
        
        if storage_method == 'keyring' and KEYRING_AVAILABLE:
            try:
                # Clear from system keychain
                keyring.delete_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
                keyring.delete_password(KEYRING_SERVICE, KEYRING_SERVER_KEY)
                logger.debug("Cleared authentication token from system keychain")
            except Exception as e:
                logger.warning(f"Failed to clear token from keychain: {e}")
        
        # Also clear file-based storage (both plain text and encoded)
        if DEFAULT_ENV_FILE.exists():
            try:
                DEFAULT_ENV_FILE.unlink()
                logger.debug("Cleared authentication token from file storage")
            except Exception as e:
                logger.warning(f"Failed to clear token file: {e}")
        
        self._token = None
    
    def ensure_authenticated(self) -> None:
        """Ensure user is authenticated before proceeding."""
        if not self.token:
            raise AuthenticationError("Authentication required. Please run 'orbit login' first.")

