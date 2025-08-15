#!/usr/bin/env python3
"""
Direct MongoDB Cleanup Test Data Script
=======================================

This script directly connects to MongoDB to clean up test users, API keys, and system prompts.
It bypasses the CLI and directly removes test records from the database.

Cleanup criteria:
- Test Users: Usernames containing patterns like 'testuser_', 'cli_comprehensive_', 
  'lookup_test_', 'activation_test_', 'debug_test_user_', etc.
- Test API Keys: Keys where client_name, notes, or name fields contain 'test',
  or where the notes field is null/None.
- Test System Prompts: Prompts where name field contains 'test', 'CLI Test Prompt', etc.

Usage:
    python direct_cleanup_test_users.py [options]

Options:
    --dry-run       Show what would be deleted without actually deleting
    --verbose       Show detailed output
    --list          List all users in the database
    --users-only    Only clean up test users
    --keys-only     Only clean up test API keys
    --prompts-only  Only clean up test system prompts
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import MongoDB
try:
    from pymongo import MongoClient
    from bson import ObjectId
except ImportError:
    logger.error("pymongo not installed. Please install it with: pip install pymongo")
    sys.exit(1)


class DirectTestUserCleanup:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.client = None
        self.db = None
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
    
    def connect_to_mongodb(self) -> bool:
        """Connect to MongoDB"""
        try:
            # Get MongoDB connection details from environment
            host = os.getenv('INTERNAL_SERVICES_MONGODB_HOST', 'localhost')
            port = int(os.getenv('INTERNAL_SERVICES_MONGODB_PORT', 27017))
            username = os.getenv('INTERNAL_SERVICES_MONGODB_USERNAME')
            password = os.getenv('INTERNAL_SERVICES_MONGODB_PASSWORD')
            database = os.getenv('INTERNAL_SERVICES_MONGODB_DATABASE', 'orbit')
            
            # Build connection URI
            if username and password:
                # For cloud MongoDB (Atlas)
                if 'mongodb.net' in host or '+srv' in host:
                    # MongoDB Atlas connection string
                    uri = f"mongodb+srv://{username}:{password}@{host.replace('mongodb+srv://', '').split('@')[-1]}/{database}?retryWrites=true&w=majority"
                else:
                    # Standard MongoDB with auth
                    uri = f'mongodb://{username}:{password}@{host}:{port}/{database}?authSource=admin'
            else:
                # Local MongoDB without auth
                uri = f'mongodb://{host}:{port}/{database}'
            
            if self.verbose:
                # Mask password in debug output
                safe_uri = uri
                if password:
                    safe_uri = uri.replace(password, '***')
                logger.debug(f"Connecting to MongoDB: {safe_uri}")
            
            # Connect to MongoDB
            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            
            # Test connection
            self.client.server_info()
            
            # Select database
            self.db = self.client[database]
            
            logger.info(f"✓ Connected to MongoDB database: {database}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to connect to MongoDB: {e}")
            return False
    
    def get_test_users(self) -> List[Dict[str, Any]]:
        """Get all test users from the database"""
        if self.db is None:
            logger.error("Not connected to database")
            return []
        
        # Define test patterns - comprehensive list from all test files
        test_patterns = [
            "testuser_",
            "cli_comprehensive_", 
            "pwd_test_",
            "defaultuser_",
            "user_to_delete_",
            "lookup_test_",
            "activation_test_",
            "debug_test_user_",
            "test_activation_user",
            "test_user"  # Be careful with this one - it's quite generic
        ]
        
        try:
            # Get all users from the users collection
            users_collection = self.db.users
            all_users = list(users_collection.find())
            
            test_users = []
            for user in all_users:
                username = user.get('username', '')
                # Skip admin user
                if username == 'admin':
                    continue
                    
                # Check if username matches any test pattern
                if any(pattern in username for pattern in test_patterns):
                    test_users.append({
                        '_id': user.get('_id'),
                        'username': username,
                        'role': user.get('role', 'unknown'),
                        'active': user.get('active', False)
                    })
            
            return test_users
            
        except Exception as e:
            logger.error(f"Error getting test users: {e}")
            return []
    
    def delete_user(self, user_id: ObjectId, username: str) -> bool:
        """Delete a user from the database"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete user: {username} (ID: {user_id})")
            return True
        
        try:
            # Delete from users collection
            result = self.db.users.delete_one({'_id': user_id})
            
            if result.deleted_count > 0:
                logger.info(f"✓ Deleted user: {username} (ID: {user_id})")
                
                # Also clean up any sessions for this user
                sessions_result = self.db.sessions.delete_many({'user_id': str(user_id)})
                if sessions_result.deleted_count > 0:
                    logger.debug(f"  Deleted {sessions_result.deleted_count} session(s) for user {username}")
                
                # Clean up API keys if they exist
                try:
                    api_keys_result = self.db.api_keys.delete_many({'user_id': str(user_id)})
                    if api_keys_result.deleted_count > 0:
                        logger.debug(f"  Deleted {api_keys_result.deleted_count} API key(s) for user {username}")
                except:
                    pass  # API keys collection might not exist
                
                return True
            else:
                logger.warning(f"⚠ User not found: {username} (ID: {user_id})")
                return False
                
        except Exception as e:
            logger.error(f"✗ Failed to delete user {username}: {e}")
            return False
    
    def get_test_api_keys(self) -> List[Dict[str, Any]]:
        """Get all test API keys from the database"""
        if self.db is None:
            logger.error("Not connected to database")
            return []
        
        try:
            # Get all API keys from the api_keys collection
            api_keys_collection = self.db.api_keys
            all_keys = list(api_keys_collection.find())
            
            test_keys = []
            for key in all_keys:
                # Get the raw notes value to check for None/null
                notes_raw = key.get('notes')
                
                # Check if notes field is None/null
                if notes_raw is None:
                    test_keys.append({
                        '_id': key.get('_id'),
                        'client_name': key.get('client_name', 'N/A'),
                        'notes': 'NULL',  # Mark as NULL for display
                        'name': key.get('name', 'N/A'),
                        'api_key': key.get('api_key', 'N/A')[:20] + '...' if key.get('api_key') else 'N/A',
                        'reason': 'Notes field is null'
                    })
                    continue
                
                # Check if any field contains 'test' (case insensitive)
                client_name = str(key.get('client_name', '')).lower()
                notes = str(notes_raw).lower()
                name = str(key.get('name', '')).lower()
                
                # Check if this is a test API key
                if ('test' in client_name or 
                    'test' in notes or 
                    'test' in name or
                    'cli test' in client_name or
                    'cli integration' in notes or
                    'cli comprehensive' in client_name):
                    test_keys.append({
                        '_id': key.get('_id'),
                        'client_name': key.get('client_name', 'N/A'),
                        'notes': key.get('notes', 'N/A'),
                        'name': key.get('name', 'N/A'),
                        'api_key': key.get('api_key', 'N/A')[:20] + '...' if key.get('api_key') else 'N/A',
                        'reason': 'Contains test-related text'
                    })
            
            return test_keys
            
        except Exception as e:
            logger.error(f"Error getting test API keys: {e}")
            return []
    
    def delete_api_key(self, key_id: ObjectId, client_name: str) -> bool:
        """Delete an API key from the database"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete API key: {client_name} (ID: {key_id})")
            return True
        
        try:
            # Delete from api_keys collection
            result = self.db.api_keys.delete_one({'_id': key_id})
            
            if result.deleted_count > 0:
                logger.info(f"✓ Deleted API key: {client_name} (ID: {key_id})")
                return True
            else:
                logger.warning(f"⚠ API key not found: {client_name} (ID: {key_id})")
                return False
                
        except Exception as e:
            logger.error(f"✗ Failed to delete API key {client_name}: {e}")
            return False
    
    def get_test_system_prompts(self) -> List[Dict[str, Any]]:
        """Get all test system prompts from the database"""
        if self.db is None:
            logger.error("Not connected to database")
            return []
        
        try:
            # Get all system prompts from the system_prompts collection
            prompts_collection = self.db.system_prompts
            all_prompts = list(prompts_collection.find())
            
            test_prompts = []
            for prompt in all_prompts:
                # Check if name field contains test-related patterns
                name = str(prompt.get('name', '')).lower()
                
                # Check if this is a test system prompt
                if ('test' in name or 
                    'cli test' in name or
                    'cli integration' in name or
                    'cli comprehensive' in name):
                    test_prompts.append({
                        '_id': prompt.get('_id'),
                        'name': prompt.get('name', 'N/A'),
                        'version': prompt.get('version', 'N/A'),
                        'created_at': prompt.get('created_at', 'N/A')
                    })
            
            return test_prompts
            
        except Exception as e:
            logger.error(f"Error getting test system prompts: {e}")
            return []
    
    def delete_system_prompt(self, prompt_id: ObjectId, name: str) -> bool:
        """Delete a system prompt from the database"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete system prompt: {name} (ID: {prompt_id})")
            return True
        
        try:
            # Delete from system_prompts collection
            result = self.db.system_prompts.delete_one({'_id': prompt_id})
            
            if result.deleted_count > 0:
                logger.info(f"✓ Deleted system prompt: {name} (ID: {prompt_id})")
                return True
            else:
                logger.warning(f"⚠ System prompt not found: {name} (ID: {prompt_id})")
                return False
                
        except Exception as e:
            logger.error(f"✗ Failed to delete system prompt {name}: {e}")
            return False
    
    def cleanup_test_system_prompts(self) -> int:
        """Clean up all test system prompts"""
        try:
            test_prompts = self.get_test_system_prompts()
            
            if not test_prompts:
                logger.info("No test system prompts found to clean up")
                return 0
            
            logger.info(f"\nFound {len(test_prompts)} test system prompts to clean up:")
            for prompt in test_prompts:
                logger.info(f"  • {prompt['name']} (ID: {prompt['_id']})")
                if prompt['version'] != 'N/A':
                    logger.info(f"    Version: {prompt['version']}")
            
            if self.dry_run:
                logger.info("\n[DRY RUN MODE] No system prompts will be actually deleted")
            else:
                logger.info("\nDeleting test system prompts...")
            
            deleted_count = 0
            for prompt in test_prompts:
                if self.delete_system_prompt(prompt['_id'], prompt['name']):
                    deleted_count += 1
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during system prompt cleanup: {e}")
            return 0
    
    def cleanup_test_api_keys(self) -> int:
        """Clean up all test API keys"""
        try:
            test_keys = self.get_test_api_keys()
            
            if not test_keys:
                logger.info("No test API keys found to clean up")
                return 0
            
            logger.info(f"\nFound {len(test_keys)} API keys to clean up:")
            
            # Group by reason for better display
            null_notes_keys = [k for k in test_keys if k.get('reason') == 'Notes field is null']
            test_related_keys = [k for k in test_keys if k.get('reason') == 'Contains test-related text']
            
            if null_notes_keys:
                logger.info(f"\n  Keys with NULL notes field ({len(null_notes_keys)}):")
                for key in null_notes_keys:
                    logger.info(f"    • {key['client_name']} (ID: {key['_id']})")
            
            if test_related_keys:
                logger.info(f"\n  Test-related keys ({len(test_related_keys)}):")
                for key in test_related_keys:
                    logger.info(f"    • {key['client_name']} (ID: {key['_id']})")
                    if key['notes'] != 'N/A' and key['notes'] != 'NULL':
                        logger.info(f"      Notes: {key['notes']}")
            
            if self.dry_run:
                logger.info("\n[DRY RUN MODE] No API keys will be actually deleted")
            else:
                logger.info("\nDeleting API keys...")
            
            deleted_count = 0
            for key in test_keys:
                if self.delete_api_key(key['_id'], key['client_name']):
                    deleted_count += 1
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during API key cleanup: {e}")
            return 0
    
    def cleanup_all(self) -> tuple:
        """Clean up all test users, API keys, and system prompts"""
        if not self.connect_to_mongodb():
            logger.error("Cannot proceed without database connection")
            return 0, 0, 0
        
        try:
            # Clean up test users
            test_users = self.get_test_users()
            
            if not test_users:
                logger.info("No test users found to clean up")
                deleted_users = 0
            else:
                logger.info(f"Found {len(test_users)} test users to clean up:")
                for user in test_users:
                    status = "✓" if user['active'] else "✗"
                    logger.info(f"  {status} {user['username']} (ID: {user['_id']}, Role: {user['role']})")
                
                if self.dry_run:
                    logger.info("\n[DRY RUN MODE] No users will be actually deleted")
                else:
                    logger.info("\nDeleting test users...")
                
                deleted_users = 0
                for user in test_users:
                    if self.delete_user(user['_id'], user['username']):
                        deleted_users += 1
            
            # Clean up test API keys
            deleted_keys = self.cleanup_test_api_keys()
            
            # Clean up test system prompts
            deleted_prompts = self.cleanup_test_system_prompts()
            
            return deleted_users, deleted_keys, deleted_prompts
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0, 0, 0
        finally:
            if self.client:
                self.client.close()
                logger.debug("Closed MongoDB connection")
    
    def show_all_users(self):
        """Show all users in the database"""
        if not self.connect_to_mongodb():
            logger.error("Cannot proceed without database connection")
            return
        
        try:
            users_collection = self.db.users
            all_users = list(users_collection.find())
            
            if not all_users:
                logger.info("No users found in database")
                return
            
            logger.info(f"\nAll users in database ({len(all_users)} total):")
            logger.info("-" * 60)
            
            for user in all_users:
                username = user.get('username', 'N/A')
                user_id = user.get('_id', 'N/A')
                role = user.get('role', 'N/A')
                active = user.get('active', True)
                status = "✓" if active else "✗"
                
                # Mark test users
                test_patterns = ["testuser_", "cli_comprehensive_", "pwd_test_", 
                               "defaultuser_", "user_to_delete_", "lookup_test_", 
                               "activation_test_", "debug_test_user_", 
                               "test_activation_user", "test_user"]
                is_test = any(pattern in username for pattern in test_patterns)
                test_marker = " [TEST USER]" if is_test else ""
                
                logger.info(f"  {status} {username}{test_marker}")
                logger.info(f"     ID: {user_id}, Role: {role}")
            
            logger.info("-" * 60)
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
        finally:
            if self.client:
                self.client.close()


def main():
    parser = argparse.ArgumentParser(description="Direct MongoDB cleanup of test users, API keys, and system prompts")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be deleted without actually deleting")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Show detailed output")
    parser.add_argument("--list", action="store_true", 
                       help="List all users without deleting anything")
    parser.add_argument("--users-only", action="store_true",
                       help="Only clean up test users")
    parser.add_argument("--keys-only", action="store_true",
                       help="Only clean up test API keys")
    parser.add_argument("--prompts-only", action="store_true",
                       help="Only clean up test system prompts")
    
    args = parser.parse_args()
    
    cleanup = DirectTestUserCleanup(dry_run=args.dry_run, verbose=args.verbose)
    
    if args.list:
        logger.info("Listing all users in database...")
        cleanup.show_all_users()
    elif args.keys_only:
        logger.info("Starting direct MongoDB test API key cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No API keys will be actually deleted")
        
        if cleanup.connect_to_mongodb():
            deleted_keys = cleanup.cleanup_test_api_keys()
            if args.dry_run:
                logger.info(f"\nDRY RUN: Would have deleted {deleted_keys} test API keys")
            else:
                logger.info(f"\nCleanup complete: Deleted {deleted_keys} test API keys")
            cleanup.client.close()
    elif args.prompts_only:
        logger.info("Starting direct MongoDB test system prompt cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No system prompts will be actually deleted")
        
        if cleanup.connect_to_mongodb():
            deleted_prompts = cleanup.cleanup_test_system_prompts()
            if args.dry_run:
                logger.info(f"\nDRY RUN: Would have deleted {deleted_prompts} test system prompts")
            else:
                logger.info(f"\nCleanup complete: Deleted {deleted_prompts} test system prompts")
            cleanup.client.close()
    elif args.users_only:
        logger.info("Starting direct MongoDB test user cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No users will be actually deleted")
        
        deleted_users, _, _ = cleanup.cleanup_all()
        if args.dry_run:
            logger.info(f"\nDRY RUN: Would have deleted {deleted_users} test users")
        else:
            logger.info(f"\nCleanup complete: Deleted {deleted_users} test users")
    else:
        logger.info("Starting direct MongoDB test data cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - Nothing will be actually deleted")
        
        deleted_users, deleted_keys, deleted_prompts = cleanup.cleanup_all()
        
        if args.dry_run:
            logger.info(f"\nDRY RUN: Would have deleted:")
            logger.info(f"  • {deleted_users} test users")
            logger.info(f"  • {deleted_keys} test API keys")
            logger.info(f"  • {deleted_prompts} test system prompts")
        else:
            logger.info(f"\nCleanup complete:")
            logger.info(f"  • Deleted {deleted_users} test users")
            logger.info(f"  • Deleted {deleted_keys} test API keys")
            logger.info(f"  • Deleted {deleted_prompts} test system prompts")


if __name__ == "__main__":
    main()