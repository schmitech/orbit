#!/usr/bin/env python3
"""
API Key Manager Utility
======================

A command-line utility for managing API keys and system prompts for the chat server.

Features:
- Create, list, test, and deactivate API keys
- Create and manage system prompts (templates that guide LLM responses)
- Associate prompts with API keys

Requirements:
- requests
- python-dotenv

Configuration:
  Server URL can be provided via:
  - Command line argument (--url or --server)
  - API_SERVER_URL environment variable
  - API_ADMIN_TOKEN environment variable for authentication (optional)

API Key Management Examples:
  # Create a new API key
  python api_key_manager.py --url http://localhost:3000 create --collection customer_data --name "Customer Support" --notes "For support portal"

  # List all API keys
  python api_key_manager.py --url http://localhost:3000 list

  # Check status of an API key
  python api_key_manager.py --url http://localhost:3000 status --key api_abcd1234

  # Test an API key
  python api_key_manager.py --url http://localhost:3000 test --key api_abcd1234

  # Deactivate an API key
  python api_key_manager.py --url http://localhost:3000 deactivate --key api_abcd1234

  # Delete an API key
  python api_key_manager.py --url http://localhost:3000 delete --key api_abcd1234

System Prompt Management Examples:
  # Create a new system prompt
  python api_key_manager.py --url http://localhost:3000 prompt create --name "Support Assistant" --file prompts/support.txt --version "1.0"

  # List all prompts
  python api_key_manager.py --url http://localhost:3000 prompt list

  # Get a specific prompt
  python api_key_manager.py --url http://localhost:3000 prompt get --id 612a4b3c78e9f25d3e1f42a7

  # Update a prompt
  python api_key_manager.py --url http://localhost:3000 prompt update --id 612a4b3c78e9f25d3e1f42a7 --file prompts/updated.txt --version "1.1"

  # Delete a prompt
  python api_key_manager.py --url http://localhost:3000 prompt delete --id 612a4b3c78e9f25d3e1f42a7

  # Associate a prompt with an API key
  python api_key_manager.py --url http://localhost:3000 prompt associate --key api_abcd1234 --prompt-id 612a4b3c78e9f25d3e1f42a7

Creating API Keys with Prompts:
  # Create API key with a new prompt
  python api_key_manager.py --url http://localhost:3000 create --collection support_docs --name "Support Team" --prompt-file prompts/support.txt --prompt-name "Support Assistant"

  # Create API key with an existing prompt
  python api_key_manager.py --url http://localhost:3000 create --collection legal_docs --name "Legal Team" --prompt-id 612a4b3c78e9f25d3e1f42a7
"""

import argparse
import json
import os
import sys
import requests
from typing import Dict, Any, List, Optional
import dotenv


class ApiKeyManager:
    """Utility class for managing API keys and system prompts via the server API endpoints"""
    
    def __init__(self, server_url: str = None):
        """
        Initialize the API Key Manager
        
        Args:
            server_url: The URL of the server, e.g., 'http://localhost:3000'
                        If None, tries to load from environment variable API_SERVER_URL
        """
        # Load environment variables from .env file if it exists
        dotenv.load_dotenv()
        
        # Get server URL from args or environment
        self.server_url = server_url or os.environ.get('API_SERVER_URL')
        if not self.server_url:
            raise ValueError("Server URL must be provided either as an argument or as API_SERVER_URL environment variable")
        
        # Ensure server URL doesn't have a trailing slash
        self.server_url = self.server_url.rstrip('/')
        
        # Set admin auth token if available in environment
        self.admin_token = os.environ.get('API_ADMIN_TOKEN')
    
    def create_api_key(
        self, 
        collection_name: str, 
        client_name: str, 
        notes: Optional[str] = None,
        prompt_id: Optional[str] = None,
        prompt_name: Optional[str] = None,
        prompt_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a client, optionally with an associated system prompt
        
        Args:
            collection_name: The name of the Chroma collection to associate with this key
            client_name: The name of the client
            notes: Optional notes about this API key
            prompt_id: Optional existing system prompt ID to associate
            prompt_name: Optional name for a new system prompt
            prompt_file: Optional path to a file containing a system prompt
            
        Returns:
            Dictionary containing the created API key details
        """
        # First handle prompt if needed
        if prompt_file and (prompt_name or prompt_id):
            # If we have a prompt file, we need to either create a new prompt or update an existing one
            prompt_text = self._read_file_content(prompt_file)
            
            if prompt_id:
                # Update an existing prompt
                prompt_result = self.update_prompt(prompt_id, prompt_text)
                print(f"Debug - Prompt update response: {json.dumps(prompt_result, indent=2)}")  # Debug log
                prompt_id = prompt_result.get("id") or prompt_id
            elif prompt_name:
                # Create a new prompt
                prompt_result = self.create_prompt(prompt_name, prompt_text)
                print(f"Debug - Prompt creation response: {json.dumps(prompt_result, indent=2)}")  # Debug log
                prompt_id = prompt_result.get("id")
                if not prompt_id:
                    print(f"Debug - Full prompt result: {json.dumps(prompt_result, indent=2)}")  # Debug log
                    raise RuntimeError("Failed to get prompt ID from created prompt")
        
        # Now create the API key
        url = f"{self.server_url}/admin/api-keys"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "collection_name": collection_name,
            "client_name": client_name
        }
        
        if notes:
            data["notes"] = notes
        
        try:
            # First create the API key
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            api_key_result = response.json()
            print(f"Debug - API key creation response: {json.dumps(api_key_result, indent=2)}")  # Debug log
            
            # If we have a prompt ID, associate it with the API key
            if prompt_id:
                api_key = api_key_result.get("api_key")
                if not api_key:
                    raise RuntimeError("Failed to get API key from creation response")
                
                print(f"Debug - Associating prompt {prompt_id} with API key {api_key}")  # Debug log
                association_result = self.associate_prompt_with_api_key(api_key, prompt_id)
                print(f"Debug - Prompt association response: {json.dumps(association_result, indent=2)}")  # Debug log
                
                # Update the result with the prompt ID
                api_key_result["system_prompt_id"] = prompt_id
            
            return api_key_result
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error creating API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error creating API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def _read_file_content(self, file_path: str) -> str:
        """
        Read content from a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content of the file as a string
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            raise RuntimeError(f"Error reading file {file_path}: {str(e)}") from e
    
    def list_api_keys(self) -> List[Dict[str, Any]]:
        """
        List all API keys
        
        Returns:
            List of dictionaries containing API key details
        """
        url = f"{self.server_url}/admin/api-keys"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error listing API keys: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error listing API keys: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def deactivate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Deactivate an API key
        
        Args:
            api_key: The API key to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/api-keys/deactivate"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "api_key": api_key
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error deactivating API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error deactivating API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def delete_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Delete an API key
        
        Args:
            api_key: The API key to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/api-keys/{api_key}"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error deleting API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error deleting API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def get_api_key_status(self, api_key: str) -> Dict[str, Any]:
        """
        Get the status of an API key
        
        Args:
            api_key: The API key to check
            
        Returns:
            Dictionary containing the API key status
        """
        url = f"{self.server_url}/admin/api-keys/{api_key}/status"
        
        headers = {}
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error checking API key status: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error checking API key status: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Test an API key by making a simple health check request
        
        Args:
            api_key: The API key to test
            
        Returns:
            Dictionary containing the health check response or error details
        """
        url = f"{self.server_url}/health"
        
        headers = {
            "X-API-Key": api_key
        }
        
        try:
            response = requests.get(url, headers=headers)
            # Check for 401 Unauthorized which would indicate an invalid or deactivated key
            if response.status_code == 401:
                return {
                    "status": "error",
                    "error": "API key is invalid or deactivated",
                    "details": response.json() if response.headers.get('content-type') == 'application/json' else response.text
                }
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 401:
                    return {
                        "status": "error",
                        "error": "API key is invalid or deactivated",
                        "details": e.response.json() if e.response.headers.get('content-type') == 'application/json' else e.response.text
                    }
                error_msg = f"API key test failed: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"API key test failed: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    # System Prompt Management
    
    def create_prompt(self, name: str, prompt_text: str, version: str = "1.0") -> Dict[str, Any]:
        """
        Create a new system prompt
        
        Args:
            name: A unique name for the prompt
            prompt_text: The prompt text
            version: Version string for the prompt
            
        Returns:
            Dictionary containing the created prompt details
        """
        url = f"{self.server_url}/admin/prompts"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "name": name,
            "prompt": prompt_text,
            "version": version
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            print(f"Debug - Prompt creation response: {json.dumps(result, indent=2)}")  # Debug log
            return result
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error creating prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error creating prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List all system prompts
        
        Returns:
            List of dictionaries containing prompt details
        """
        url = f"{self.server_url}/admin/prompts"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error listing prompts: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error listing prompts: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def get_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """
        Get a system prompt by its ID
        
        Args:
            prompt_id: The ID of the prompt
            
        Returns:
            Dictionary containing the prompt details
        """
        url = f"{self.server_url}/admin/prompts/{prompt_id}"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error getting prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error getting prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def update_prompt(self, prompt_id: str, prompt_text: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing system prompt
        
        Args:
            prompt_id: The ID of the prompt to update
            prompt_text: The new prompt text
            version: Optional new version string
            
        Returns:
            Dictionary containing the updated prompt details
        """
        url = f"{self.server_url}/admin/prompts/{prompt_id}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "prompt": prompt_text
        }
        
        if version:
            data["version"] = version
        
        try:
            response = requests.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error updating prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error updating prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def delete_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """
        Delete a system prompt
        
        Args:
            prompt_id: The ID of the prompt to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/prompts/{prompt_id}"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error deleting prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error deleting prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def associate_prompt_with_api_key(self, api_key: str, prompt_id: str) -> Dict[str, Any]:
        """
        Associate a system prompt with an API key
        
        Args:
            api_key: The API key
            prompt_id: The ID of the prompt to associate
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/api-keys/{api_key}/prompt"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "prompt_id": prompt_id
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error associating prompt with API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error associating prompt with API key: {str(e)}"
            raise RuntimeError(error_msg) from e


def main():
    """Command-line interface for the API Key Manager"""
    parser = argparse.ArgumentParser(description="API Key and Prompt Manager for the chat server")
    
    # Add both --server and --url options for server URL
    server_group = parser.add_mutually_exclusive_group()
    server_group.add_argument("--server", help="Server URL, e.g., http://localhost:3000")
    server_group.add_argument("--url", help="Server URL, e.g., http://localhost:3000")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # API Key management commands
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--collection", required=True, help="Collection name to associate with the key")
    create_parser.add_argument("--name", required=True, help="Client name")
    create_parser.add_argument("--notes", help="Optional notes about this API key")
    create_parser.add_argument("--prompt-id", help="Existing system prompt ID to associate with the key")
    create_parser.add_argument("--prompt-name", help="Name for a new system prompt")
    create_parser.add_argument("--prompt-file", help="Path to a file containing a system prompt")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all API keys")
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate an API key")
    deactivate_parser.add_argument("--key", required=True, help="API key to deactivate")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an API key")
    delete_parser.add_argument("--key", required=True, help="API key to delete")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test an API key")
    test_parser.add_argument("--key", required=True, help="API key to test")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get the status of an API key")
    status_parser.add_argument("--key", required=True, help="API key to check")
    
    # System Prompt management commands
    prompt_parser = subparsers.add_parser("prompt", help="System prompt management")
    prompt_subparsers = prompt_parser.add_subparsers(dest="prompt_command", help="Prompt command to execute")
    
    # Create prompt command
    prompt_create_parser = prompt_subparsers.add_parser("create", help="Create a new system prompt")
    prompt_create_parser.add_argument("--name", required=True, help="Unique name for the prompt")
    prompt_create_parser.add_argument("--file", required=True, help="Path to a file containing the prompt text")
    prompt_create_parser.add_argument("--version", default="1.0", help="Version string (default: 1.0)")
    
    # List prompts command
    prompt_list_parser = prompt_subparsers.add_parser("list", help="List all system prompts")
    
    # Get prompt command
    prompt_get_parser = prompt_subparsers.add_parser("get", help="Get a system prompt by ID")
    prompt_get_parser.add_argument("--id", required=True, help="Prompt ID")
    
    # Update prompt command
    prompt_update_parser = prompt_subparsers.add_parser("update", help="Update an existing system prompt")
    prompt_update_parser.add_argument("--id", required=True, help="Prompt ID to update")
    prompt_update_parser.add_argument("--file", required=True, help="Path to a file containing the updated prompt text")
    prompt_update_parser.add_argument("--version", help="New version string")
    
    # Delete prompt command
    prompt_delete_parser = prompt_subparsers.add_parser("delete", help="Delete a system prompt")
    prompt_delete_parser.add_argument("--id", required=True, help="Prompt ID to delete")
    
    # Associate prompt with API key command
    prompt_associate_parser = prompt_subparsers.add_parser("associate", help="Associate a system prompt with an API key")
    prompt_associate_parser.add_argument("--key", required=True, help="API key")
    prompt_associate_parser.add_argument("--prompt-id", required=True, help="Prompt ID to associate")

    args = parser.parse_args()
    
    try:
        # Use either --url or --server parameter for the server URL
        server_url = args.url or args.server
        
        manager = ApiKeyManager(server_url=server_url)
        
        # Handle API Key commands
        if args.command == "create":
            result = manager.create_api_key(
                args.collection, 
                args.name, 
                args.notes,
                args.prompt_id,
                args.prompt_name,
                args.prompt_file
            )
            print(json.dumps(result, indent=2))
            print("\nAPI key created successfully.")
            
        elif args.command == "list":
            result = manager.list_api_keys()
            print(json.dumps(result, indent=2))
            print(f"\nFound {len(result)} API keys.")
            
        elif args.command == "deactivate":
            result = manager.deactivate_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key deactivated successfully.")
            
        elif args.command == "delete":
            result = manager.delete_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key deleted successfully.")
            
        elif args.command == "test":
            result = manager.test_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key test completed successfully.")
            
        elif args.command == "status":
            result = manager.get_api_key_status(args.key)
            print(json.dumps(result, indent=2))
            if result.get("active"):
                print("\nAPI key is active.")
            else:
                print("\nAPI key is inactive.")
                
        # Handle System Prompt commands
        elif args.command == "prompt":
            if args.prompt_command == "create":
                prompt_text = manager._read_file_content(args.file)
                result = manager.create_prompt(args.name, prompt_text, args.version)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt created successfully.")
                
            elif args.prompt_command == "list":
                result = manager.list_prompts()
                print(json.dumps(result, indent=2))
                print(f"\nFound {len(result)} system prompts.")
                
            elif args.prompt_command == "get":
                result = manager.get_prompt(args.id)
                print(json.dumps(result, indent=2))
                
            elif args.prompt_command == "update":
                prompt_text = manager._read_file_content(args.file)
                result = manager.update_prompt(args.id, prompt_text, args.version)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt updated successfully.")
                
            elif args.prompt_command == "delete":
                result = manager.delete_prompt(args.id)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt deleted successfully.")
                
            elif args.prompt_command == "associate":
                result = manager.associate_prompt_with_api_key(args.key, args.prompt_id)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt associated with API key successfully.")
                
            else:
                prompt_parser.print_help()
                sys.exit(1)
            
        else:
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()