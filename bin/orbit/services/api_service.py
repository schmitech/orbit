"""
API service that provides high-level methods for interacting with the ORBIT server API.

This service wraps the ApiClient and AuthService to provide convenient methods
for all API operations.
"""

from datetime import datetime, timedelta, UTC
from typing import Any, Optional
import requests

from bin.orbit.services.api_client import ApiClient, handle_api_errors
from bin.orbit.services.auth_service import AuthService
from bin.orbit.utils.exceptions import AuthenticationError, OrbitError, NetworkError


class ApiService:
    """
    High-level API service for ORBIT server operations.
    
    This service provides convenient methods for all API operations,
    handling authentication automatically.
    """
    
    def __init__(self, api_client: ApiClient, auth_service: AuthService):
        """
        Initialize the API service.
        
        Args:
            api_client: HTTP client for making requests
            auth_service: Authentication service for token management
        """
        self.api_client = api_client
        self.auth_service = auth_service
    
    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        self.auth_service.ensure_authenticated()
        return {"Authorization": f"Bearer {self.auth_service.token}"}
    
    # Authentication methods
    @handle_api_errors(operation_name="Login", custom_errors={
        401: "Invalid username or password",
        400: "Invalid login request"
    })
    def login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate a user and return a bearer token."""
        data = {"username": username, "password": password}
        response = self.api_client.post("/auth/login", json_data=data)
        response.raise_for_status()
        result = response.json()
        
        if "token" in result:
            self.auth_service.token = result["token"]
            self.auth_service.save_token(result["token"])
        
        return result
    
    def logout(self) -> dict[str, Any]:
        """Logout the current user."""
        if not self.auth_service.token:
            return {"message": "Not logged in"}
        
        try:
            headers = self._get_auth_headers()
            response = self.api_client.post("/auth/logout", headers=headers)
            response.raise_for_status()
            result = response.json()
        except Exception:
            result = {"message": "Logged out locally"}
        finally:
            self.auth_service.token = None
            self.auth_service.clear_token()
        
        return result
    
    @handle_api_errors(operation_name="User registration", custom_errors={
        403: "Admin privileges required to register users",
        409: "User already exists"
    })
    def register_user(self, username: str, password: str, role: str = "user",
                       roles: list[str] | None = None) -> dict[str, Any]:
        """Register a new user (users.manage permission required)."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"username": username, "password": password, "role": role}
        if roles:
            data["roles"] = roles
        response = self.api_client.post("/auth/register", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="List roles", custom_errors={
        403: "users.manage permission required to list roles"
    })
    def list_roles(self) -> list[str]:
        """List all registered roles."""
        headers = self._get_auth_headers()
        response = self.api_client.get("/auth/roles", headers=headers)
        response.raise_for_status()
        return response.json().get("roles", [])

    @handle_api_errors(operation_name="Set user roles", custom_errors={
        403: "users.manage permission required to assign roles",
        404: "User not found"
    })
    def set_user_roles(self, user_id: str, roles: list[str]) -> dict[str, Any]:
        """Replace a user's role assignment."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        response = self.api_client.put(
            f"/auth/users/{user_id}/roles", headers=headers, json_data={"roles": roles}
        )
        response.raise_for_status()
        return response.json()
    
    @handle_api_errors(operation_name="Get current user", custom_errors={
        401: "Invalid or expired token"
    })
    def get_current_user(self) -> dict[str, Any]:
        """Get information about the currently authenticated user."""
        headers = self._get_auth_headers()
        response = self.api_client.get("/auth/me", headers=headers)
        response.raise_for_status()
        return response.json()
    
    # Identity allowlist (pre-clearing external Entra/Auth0 logins)
    @handle_api_errors(operation_name="List allowlist rules", custom_errors={
        403: "users.manage permission required to manage the identity allowlist"
    })
    def list_allowlist_rules(self) -> list[dict[str, Any]]:
        """List every identity allowlist rule, newest first."""
        headers = self._get_auth_headers()
        response = self.api_client.get("/auth/allowlist", headers=headers)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Add allowlist rule", custom_errors={
        403: "users.manage permission required to manage the identity allowlist",
        400: "Invalid or duplicate allowlist rule"
    })
    def add_allowlist_rule(self, pattern: str, entry_type: str,
                           reason: str | None = None) -> dict[str, Any]:
        """Pre-clear an identity pattern for external login."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        response = self.api_client.post(
            "/auth/allowlist", headers=headers,
            json_data={"pattern": pattern, "entry_type": entry_type, "reason": reason},
        )
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Remove allowlist rule", custom_errors={
        403: "users.manage permission required to manage the identity allowlist",
        404: "Allowlist rule not found",
        400: "This change would revoke your own access"
    })
    def delete_allowlist_rule(self, rule_id: str) -> dict[str, Any]:
        """Remove an allowlist rule, revoking the sessions it was clearing."""
        headers = self._get_auth_headers()
        response = self.api_client.delete(f"/auth/allowlist/{rule_id}", headers=headers)
        response.raise_for_status()
        return response.json()

    # Admin IP allowlist (restricting /admin and admin-scoped /auth routes to
    # configured IP/CIDR ranges)
    @handle_api_errors(operation_name="List admin IP rules", custom_errors={
        403: "users.manage permission required to manage the admin IP allowlist"
    })
    def list_admin_ip_rules(self) -> list[dict[str, Any]]:
        """List every admin IP allowlist rule, newest first."""
        headers = self._get_auth_headers()
        response = self.api_client.get("/auth/admin-ip-rules", headers=headers)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Add admin IP rule", custom_errors={
        403: "users.manage permission required to manage the admin IP allowlist",
        400: "Invalid or duplicate admin IP rule"
    })
    def add_admin_ip_rule(self, cidr: str, reason: str | None = None) -> dict[str, Any]:
        """Allow an IP address/CIDR range to reach the admin interface."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        response = self.api_client.post(
            "/auth/admin-ip-rules", headers=headers,
            json_data={"cidr": cidr, "reason": reason},
        )
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Remove admin IP rule", custom_errors={
        403: "users.manage permission required to manage the admin IP allowlist",
        404: "Admin IP rule not found",
        400: "This change would exclude your own current IP"
    })
    def delete_admin_ip_rule(self, rule_id: str, force: bool = False) -> dict[str, Any]:
        """Remove an admin IP allowlist rule."""
        headers = self._get_auth_headers()
        endpoint = f"/auth/admin-ip-rules/{rule_id}"
        if force:
            endpoint += "?force=true"
        response = self.api_client.delete(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()

    # User management
    @handle_api_errors(operation_name="List users", custom_errors={
        403: "Admin privileges required to list users"
    })
    def list_users(self, role: str | None = None, active_only: bool = False,
                   limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List all users in the system."""
        headers = self._get_auth_headers()
        params = {}
        if role:
            params['role'] = role
        if active_only:
            params['active_only'] = 'true'
        if limit != 100:
            params['limit'] = str(limit)
        if offset != 0:
            params['offset'] = str(offset)
        
        response = self.api_client.get("/auth/users", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    
    def reset_user_password(self, user_id: str, new_password: str) -> dict[str, Any]:
        """Reset a user's password (admin only)."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"user_id": user_id, "new_password": new_password}
        response = self.api_client.post("/auth/reset-password", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()

    def get_password_policy(self) -> dict[str, Any]:
        """Return the active local-password policy for an authenticated user."""
        headers = self._get_auth_headers()
        response = self.api_client.get("/auth/password-policy", headers=headers)
        response.raise_for_status()
        return response.json()
    
    @handle_api_errors(operation_name="Find user by username", custom_errors={
        403: "Admin privileges required",
        404: "User not found"
    })
    def find_user_id_by_username(self, username: str) -> str:
        """Find a user's ID by their username."""
        headers = self._get_auth_headers()
        params = {"username": username}
        response = self.api_client.get("/auth/users/by-username", headers=headers, params=params)
        response.raise_for_status()
        user_data = response.json()
        return user_data.get('id')
    
    @handle_api_errors(operation_name="Delete user", custom_errors={
        403: "Admin privileges required",
        404: "User not found",
        400: "Cannot delete your own account"
    })
    def delete_user(self, user_id: str) -> dict[str, Any]:
        """Delete a user."""
        headers = self._get_auth_headers()
        response = self.api_client.delete(f"/auth/users/{user_id}", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def change_password(self, current_password: str, new_password: str) -> dict[str, Any]:
        """Change the current user's password."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"current_password": current_password, "new_password": new_password}
        response = self.api_client.post("/auth/change-password", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()
    
    def deactivate_user(self, user_id: str) -> dict[str, Any]:
        """Deactivate a user."""
        headers = self._get_auth_headers()
        response = self.api_client.post(f"/auth/users/{user_id}/deactivate", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def activate_user(self, user_id: str) -> dict[str, Any]:
        """Activate a user."""
        headers = self._get_auth_headers()
        response = self.api_client.post(f"/auth/users/{user_id}/activate", headers=headers)
        response.raise_for_status()
        return response.json()
    
    # API Key methods
    def create_api_key(self, client_name: str, notes: str | None = None,
                      prompt_id: str | None = None, prompt_name: str | None = None,
                      prompt_file: str | None = None, adapter_name: str | None = None,
                      prompt_text: str | None = None,
                      notes_file: str | None = None,
                      expires_in_days: int | None = None,
                      non_expiring: bool = False,
                      expiration_justification: str | None = None) -> dict[str, Any]:
        """Create a new API key."""
        # Resolve notes input.
        # Priority: notes > notes_file
        resolved_notes = notes
        if not resolved_notes and notes_file:
            resolved_notes = self.api_client.read_file_content(notes_file)

        # Handle prompt if needed
        # Priority: prompt_text > prompt_file
        if prompt_text and (prompt_name or prompt_id):
            # Use prompt text directly
            if prompt_id:
                self.update_prompt(prompt_id, prompt_text)
            elif prompt_name:
                prompt_result = self.create_prompt(prompt_name, prompt_text)
                prompt_id = prompt_result.get("id")
        elif prompt_file and (prompt_name or prompt_id):
            # Read prompt from file
            prompt_text_from_file = self.api_client.read_file_content(prompt_file)
            if prompt_id:
                self.update_prompt(prompt_id, prompt_text_from_file)
            elif prompt_name:
                prompt_result = self.create_prompt(prompt_name, prompt_text_from_file)
                prompt_id = prompt_result.get("id")
        
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"client_name": client_name}
        if adapter_name:
            data["adapter_name"] = adapter_name
        if resolved_notes:
            data["notes"] = resolved_notes
        if prompt_id:
            data["system_prompt_id"] = prompt_id
        if expires_in_days is not None:
            expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
            data["expires_at"] = expires_at.isoformat()
        if non_expiring:
            data["non_expiring"] = True
        if expiration_justification:
            data["expiration_justification"] = expiration_justification

        try:
            response = self.api_client.post("/admin/api-keys", headers=headers, json_data=data)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            detail = e.response.text
            try:
                detail = e.response.json().get("detail", detail)
            except Exception:
                pass
            raise OrbitError(f"{e.response.status_code} {detail}")

        api_key_result = response.json()
        
        return api_key_result
    
    def list_api_keys(self, active_only: bool = False, limit: int = 100, offset: int = 0,
                       expired_only: bool = False, expiring_within_days: int | None = None) -> list[dict[str, Any]]:
        """List all API keys, optionally filtered to expired or soon-to-expire keys.

        expired_only and expiring_within_days are applied client-side against the
        expires_at/expired fields the server already returns per key. Since the
        server paginates before this filter is applied, a filtered request walks
        every server page first so a key past the first `limit` records is never
        silently dropped; `limit`/`offset` are then applied to the *filtered*
        result, matching the semantics an unfiltered request gets directly from
        the server.
        """
        headers = self._get_auth_headers()
        filtering = expired_only or expiring_within_days is not None

        def _fetch_page(page_limit: int, page_offset: int) -> list[dict[str, Any]]:
            params = {'limit': str(page_limit), 'offset': str(page_offset)}
            if active_only:
                params['active_only'] = 'true'
            response = self.api_client.get("/admin/api-keys", headers=headers, params=params)
            response.raise_for_status()
            return response.json()

        if not filtering:
            keys = _fetch_page(limit, offset)
        else:
            page_size = 1000
            keys = []
            page_offset = 0
            while True:
                page = _fetch_page(page_size, page_offset)
                keys.extend(page)
                if len(page) < page_size:
                    break
                page_offset += page_size

            if expired_only:
                keys = [k for k in keys if k.get('expired')]
            else:
                keys = [
                    k for k in keys
                    if not k.get('expired') and k.get('days_remaining') is not None
                    and k['days_remaining'] <= expiring_within_days
                ]
            keys = keys[offset:offset + limit]

        return keys

    @handle_api_errors(operation_name="Renew API key")
    def renew_api_key(self, api_key_id: str, expires_in_days: int | None = None,
                       non_expiring: bool = False, expiration_justification: str | None = None) -> dict[str, Any]:
        """Renew an API key's expiration, or grant an approved non-expiring exception."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data: dict[str, Any] = {}
        if expires_in_days is not None:
            expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
            data["expires_at"] = expires_at.isoformat()
        if non_expiring:
            data["non_expiring"] = True
        if expiration_justification:
            data["expiration_justification"] = expiration_justification

        response = self.api_client.post(f"/admin/api-keys/{api_key_id}/renew", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()
    
    @handle_api_errors(operation_name="Rename API key", custom_errors={
        404: "Old API key not found",
        409: "New API key already exists"
    })
    def rename_api_key(self, old_api_key: str, new_api_key: str) -> dict[str, Any]:
        """Rename an API key."""
        headers = self._get_auth_headers()
        params = {"new_api_key": new_api_key}
        response = self.api_client.patch(f"/admin/api-keys/{old_api_key}/rename", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    
    @handle_api_errors(operation_name="Deactivate API key")
    def deactivate_api_key(self, api_key: str) -> dict[str, Any]:
        """Deactivate an API key."""
        headers = self._get_auth_headers()
        response = self.api_client.post(f"/admin/api-keys/{api_key}/deactivate", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def delete_api_key(self, api_key: str) -> dict[str, Any]:
        """Delete an API key."""
        headers = self._get_auth_headers()
        response = self.api_client.delete(f"/admin/api-keys/{api_key}", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def get_api_key_status(self, api_key: str) -> dict[str, Any]:
        """Get the status of an API key."""
        headers = self._get_auth_headers()
        response = self.api_client.get(f"/admin/api-keys/{api_key}/status", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def test_api_key(self, api_key: str) -> dict[str, Any]:
        """Test an API key."""
        if not api_key or len(api_key) < 10:
            return {"status": "error", "error": "API key format is invalid"}
        
        headers = {"X-API-Key": api_key}
        try:
            response = self.api_client.get("/health", headers=headers, retry=False)
            if response.status_code == 401:
                return {"status": "error", "error": "API key is invalid or deactivated"}
            elif response.status_code == 403:
                return {"status": "error", "error": "API key is valid but access forbidden"}
            
            response.raise_for_status()
            # Try to get status to verify
            try:
                self.get_api_key_status(api_key)
                return {"status": "success", "message": "API key is valid and active"}
            except Exception:
                return {"status": "error", "error": "API key is invalid or deactivated"}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return {"status": "error", "error": "API key is invalid or deactivated"}
            elif e.response.status_code == 403:
                return {"status": "error", "error": "API key is valid but access forbidden"}
            raise OrbitError(f"API key test failed: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"API key test failed: {e!s}")
    
    # System Prompt methods
    def create_prompt(self, name: str, prompt_text: str, version: str = "1.0") -> dict[str, Any]:
        """Create a new system prompt."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"name": name, "prompt": prompt_text, "version": version}
        response = self.api_client.post("/admin/prompts", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()
    
    def list_prompts(self, name_filter: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List all system prompts."""
        headers = self._get_auth_headers()
        params = {}
        if name_filter:
            params['name_filter'] = name_filter
        if limit != 100:
            params['limit'] = str(limit)
        if offset != 0:
            params['offset'] = str(offset)
        
        response = self.api_client.get("/admin/prompts", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_prompt(self, prompt_id: str) -> dict[str, Any]:
        """Get a system prompt by its ID."""
        headers = self._get_auth_headers()
        response = self.api_client.get(f"/admin/prompts/{prompt_id}", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def update_prompt(self, prompt_id: str, prompt_text: str, version: str | None = None) -> dict[str, Any]:
        """Update an existing system prompt."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"prompt": prompt_text}
        if version:
            data["version"] = version
        response = self.api_client.put(f"/admin/prompts/{prompt_id}", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()
    
    def delete_prompt(self, prompt_id: str) -> dict[str, Any]:
        """Delete a system prompt."""
        headers = self._get_auth_headers()
        response = self.api_client.delete(f"/admin/prompts/{prompt_id}", headers=headers)
        response.raise_for_status()
        return response.json()
    
    def associate_prompt_with_api_key(self, api_key: str, prompt_id: str) -> dict[str, Any]:
        """Associate a system prompt with an API key."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        data = {"prompt_id": prompt_id}
        response = self.api_client.post(f"/admin/api-keys/{api_key}/prompt", headers=headers, json_data=data)
        response.raise_for_status()
        return response.json()
    
    # Admin operations
    @handle_api_errors(operation_name="Reload adapters", custom_errors={
        404: "Adapter not found or is disabled in configuration",
        503: "Adapter manager is not available"
    })
    def reload_adapters(self, adapter_name: str | None = None) -> dict[str, Any]:
        """Reload adapter configurations from adapters.yaml without server restart."""
        headers = self._get_auth_headers()
        params = {}
        if adapter_name:
            params['adapter_name'] = adapter_name

        response = self.api_client.post("/admin/reload-adapters", headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Reload templates", custom_errors={
        404: "Adapter not found or does not support template reloading",
        503: "Adapter manager is not available"
    })
    def reload_templates(self, adapter_name: str | None = None) -> dict[str, Any]:
        """Reload intent templates from template library files without server restart."""
        headers = self._get_auth_headers()
        params = {}
        if adapter_name:
            params['adapter_name'] = adapter_name

        response = self.api_client.post("/admin/reload-templates", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    
    def check_auth_status(self) -> dict[str, Any]:
        """Check authentication status."""
        storage_method = self.auth_service.config_service.get_auth_storage_method()
        auth_enabled = True  # Always enabled in server
        
        # Check keyring availability
        try:
            import keyring  # noqa: F401
            keyring_available = True
        except ImportError:
            keyring_available = False
        
        token = self.auth_service.load_token(suppress_legacy_warning=True)
        if not token:
            return {
                "authenticated": False,
                "message": "Not authenticated",
                "server_auth_enabled": auth_enabled,
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": keyring_available
                }
            }
        
        # Validate token by making a request
        try:
            user_info = self.get_current_user()
            return {
                "authenticated": True,
                "user": user_info,
                "server_auth_enabled": auth_enabled,
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": keyring_available
                }
            }
        except AuthenticationError:
            return {
                "authenticated": False,
                "message": "Token expired or invalid",
                "server_auth_enabled": auth_enabled,
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": keyring_available
                }
            }
        except Exception as e:
            return {
                "authenticated": False,
                "message": f"Error checking status: {e!s}",
                "server_auth_enabled": auth_enabled,
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": keyring_available
                }
            }

    # Quota management methods
    @handle_api_errors(operation_name="Get quota", custom_errors={
        404: "API key not found",
        503: "Quota service is not available (throttling may be disabled)"
    })
    def get_quota(self, api_key: str) -> dict[str, Any]:
        """Get quota configuration and usage for an API key."""
        headers = self._get_auth_headers()
        response = self.api_client.get(f"/admin/api-keys/{api_key}/quota", headers=headers)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Update quota", custom_errors={
        404: "API key not found",
        503: "Quota service is not available (throttling may be disabled)"
    })
    def update_quota(self, api_key: str, quota_data: dict[str, Any]) -> dict[str, Any]:
        """Update quota settings for an API key."""
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        response = self.api_client.put(f"/admin/api-keys/{api_key}/quota", headers=headers, json_data=quota_data)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Reset quota", custom_errors={
        404: "API key not found",
        503: "Quota service is not available (throttling may be disabled)"
    })
    def reset_quota(self, api_key: str, period: str = "daily") -> dict[str, Any]:
        """Reset quota usage for an API key."""
        headers = self._get_auth_headers()
        params = {"period": period}
        response = self.api_client.post(f"/admin/api-keys/{api_key}/quota/reset", headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    @handle_api_errors(operation_name="Get quota report", custom_errors={
        503: "Quota service is not available (throttling may be disabled)"
    })
    def get_quota_report(self, period: str = "daily", limit: int = 100) -> dict[str, Any]:
        """Get quota usage report for all API keys."""
        headers = self._get_auth_headers()
        params = {"period": period, "limit": str(limit)}
        response = self.api_client.get("/admin/quotas/usage-report", headers=headers, params=params)
        response.raise_for_status()
        return response.json()
