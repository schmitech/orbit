"""System prompt management endpoints."""

from typing import Dict, Any, List, Optional

from ..base_client import AuthenticatedAPIClient
from ..decorators import handle_api_errors, require_auth, paginated
from ...core.exceptions import OrbitError


class PromptsAPI(AuthenticatedAPIClient):
    """Handles system prompt management operations."""
    
    @require_auth
    @handle_api_errors(
        operation_name="Create prompt",
        custom_errors={
            403: "Admin privileges required to create prompts",
            409: "Prompt with this name already exists"
        }
    )
    def create_prompt(
        self,
        name: str,
        prompt: str,
        version: str = "1.0",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new system prompt.
        
        Args:
            name: A unique name for the prompt
            prompt: The prompt text
            version: Version string for the prompt (default: "1.0")
            description: Optional description
            tags: Optional list of tags
            
        Returns:
            Dictionary containing the created prompt details
        """
        data = {
            "name": name,
            "prompt": prompt,
            "version": version
        }
        
        if description:
            data["description"] = description
        if tags:
            data["tags"] = tags
        
        response = self.post("/admin/prompts", json_data=data)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="List prompts")
    def list_prompts(
        self,
        name_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all system prompts with optional server-side filtering.
        
        Args:
            name_filter: Optional name filter (case-insensitive partial match)
            tag_filter: Optional tag filter
            limit: Maximum number of prompts to return (default: 100, max: 1000)
            offset: Number of prompts to skip for pagination (default: 0)
            
        Returns:
            List of dictionaries containing prompt details
        """
        params = {
            'limit': str(min(limit, 1000)),
            'offset': str(offset)
        }
        
        if name_filter:
            params['name_filter'] = name_filter
        if tag_filter:
            params['tag_filter'] = tag_filter
        
        response = self.get("/admin/prompts", params=params)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @paginated(page_size=100)
    def list_all_prompts(
        self,
        name_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all system prompts with automatic pagination.
        
        Args:
            name_filter: Optional name filter
            tag_filter: Optional tag filter
            limit: Used internally by paginated decorator
            offset: Used internally by paginated decorator
            
        Returns:
            Complete list of all prompts
        """
        return self.list_prompts(name_filter, tag_filter, limit, offset)
    
    @require_auth
    @handle_api_errors(
        operation_name="Get prompt",
        custom_errors={
            404: "Prompt not found"
        }
    )
    def get_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """
        Get a system prompt by its ID.
        
        Args:
            prompt_id: The ID of the prompt
            
        Returns:
            Dictionary containing the prompt details
        """
        response = self.get(f"/admin/prompts/{prompt_id}")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Get prompt by name",
        custom_errors={
            404: "Prompt not found"
        }
    )
    def get_prompt_by_name(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a system prompt by its name.
        
        Args:
            name: The name of the prompt
            version: Optional version (gets latest if not specified)
            
        Returns:
            Dictionary containing the prompt details
        """
        params = {"name": name}
        if version:
            params["version"] = version
        
        response = self.get("/admin/prompts/by-name", params=params)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Update prompt",
        custom_errors={
            404: "Prompt not found",
            409: "Version conflict"
        }
    )
    def update_prompt(
        self,
        prompt_id: str,
        prompt: Optional[str] = None,
        version: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing system prompt.
        
        Args:
            prompt_id: The ID of the prompt to update
            prompt: The new prompt text (optional)
            version: New version string (optional)
            description: New description (optional)
            tags: New tags list (optional)
            
        Returns:
            Dictionary containing the updated prompt details
        """
        data = {}
        if prompt is not None:
            data["prompt"] = prompt
        if version is not None:
            data["version"] = version
        if description is not None:
            data["description"] = description
        if tags is not None:
            data["tags"] = tags
        
        response = self.put(f"/admin/prompts/{prompt_id}", json_data=data)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Delete prompt",
        custom_errors={
            404: "Prompt not found",
            409: "Prompt is in use by API keys"
        }
    )
    def delete_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """
        Delete a system prompt.
        
        Args:
            prompt_id: The ID of the prompt to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.delete(f"/admin/prompts/{prompt_id}")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Get prompt versions")
    def get_prompt_versions(self, name: str) -> List[Dict[str, Any]]:
        """
        Get all versions of a prompt by name.
        
        Args:
            name: The name of the prompt
            
        Returns:
            List of prompt versions
        """
        response = self.get(f"/admin/prompts/versions/{name}")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Clone prompt")
    def clone_prompt(
        self,
        prompt_id: str,
        new_name: str,
        new_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clone an existing prompt with a new name.
        
        Args:
            prompt_id: The ID of the prompt to clone
            new_name: Name for the cloned prompt
            new_version: Version for the cloned prompt (default: "1.0")
            
        Returns:
            Dictionary containing the cloned prompt details
        """
        data = {
            "new_name": new_name
        }
        if new_version:
            data["new_version"] = new_version
        
        response = self.post(f"/admin/prompts/{prompt_id}/clone", json_data=data)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Search prompts")
    def search_prompts(
        self,
        query: str,
        search_in: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search for prompts by query string.
        
        Args:
            query: Search query
            search_in: Fields to search in (default: name, prompt, description)
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of matching prompts
        """
        params = {
            'q': query,
            'limit': str(min(limit, 1000)),
            'offset': str(offset)
        }
        
        if search_in:
            params['fields'] = ','.join(search_in)
        
        response = self.get("/admin/prompts/search", params=params)
        response.raise_for_status()
        return response.json()