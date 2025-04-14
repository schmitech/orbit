#!/usr/bin/env python3
"""
API Key Manager Utility

A command-line utility for managing API keys for the chat server.
This tool provides convenient methods for creating, listing, and deactivating API keys.

Usage:
    python api_key_manager.py --url http://host:port create --collection client_collection --name "Client Name" --notes "Optional notes"
    python api_key_manager.py --url http://host:port list
    python api_key_manager.py --url http://host:port test --key YOUR_API_KEY
    python api_key_manager.py --url http://host:port deactivate --key YOUR_API_KEY
"""

import argparse
import json
import os
import sys
import requests
from typing import Dict, Any, List, Optional
import dotenv


class ApiKeyManager:
    """Utility class for managing API keys via the server API endpoints"""
    
    def __init__(self, server_url: str = None):
        """
        Initialize the API Key Manager
        
        Args:
            server_url: The URL of the server, e.g., 'http://localhost:3001'
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
    
    def create_api_key(self, collection_name: str, client_name: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new API key for a client
        
        Args:
            collection_name: The name of the Chroma collection to associate with this key
            client_name: The name of the client
            notes: Optional notes about this API key
            
        Returns:
            Dictionary containing the created API key details
        """
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
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error creating API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error creating API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
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


def main():
    """Command-line interface for the API Key Manager"""
    parser = argparse.ArgumentParser(description="API Key Manager for the chat server")
    
    # Add both --server and --url options for server URL
    server_group = parser.add_mutually_exclusive_group()
    server_group.add_argument("--server", help="Server URL, e.g., http://localhost:3001")
    server_group.add_argument("--url", help="Server URL, e.g., http://localhost:3001")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--collection", required=True, help="Collection name to associate with the key")
    create_parser.add_argument("--name", required=True, help="Client name")
    create_parser.add_argument("--notes", help="Optional notes about this API key")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all API keys")
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate an API key")
    deactivate_parser.add_argument("--key", required=True, help="API key to deactivate")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test an API key")
    test_parser.add_argument("--key", required=True, help="API key to test")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get the status of an API key")
    status_parser.add_argument("--key", required=True, help="API key to check")

    args = parser.parse_args()
    
    try:
        # Use either --url or --server parameter for the server URL
        server_url = args.url or args.server
        
        manager = ApiKeyManager(server_url=server_url)
        
        if args.command == "create":
            result = manager.create_api_key(args.collection, args.name, args.notes)
            print(json.dumps(result, indent=2))
            
        elif args.command == "list":
            result = manager.list_api_keys()
            print(json.dumps(result, indent=2))
            print(f"\nFound {len(result)} API keys.")
            
        elif args.command == "deactivate":
            result = manager.deactivate_api_key(args.key)
            print(json.dumps(result, indent=2))
            print(f"\nAPI key deactivated successfully.")
            
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
            
        else:
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()