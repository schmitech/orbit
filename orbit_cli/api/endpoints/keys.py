"""API key management endpoints."""

from typing import Dict, Any, List, Optional

from ..base_client import AuthenticatedAPIClient
from ..decorators import handle_api_errors, require_auth, paginated
from ...core.exceptions import OrbitError


class ApiKeysAPI(AuthenticatedAPIClient):
    """Handles API key management operations."""
    
    @require_auth
    @handle_api_errors(
        operation_name="Create API key",
        custom_errors={
            403: "Admin privileges required to create API keys",
            409: "API key with this name already exists"
        }
    )
    def create_api_key(
        self,
        collection_name: str,
        client_name: str,
        notes: Optional[str] = None,
        expires_in_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a client.
        
        Args:
            collection_name: The name of the Chroma collection to associate with this key
            client_name: The name of the client
            notes: Optional notes about this API key
            expires_in_days: Optional expiration time in days
            
        Returns:
            Dictionary containing the created API key details
        """
        data = {
            "collection_name": collection_name,
            "client_name": client_name
        }
        
        if notes:
            data["notes"] = notes
        if expires_in_days:
            data["expires_in_days"] = expires_in_days
        
        response = self.post("/admin/api-keys", json_data=data)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="List API keys")
    def list_api_keys(
        self,
        collection: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all API keys with optional server-side filtering.
        
        Args:
            collection: Optional collection name filter
            active_only: If True, only return active keys
            limit: Maximum number of keys to return (default: 100, max: 1000)
            offset: Number of keys to skip for pagination (default: 0)
            
        Returns:
            List of dictionaries containing API key details
        """
        params = {
            'limit': str(min(limit, 1000)),
            'offset': str(offset)
        }
        
        if collection:
            params['collection'] = collection
        if active_only:
            params['active_only'] = 'true'
        
        response = self.get("/admin/api-keys", params=params)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @paginated(page_size=100)
    def list_all_api_keys(
        self,
        collection: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all API keys with automatic pagination.
        
        Args:
            collection: Optional collection name filter
            active_only: If True, only return active keys
            limit: Used internally by paginated decorator
            offset: Used internally by paginated decorator
            
        Returns:
            Complete list of all API keys
        """
        return self.list_api_keys(collection, active_only, limit, offset)
    
    @require_auth
    @handle_api_errors(
        operation_name="Get API key status",
        custom_errors={
            404: "API key not found"
        }
    )
    def get_api_key_status(self, api_key: str) -> Dict[str, Any]:
        """
        Get the status of an API key.
        
        Args:
            api_key: The API key to check
            
        Returns:
            Dictionary containing the API key status
        """
        response = self.get(f"/admin/api-keys/{api_key}/status")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Deactivate API key")
    def deactivate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Deactivate an API key.
        
        Args:
            api_key: The API key to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(
            "/admin/api-keys/deactivate",
            json_data={"api_key": api_key}
        )
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Activate API key")
    def activate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Activate a previously deactivated API key.
        
        Args:
            api_key: The API key to activate
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(
            "/admin/api-keys/activate",
            json_data={"api_key": api_key}
        )
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Delete API key",
        custom_errors={
            404: "API key not found"
        }
    )
    def delete_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Delete an API key.
        
        Args:
            api_key: The API key to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.delete(f"/admin/api-keys/{api_key}")
        response.raise_for_status()
        return response.json()
    
    @handle_api_errors(operation_name="Test API key")
    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Test an API key by making a simple health check request.
        
        Args:
            api_key: The API key to test
            
        Returns:
            Dictionary containing the test result
        """
        # Basic format check
        if not api_key or len(api_key) < 10:
            return {
                "status": "error",
                "error": "API key format is invalid"
            }
        
        # Test with health endpoint
        headers = {"X-API-Key": api_key}
        
        try:
            response = self.get("/health", headers=headers, retry=False)
            
            if response.status_code == 401:
                return {
                    "status": "error",
                    "error": "API key is invalid or deactivated"
                }
            elif response.status_code == 403:
                return {
                    "status": "error",
                    "error": "API key is valid but access forbidden"
                }
            
            response.raise_for_status()
            
            # If successful, try to get key status for more info
            if self.token:  # Only if we're authenticated
                try:
                    status = self.get_api_key_status(api_key)
                    return {
                        "status": "success",
                        "message": "API key is valid and active",
                        "key_info": status
                    }
                except:
                    pass
            
            return {
                "status": "success",
                "message": "API key is valid",
                "server_response": response.json() if response.headers.get('content-type') == 'application/json' else response.text
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    @require_auth
    @handle_api_errors(operation_name="Associate prompt with API key")
    def associate_prompt_with_api_key(self, api_key: str, prompt_id: str) -> Dict[str, Any]:
        """
        Associate a system prompt with an API key.
        
        Args:
            api_key: The API key
            prompt_id: The ID of the prompt to associate
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(
            f"/admin/api-keys/{api_key}/prompt",
            json_data={"prompt_id": prompt_id}
        )
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Update API key")
    def update_api_key(
        self,
        api_key: str,
        client_name: Optional[str] = None,
        notes: Optional[str] = None,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update API key information.
        
        Args:
            api_key: The API key to update
            client_name: New client name (optional)
            notes: New notes (optional)
            collection_name: New collection name (optional)
            
        Returns:
            Updated API key information
        """
        data = {}
        if client_name is not None:
            data["client_name"] = client_name
        if notes is not None:
            data["notes"] = notes
        if collection_name is not None:
            data["collection_name"] = collection_name
        
        response = self.patch(f"/admin/api-keys/{api_key}", json_data=data)
        response.raise_for_status()
        return response.json()