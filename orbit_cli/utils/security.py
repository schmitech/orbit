"""Security utilities for token storage and management."""

import base64
import logging
from pathlib import Path
from typing import Optional, Tuple

from ..core.constants import (
    KEYRING_SERVICE,
    KEYRING_TOKEN_KEY,
    KEYRING_SERVER_KEY,
    DEFAULT_ENV_FILE
)
from ..core.exceptions import ConfigurationError

# Check if keyring is available
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages secure storage and retrieval of authentication tokens."""
    
    def __init__(self, storage_method: str = "auto"):
        """
        Initialize the token manager.
        
        Args:
            storage_method: Storage method ("keyring", "file", or "auto")
        """
        self.storage_method = storage_method
        self._legacy_warning_shown = False
    
    def save_token(self, token: str, server_url: str) -> None:
        """
        Save token securely using the configured storage method.
        
        Args:
            token: Authentication token
            server_url: Server URL
        """
        if self.storage_method == "file":
            self._save_token_to_file_plain(token, server_url)
        elif KEYRING_AVAILABLE and self.storage_method in ["keyring", "auto"]:
            try:
                self._save_token_to_keyring(token, server_url)
                self._cleanup_legacy_file()
            except Exception as e:
                logger.warning(f"Failed to save token to keychain: {e}")
                logger.info("Falling back to file storage")
                self._save_token_to_file_secure(token, server_url)
        else:
            self._save_token_to_file_secure(token, server_url)
    
    def load_token(self, suppress_legacy_warning: bool = False) -> Optional[Tuple[str, str]]:
        """
        Load token from secure storage.
        
        Args:
            suppress_legacy_warning: Whether to suppress legacy storage warnings
            
        Returns:
            Tuple of (token, server_url) if found, None otherwise
        """
        if not suppress_legacy_warning:
            self._legacy_warning_shown = False
        
        if self.storage_method == "file":
            return self._load_token_from_file()
        elif KEYRING_AVAILABLE and self.storage_method in ["keyring", "auto"]:
            # Try keyring first
            result = self._load_token_from_keyring()
            if result:
                return result
            # Fall back to file
            return self._load_token_from_file(suppress_legacy_warning)
        else:
            return self._load_token_from_file(suppress_legacy_warning)
    
    def clear_token(self) -> None:
        """Clear token from all storage locations."""
        # Clear from keyring if available
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
                keyring.delete_password(KEYRING_SERVICE, KEYRING_SERVER_KEY)
                logger.debug("Cleared authentication token from system keychain")
            except keyring.errors.PasswordDeleteError:
                logger.debug("No token found in keychain to clear")
            except Exception as e:
                logger.warning(f"Failed to clear token from keychain: {e}")
        
        # Clear file storage
        if DEFAULT_ENV_FILE.exists():
            try:
                DEFAULT_ENV_FILE.unlink()
                logger.debug("Cleared authentication token from file storage")
            except Exception as e:
                logger.warning(f"Failed to clear token file: {e}")
    
    def _save_token_to_keyring(self, token: str, server_url: str) -> None:
        """Save token to system keyring."""
        keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, token)
        keyring.set_password(KEYRING_SERVICE, KEYRING_SERVER_KEY, server_url)
        logger.debug("Saved authentication token to system keychain")
    
    def _save_token_to_file_plain(self, token: str, server_url: str) -> None:
        """Save token to file in plain text (less secure but visible)."""
        DEFAULT_ENV_FILE.parent.mkdir(exist_ok=True, mode=0o700)
        
        with open(DEFAULT_ENV_FILE, 'w') as f:
            f.write(f'# ORBIT CLI Configuration - Plain text storage\n')
            f.write(f'# Set auth.credential_storage: keyring in config for enhanced security\n')
            f.write(f'API_ADMIN_TOKEN={token}\n')
            f.write(f'API_SERVER_URL={server_url}\n')
        
        DEFAULT_ENV_FILE.chmod(0o600)
        logger.debug("Saved authentication token to plain text file storage")
    
    def _save_token_to_file_secure(self, token: str, server_url: str) -> None:
        """Save token to file with basic obfuscation."""
        DEFAULT_ENV_FILE.parent.mkdir(exist_ok=True, mode=0o700)
        
        # Basic obfuscation - not encryption but better than plain text
        obfuscated_token = base64.b64encode(token.encode()).decode()
        obfuscated_url = base64.b64encode(server_url.encode()).decode()
        
        with open(DEFAULT_ENV_FILE, 'w') as f:
            f.write(f'# ORBIT CLI Configuration - Token is base64 encoded\n')
            f.write(f'# For security, consider installing the keyring library: pip install keyring\n')
            f.write(f'API_ADMIN_TOKEN_B64={obfuscated_token}\n')
            f.write(f'API_SERVER_URL_B64={obfuscated_url}\n')
        
        DEFAULT_ENV_FILE.chmod(0o600)
        logger.debug("Saved authentication token to secure file storage")
    
    def _load_token_from_keyring(self) -> Optional[Tuple[str, str]]:
        """Load token from system keyring."""
        try:
            token = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
            if token:
                server_url = keyring.get_password(KEYRING_SERVICE, KEYRING_SERVER_KEY)
                logger.debug("Loaded authentication token from system keychain")
                return token, server_url
        except Exception as e:
            logger.warning(f"Failed to load token from keychain: {e}")
        return None
    
    def _load_token_from_file(self, suppress_legacy_warning: bool = False) -> Optional[Tuple[str, str]]:
        """Load token from file storage."""
        if not DEFAULT_ENV_FILE.exists():
            return None
        
        try:
            encoded_token = None
            encoded_url = None
            plain_token = None
            plain_url = None
            
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
            
            # Try base64 encoded format first
            if encoded_token:
                try:
                    token = base64.b64decode(encoded_token.encode()).decode()
                    server_url = base64.b64decode(encoded_url.encode()).decode() if encoded_url else None
                    logger.debug("Loaded authentication token from secure file storage")
                    return token, server_url
                except Exception as e:
                    logger.warning(f"Failed to decode token: {e}")
            
            # Fall back to plain text format
            if plain_token:
                if not self._legacy_warning_shown and not suppress_legacy_warning:
                    logger.warning("Found legacy plain text token in ~/.orbit/.env")
                    if KEYRING_AVAILABLE:
                        logger.info("To migrate to secure storage: orbit config set auth.credential_storage keyring && orbit logout && orbit login")
                    else:
                        logger.info("For enhanced security: pip install keyring && orbit config set auth.credential_storage keyring && orbit logout && orbit login")
                    self._legacy_warning_shown = True
                
                return plain_token, plain_url
                
        except Exception as e:
            logger.error(f"Failed to load token from file: {e}")
        
        return None
    
    def _cleanup_legacy_file(self) -> None:
        """Remove legacy plain text token file if it exists."""
        if DEFAULT_ENV_FILE.exists():
            try:
                DEFAULT_ENV_FILE.unlink()
                logger.debug("Removed legacy plain text token file")
            except Exception as e:
                logger.warning(f"Failed to remove legacy token file: {e}")
    
    def migrate_legacy_token(self) -> bool:
        """
        Attempt to migrate from legacy plain text storage to secure storage.
        
        Returns:
            True if migration successful, False otherwise
        """
        if not DEFAULT_ENV_FILE.exists():
            return False
        
        try:
            # Try to load plain text token
            plain_token = None
            plain_url = None
            
            with open(DEFAULT_ENV_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('API_ADMIN_TOKEN='):
                        plain_token = line.split('=', 1)[1]
                    elif line.startswith('API_SERVER_URL='):
                        plain_url = line.split('=', 1)[1]
            
            if not plain_token:
                return False
            
            # Save using secure method
            self.save_token(plain_token, plain_url or "")
            
            # Remove legacy file
            DEFAULT_ENV_FILE.unlink()
            
            logger.info("Successfully migrated from legacy plain text storage")
            return True
            
        except Exception as e:
            logger.debug(f"Failed to migrate legacy token: {e}")
            return False