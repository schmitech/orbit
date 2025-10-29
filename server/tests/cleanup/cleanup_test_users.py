#!/usr/bin/env python3
"""
Direct Database Cleanup Test Data Script
=========================================

This script directly connects to MongoDB and/or SQLite to clean up test users, API keys, and system prompts.
It bypasses the CLI and directly removes test records from the database(s).

Cleanup criteria:
- Test Users: Usernames containing patterns like 'testuser_', 'cli_comprehensive_', 
  'lookup_test_', 'activation_test_', 'debug_test_user_', etc.
- Test API Keys: Keys where client_name, notes, or name fields contain 'test',
  or where the notes field is null/None.
- Test System Prompts: Prompts where name field contains 'test', 'CLI Test Prompt', etc.

Usage:
    python cleanup_test_users.py [options]

Options:
    --dry-run       Show what would be deleted without actually deleting
    --verbose       Show detailed output
    --list          List all users in the database
    --users-only    Only clean up test users
    --keys-only     Only clean up test API keys
    --prompts-only  Only clean up test system prompts
    --mongodb-only  Only clean up MongoDB database
    --sqlite-only   Only clean up SQLite database
"""

import argparse
import logging
import os
import sys
import sqlite3
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
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
    MONGO_AVAILABLE = True
except ImportError:
    logger.warning("pymongo not installed. MongoDB cleanup will be disabled.")
    MONGO_AVAILABLE = False


class DirectTestUserCleanup:
    def __init__(self, dry_run: bool = False, verbose: bool = False, 
                 mongodb_only: bool = False, sqlite_only: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.mongodb_only = mongodb_only
        self.sqlite_only = sqlite_only
        
        # MongoDB connection
        self.mongo_client = None
        self.mongo_db = None
        
        # SQLite connection
        self.sqlite_conn = None
        self.sqlite_path = None
        
        # Load configuration
        self.config = self._load_config()
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.yaml"""
        config_paths = [
            Path(__file__).parent.parent.parent.parent / 'config' / 'config.yaml',
            Path(__file__).parent.parent.parent / 'config' / 'config.yaml',
            Path('config') / 'config.yaml',
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        if self.verbose:
                            logger.debug(f"Loaded config from: {config_path}")
                        return config
                except Exception as e:
                    logger.warning(f"Error loading config from {config_path}: {e}")
        
        logger.warning("Could not load config.yaml, using defaults")
        return {}
    
    def connect_to_sqlite(self) -> bool:
        """Connect to SQLite database"""
        try:
            # Get SQLite database path from config
            sqlite_config = self.config.get('internal_services', {}).get('backend', {}).get('sqlite', {})
            database_path = sqlite_config.get('database_path', 'orbit.db')
            
            # Try resolving path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            db_path = Path(database_path)
            
            if not db_path.is_absolute():
                db_path = project_root / db_path
            
            self.sqlite_path = str(db_path)
            
            if not db_path.exists():
                logger.warning(f"SQLite database file not found: {self.sqlite_path}")
                return False
            
            if self.verbose:
                logger.debug(f"Connecting to SQLite: {self.sqlite_path}")
            
            # Connect to SQLite
            self.sqlite_conn = sqlite3.connect(self.sqlite_path)
            self.sqlite_conn.row_factory = sqlite3.Row
            
            # Test connection
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            
            logger.info(f"✓ Connected to SQLite database: {self.sqlite_path}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to connect to SQLite: {e}")
            return False
    
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
            
            if not MONGO_AVAILABLE:
                logger.error("pymongo not installed, cannot connect to MongoDB")
                return False
            
            # Connect to MongoDB
            self.mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            
            # Test connection
            self.mongo_client.server_info()
            
            # Select database
            self.mongo_db = self.mongo_client[database]
            
            logger.info(f"✓ Connected to MongoDB database: {database}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to connect to MongoDB: {e}")
            return False
    
    def get_test_users_mongodb(self) -> List[Dict[str, Any]]:
        """Get all test users from MongoDB"""
        if self.mongo_db is None:
            logger.error("Not connected to MongoDB")
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
            users_collection = self.mongo_db.users
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
            logger.error(f"Error getting test users from MongoDB: {e}")
            return []
    
    def get_test_users_sqlite(self) -> List[Dict[str, Any]]:
        """Get all test users from SQLite"""
        if self.sqlite_conn is None:
            logger.error("Not connected to SQLite")
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
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT id, username, role, active FROM users")
            all_users = cursor.fetchall()
            cursor.close()
            
            test_users = []
            for row in all_users:
                username = row['username'] if isinstance(row, sqlite3.Row) else row[1]
                # Skip admin user
                if username == 'admin':
                    continue
                    
                # Check if username matches any test pattern
                if any(pattern in username for pattern in test_patterns):
                    user_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
                    role = row['role'] if isinstance(row, sqlite3.Row) else row[2]
                    active = bool(row['active']) if isinstance(row, sqlite3.Row) else bool(row[3])
                    
                    test_users.append({
                        'id': user_id,
                        'username': username,
                        'role': role,
                        'active': active,
                        'db_type': 'sqlite'
                    })
            
            return test_users
            
        except Exception as e:
            logger.error(f"Error getting test users from SQLite: {e}")
            return []
    
    def get_test_users(self) -> List[Dict[str, Any]]:
        """Get all test users from all configured databases"""
        test_users = []
        
        # Get from MongoDB if configured and not SQLite-only
        if not self.sqlite_only:
            mongodb_users = self.get_test_users_mongodb()
            for user in mongodb_users:
                user['db_type'] = 'mongodb'
            test_users.extend(mongodb_users)
        
        # Get from SQLite if configured and not MongoDB-only
        if not self.mongodb_only:
            sqlite_users = self.get_test_users_sqlite()
            test_users.extend(sqlite_users)
        
        return test_users
    
    def delete_user_mongodb(self, user_id: Any, username: str) -> bool:
        """Delete a user from MongoDB"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete MongoDB user: {username} (ID: {user_id})")
            return True
        
        try:
            # Delete from users collection
            result = self.mongo_db.users.delete_one({'_id': user_id})
            
            if result.deleted_count > 0:
                logger.info(f"✓ Deleted MongoDB user: {username} (ID: {user_id})")
                
                # Also clean up any sessions for this user
                sessions_result = self.mongo_db.sessions.delete_many({'user_id': str(user_id)})
                if sessions_result.deleted_count > 0:
                    logger.debug(f"  Deleted {sessions_result.deleted_count} session(s) for user {username}")
                
                # Clean up API keys if they exist
                try:
                    api_keys_result = self.mongo_db.api_keys.delete_many({'user_id': str(user_id)})
                    if api_keys_result.deleted_count > 0:
                        logger.debug(f"  Deleted {api_keys_result.deleted_count} API key(s) for user {username}")
                except:
                    pass  # API keys collection might not exist
                
                return True
            else:
                logger.warning(f"⚠ MongoDB user not found: {username} (ID: {user_id})")
                return False
                
        except Exception as e:
            logger.error(f"✗ Failed to delete MongoDB user {username}: {e}")
            return False
    
    def delete_user_sqlite(self, user_id: str, username: str) -> bool:
        """Delete a user from SQLite"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete SQLite user: {username} (ID: {user_id})")
            return True
        
        try:
            cursor = self.sqlite_conn.cursor()
            
            # Delete from users table
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            deleted = cursor.rowcount > 0
            
            if deleted:
                self.sqlite_conn.commit()
                logger.info(f"✓ Deleted SQLite user: {username} (ID: {user_id})")
                
                # Also clean up any sessions for this user
                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                sessions_deleted = cursor.rowcount
                if sessions_deleted > 0:
                    logger.debug(f"  Deleted {sessions_deleted} session(s) for user {username}")
                    self.sqlite_conn.commit()
                
                cursor.close()
                return True
            else:
                logger.warning(f"⚠ SQLite user not found: {username} (ID: {user_id})")
                cursor.close()
                return False
                
        except Exception as e:
            logger.error(f"✗ Failed to delete SQLite user {username}: {e}")
            if self.sqlite_conn:
                self.sqlite_conn.rollback()
            return False
    
    def delete_user(self, user: Dict[str, Any]) -> bool:
        """Delete a user from the appropriate database"""
        user_id = user.get('_id') or user.get('id')
        username = user.get('username')
        db_type = user.get('db_type', 'mongodb')
        
        if db_type == 'mongodb':
            return self.delete_user_mongodb(user_id, username)
        elif db_type == 'sqlite':
            return self.delete_user_sqlite(user_id, username)
        else:
            logger.warning(f"Unknown database type: {db_type}")
            return False
    
    def get_test_api_keys_mongodb(self) -> List[Dict[str, Any]]:
        """Get all test API keys from MongoDB"""
        if self.mongo_db is None:
            return []
        
        try:
            api_keys_collection = self.mongo_db.api_keys
            all_keys = list(api_keys_collection.find())
            
            test_keys = []
            for key in all_keys:
                notes_raw = key.get('notes')
                
                if notes_raw is None:
                    test_keys.append({
                        'id': key.get('_id'),
                        'client_name': key.get('client_name', 'N/A'),
                        'notes': 'NULL',
                        'name': key.get('name', 'N/A'),
                        'api_key': key.get('api_key', 'N/A')[:20] + '...' if key.get('api_key') else 'N/A',
                        'reason': 'Notes field is null',
                        'db_type': 'mongodb'
                    })
                    continue
                
                client_name = str(key.get('client_name', '')).lower()
                notes = str(notes_raw).lower()
                name = str(key.get('name', '')).lower()
                
                # Check for test patterns in any field
                is_test = (
                    'test' in client_name or 'test' in notes or 'test' in name or
                    'cli test' in client_name or 'cli test' in notes or
                    'cli integration' in client_name or 'cli integration' in notes or
                    'cli comprehensive' in client_name or 'cli comprehensive' in notes
                )
                
                if is_test:
                    test_keys.append({
                        'id': key.get('_id'),
                        'client_name': key.get('client_name', 'N/A'),
                        'notes': key.get('notes', 'N/A'),
                        'name': key.get('name', 'N/A'),
                        'api_key': key.get('api_key', 'N/A')[:20] + '...' if key.get('api_key') else 'N/A',
                        'reason': 'Contains test-related text',
                        'db_type': 'mongodb'
                    })
            
            return test_keys
        except Exception as e:
            logger.error(f"Error getting test API keys from MongoDB: {e}")
            return []
    
    def get_test_api_keys_sqlite(self) -> List[Dict[str, Any]]:
        """Get all test API keys from SQLite"""
        if self.sqlite_conn is None:
            return []
        
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT id, api_key, client_name, notes, name FROM api_keys")
            all_keys = cursor.fetchall()
            cursor.close()
            
            test_keys = []
            for row in all_keys:
                notes_raw = row['notes'] if isinstance(row, sqlite3.Row) else row[3]
                client_name_val = row['client_name'] if isinstance(row, sqlite3.Row) else row[2]
                name_val = row['name'] if isinstance(row, sqlite3.Row) else (row[4] if len(row) > 4 else 'N/A')
                api_key_val = row['api_key'] if isinstance(row, sqlite3.Row) else row[1]
                key_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
                
                if notes_raw is None:
                    test_keys.append({
                        'id': key_id,
                        'client_name': client_name_val or 'N/A',
                        'notes': 'NULL',
                        'name': name_val or 'N/A',
                        'api_key': (api_key_val[:20] + '...') if api_key_val else 'N/A',
                        'reason': 'Notes field is null',
                        'db_type': 'sqlite'
                    })
                    continue
                
                client_name = str(client_name_val or '').lower()
                notes = str(notes_raw).lower()
                name = str(name_val or '').lower()
                
                # Check for test patterns in any field
                is_test = (
                    'test' in client_name or 'test' in notes or 'test' in name or
                    'cli test' in client_name or 'cli test' in notes or
                    'cli integration' in client_name or 'cli integration' in notes or
                    'cli comprehensive' in client_name or 'cli comprehensive' in notes
                )
                
                if is_test:
                    test_keys.append({
                        'id': key_id,
                        'client_name': client_name_val or 'N/A',
                        'notes': notes_raw or 'N/A',
                        'name': name_val or 'N/A',
                        'api_key': (api_key_val[:20] + '...') if api_key_val else 'N/A',
                        'reason': 'Contains test-related text',
                        'db_type': 'sqlite'
                    })
            
            return test_keys
        except Exception as e:
            logger.error(f"Error getting test API keys from SQLite: {e}")
            return []
    
    def get_test_api_keys(self) -> List[Dict[str, Any]]:
        """Get all test API keys from all configured databases"""
        test_keys = []
        
        if not self.sqlite_only:
            test_keys.extend(self.get_test_api_keys_mongodb())
        
        if not self.mongodb_only:
            test_keys.extend(self.get_test_api_keys_sqlite())
        
        return test_keys
    
    def delete_api_key_mongodb(self, key_id: Any, client_name: str) -> bool:
        """Delete an API key from MongoDB"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete MongoDB API key: {client_name} (ID: {key_id})")
            return True
        
        try:
            result = self.mongo_db.api_keys.delete_one({'_id': key_id})
            
            if result.deleted_count > 0:
                logger.info(f"✓ Deleted MongoDB API key: {client_name} (ID: {key_id})")
                return True
            else:
                logger.warning(f"⚠ MongoDB API key not found: {client_name} (ID: {key_id})")
                return False
        except Exception as e:
            logger.error(f"✗ Failed to delete MongoDB API key {client_name}: {e}")
            return False
    
    def delete_api_key_sqlite(self, key_id: str, client_name: str) -> bool:
        """Delete an API key from SQLite"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete SQLite API key: {client_name} (ID: {key_id})")
            return True
        
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            deleted = cursor.rowcount > 0
            
            if deleted:
                self.sqlite_conn.commit()
                logger.info(f"✓ Deleted SQLite API key: {client_name} (ID: {key_id})")
                cursor.close()
                return True
            else:
                logger.warning(f"⚠ SQLite API key not found: {client_name} (ID: {key_id})")
                cursor.close()
                return False
        except Exception as e:
            logger.error(f"✗ Failed to delete SQLite API key {client_name}: {e}")
            if self.sqlite_conn:
                self.sqlite_conn.rollback()
            return False
    
    def delete_api_key(self, key: Dict[str, Any]) -> bool:
        """Delete an API key from the appropriate database"""
        key_id = key.get('_id') or key.get('id')
        client_name = key.get('client_name')
        db_type = key.get('db_type', 'mongodb')
        
        if db_type == 'mongodb':
            return self.delete_api_key_mongodb(key_id, client_name)
        elif db_type == 'sqlite':
            return self.delete_api_key_sqlite(key_id, client_name)
        else:
            logger.warning(f"Unknown database type: {db_type}")
            return False
    
    def get_test_system_prompts_mongodb(self) -> List[Dict[str, Any]]:
        """Get all test system prompts from MongoDB"""
        if self.mongo_db is None:
            return []
        
        try:
            prompts_collection = self.mongo_db.system_prompts
            all_prompts = list(prompts_collection.find())
            
            test_prompts = []
            for prompt in all_prompts:
                name = str(prompt.get('name', '')).lower()
                
                if ('test' in name or 'cli test' in name or 'cli integration' in name or 'cli comprehensive' in name):
                    test_prompts.append({
                        'id': prompt.get('_id'),
                        'name': prompt.get('name', 'N/A'),
                        'version': prompt.get('version', 'N/A'),
                        'created_at': prompt.get('created_at', 'N/A'),
                        'db_type': 'mongodb'
                    })
            
            return test_prompts
        except Exception as e:
            logger.error(f"Error getting test system prompts from MongoDB: {e}")
            return []
    
    def get_test_system_prompts_sqlite(self) -> List[Dict[str, Any]]:
        """Get all test system prompts from SQLite"""
        if self.sqlite_conn is None:
            return []
        
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT id, name, version, created_at FROM system_prompts")
            all_prompts = cursor.fetchall()
            cursor.close()
            
            test_prompts = []
            for row in all_prompts:
                name = (row['name'] if isinstance(row, sqlite3.Row) else row[1]) or ''
                name_lower = str(name).lower()
                
                if ('test' in name_lower or 'cli test' in name_lower or 
                    'cli integration' in name_lower or 'cli comprehensive' in name_lower):
                    test_prompts.append({
                        'id': row['id'] if isinstance(row, sqlite3.Row) else row[0],
                        'name': name,
                        'version': row['version'] if isinstance(row, sqlite3.Row) else row[2],
                        'created_at': row['created_at'] if isinstance(row, sqlite3.Row) else row[3],
                        'db_type': 'sqlite'
                    })
            
            return test_prompts
        except Exception as e:
            logger.error(f"Error getting test system prompts from SQLite: {e}")
            return []
    
    def get_test_system_prompts(self) -> List[Dict[str, Any]]:
        """Get all test system prompts from all configured databases"""
        test_prompts = []
        
        if not self.sqlite_only:
            test_prompts.extend(self.get_test_system_prompts_mongodb())
        
        if not self.mongodb_only:
            test_prompts.extend(self.get_test_system_prompts_sqlite())
        
        return test_prompts
    
    def delete_system_prompt_mongodb(self, prompt_id: Any, name: str) -> bool:
        """Delete a system prompt from MongoDB"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete MongoDB system prompt: {name} (ID: {prompt_id})")
            return True
        
        try:
            result = self.mongo_db.system_prompts.delete_one({'_id': prompt_id})
            
            if result.deleted_count > 0:
                logger.info(f"✓ Deleted MongoDB system prompt: {name} (ID: {prompt_id})")
                return True
            else:
                logger.warning(f"⚠ MongoDB system prompt not found: {name} (ID: {prompt_id})")
                return False
        except Exception as e:
            logger.error(f"✗ Failed to delete MongoDB system prompt {name}: {e}")
            return False
    
    def delete_system_prompt_sqlite(self, prompt_id: str, name: str) -> bool:
        """Delete a system prompt from SQLite"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete SQLite system prompt: {name} (ID: {prompt_id})")
            return True
        
        try:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
            deleted = cursor.rowcount > 0
            
            if deleted:
                self.sqlite_conn.commit()
                logger.info(f"✓ Deleted SQLite system prompt: {name} (ID: {prompt_id})")
                cursor.close()
                return True
            else:
                logger.warning(f"⚠ SQLite system prompt not found: {name} (ID: {prompt_id})")
                cursor.close()
                return False
        except Exception as e:
            logger.error(f"✗ Failed to delete SQLite system prompt {name}: {e}")
            if self.sqlite_conn:
                self.sqlite_conn.rollback()
            return False
    
    def delete_system_prompt(self, prompt: Dict[str, Any]) -> bool:
        """Delete a system prompt from the appropriate database"""
        prompt_id = prompt.get('_id') or prompt.get('id')
        name = prompt.get('name')
        db_type = prompt.get('db_type', 'mongodb')
        
        if db_type == 'mongodb':
            return self.delete_system_prompt_mongodb(prompt_id, name)
        elif db_type == 'sqlite':
            return self.delete_system_prompt_sqlite(prompt_id, name)
        else:
            logger.warning(f"Unknown database type: {db_type}")
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
                prompt_id = prompt.get('_id') or prompt.get('id')
                logger.info(f"  • {prompt['name']} (ID: {prompt_id})")
                if prompt.get('version') != 'N/A':
                    logger.info(f"    Version: {prompt.get('version')}")
            
            if self.dry_run:
                logger.info("\n[DRY RUN MODE] No system prompts will be actually deleted")
            else:
                logger.info("\nDeleting test system prompts...")
            
            deleted_count = 0
            for prompt in test_prompts:
                if self.delete_system_prompt(prompt):
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
                    key_id = key.get('_id') or key.get('id')
                    logger.info(f"    • {key['client_name']} (ID: {key_id})")
            
            if test_related_keys:
                logger.info(f"\n  Test-related keys ({len(test_related_keys)}):")
                for key in test_related_keys:
                    key_id = key.get('_id') or key.get('id')
                    logger.info(f"    • {key['client_name']} (ID: {key_id})")
                    if key['notes'] != 'N/A' and key['notes'] != 'NULL':
                        logger.info(f"      Notes: {key['notes']}")
            
            if self.dry_run:
                logger.info("\n[DRY RUN MODE] No API keys will be actually deleted")
            else:
                logger.info("\nDeleting API keys...")
            
            deleted_count = 0
            for key in test_keys:
                if self.delete_api_key(key):
                    deleted_count += 1
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during API key cleanup: {e}")
            return 0
    
    def cleanup_all(self) -> tuple:
        """Clean up all test users, API keys, and system prompts"""
        # Connect to databases
        mongo_connected = False
        sqlite_connected = False
        
        if not self.sqlite_only:
            mongo_connected = self.connect_to_mongodb()
        
        if not self.mongodb_only:
            sqlite_connected = self.connect_to_sqlite()
        
        if not mongo_connected and not sqlite_connected:
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
                    status = "✓" if user.get('active', True) else "✗"
                    user_id = user.get('_id') or user.get('id')
                    db_type = user.get('db_type', 'mongodb')
                    logger.info(f"  {status} {user['username']} (ID: {user_id}, Role: {user.get('role', 'N/A')}, DB: {db_type})")
                
                if self.dry_run:
                    logger.info("\n[DRY RUN MODE] No users will be actually deleted")
                else:
                    logger.info("\nDeleting test users...")
                
                deleted_users = 0
                for user in test_users:
                    if self.delete_user(user):
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
            if self.mongo_client:
                self.mongo_client.close()
                logger.debug("Closed MongoDB connection")
            if self.sqlite_conn:
                self.sqlite_conn.close()
                logger.debug("Closed SQLite connection")
    
    def show_all_users(self):
        """Show all users in the databases"""
        # Connect to databases
        if not self.sqlite_only:
            if not self.connect_to_mongodb():
                logger.warning("Could not connect to MongoDB")
        
        if not self.mongodb_only:
            if not self.connect_to_sqlite():
                logger.warning("Could not connect to SQLite")
        
        try:
            all_users = []
            
            # Get MongoDB users
            if not self.sqlite_only and self.mongo_db:
                try:
                    mongodb_users = list(self.mongo_db.users.find())
                    for user in mongodb_users:
                        user['db_type'] = 'mongodb'
                        all_users.append(user)
                except Exception as e:
                    logger.warning(f"Error getting MongoDB users: {e}")
            
            # Get SQLite users
            if not self.mongodb_only and self.sqlite_conn:
                try:
                    cursor = self.sqlite_conn.cursor()
                    cursor.execute("SELECT id, username, role, active FROM users")
                    sqlite_users = cursor.fetchall()
                    cursor.close()
                    
                    for row in sqlite_users:
                        all_users.append({
                            'id': row['id'] if isinstance(row, sqlite3.Row) else row[0],
                            'username': row['username'] if isinstance(row, sqlite3.Row) else row[1],
                            'role': row['role'] if isinstance(row, sqlite3.Row) else row[2],
                            'active': bool(row['active']) if isinstance(row, sqlite3.Row) else bool(row[3]),
                            'db_type': 'sqlite'
                        })
                except Exception as e:
                    logger.warning(f"Error getting SQLite users: {e}")
            
            if not all_users:
                logger.info("No users found in databases")
                return
            
            logger.info(f"\nAll users in databases ({len(all_users)} total):")
            logger.info("-" * 60)
            
            test_patterns = ["testuser_", "cli_comprehensive_", "pwd_test_", 
                           "defaultuser_", "user_to_delete_", "lookup_test_", 
                           "activation_test_", "debug_test_user_", 
                           "test_activation_user", "test_user"]
            
            for user in all_users:
                username = user.get('username', 'N/A')
                user_id = user.get('_id') or user.get('id', 'N/A')
                role = user.get('role', 'N/A')
                active = user.get('active', True)
                db_type = user.get('db_type', 'unknown')
                status = "✓" if active else "✗"
                
                is_test = any(pattern in username for pattern in test_patterns)
                test_marker = " [TEST USER]" if is_test else ""
                
                logger.info(f"  {status} {username}{test_marker} [{db_type}]")
                logger.info(f"     ID: {user_id}, Role: {role}")
            
            logger.info("-" * 60)
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
        finally:
            if self.mongo_client:
                self.mongo_client.close()
            if self.sqlite_conn:
                self.sqlite_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Direct database cleanup of test users, API keys, and system prompts")
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
    parser.add_argument("--mongodb-only", action="store_true",
                       help="Only clean up MongoDB database")
    parser.add_argument("--sqlite-only", action="store_true",
                       help="Only clean up SQLite database")
    
    args = parser.parse_args()
    
    cleanup = DirectTestUserCleanup(
        dry_run=args.dry_run, 
        verbose=args.verbose,
        mongodb_only=args.mongodb_only,
        sqlite_only=args.sqlite_only
    )
    
    if args.list:
        logger.info("Listing all users in databases...")
        cleanup.show_all_users()
    elif args.keys_only:
        logger.info("Starting test API key cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No API keys will be actually deleted")
        
        # Connect to databases
        if not cleanup.sqlite_only:
            cleanup.connect_to_mongodb()
        if not cleanup.mongodb_only:
            cleanup.connect_to_sqlite()
        
        deleted_keys = cleanup.cleanup_test_api_keys()
        if args.dry_run:
            logger.info(f"\nDRY RUN: Would have deleted {deleted_keys} test API keys")
        else:
            logger.info(f"\nCleanup complete: Deleted {deleted_keys} test API keys")
        
        if cleanup.mongo_client:
            cleanup.mongo_client.close()
        if cleanup.sqlite_conn:
            cleanup.sqlite_conn.close()
    elif args.prompts_only:
        logger.info("Starting test system prompt cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No system prompts will be actually deleted")
        
        # Connect to databases
        if not cleanup.sqlite_only:
            cleanup.connect_to_mongodb()
        if not cleanup.mongodb_only:
            cleanup.connect_to_sqlite()
        
        deleted_prompts = cleanup.cleanup_test_system_prompts()
        if args.dry_run:
            logger.info(f"\nDRY RUN: Would have deleted {deleted_prompts} test system prompts")
        else:
            logger.info(f"\nCleanup complete: Deleted {deleted_prompts} test system prompts")
        
        if cleanup.mongo_client:
            cleanup.mongo_client.close()
        if cleanup.sqlite_conn:
            cleanup.sqlite_conn.close()
    elif args.users_only:
        logger.info("Starting test user cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No users will be actually deleted")
        
        deleted_users, _, _ = cleanup.cleanup_all()
        if args.dry_run:
            logger.info(f"\nDRY RUN: Would have deleted {deleted_users} test users")
        else:
            logger.info(f"\nCleanup complete: Deleted {deleted_users} test users")
    else:
        logger.info("Starting test data cleanup...")
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