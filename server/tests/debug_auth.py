#!/usr/bin/env python3
"""
Debug Authentication Issues
==========================

This script helps debug authentication issues by:
1. Checking what password the server is configured to use
2. Providing options to reset the admin password
3. Checking MongoDB for existing users
"""

import os
import sys
import asyncio
import logging
from typing import Optional

# Add the server directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.mongodb_service import MongoDBService
from services.auth_service import AuthService
from config.config_manager import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def check_config_password():
    """Check what password the server is configured to use"""
    logger.info("=== Checking Server Configuration ===")
    
    try:
        # Load the config
        config = load_config()
        
        # Check auth configuration
        auth_config = config.get('auth', {})
        default_password = auth_config.get('default_admin_password', 'admin123')
        
        logger.info(f"Auth enabled: {auth_config.get('enabled', False)}")
        logger.info(f"Default admin username: {auth_config.get('default_admin_username', 'admin')}")
        logger.info(f"Default admin password: {default_password}")
        
        # Check environment variable
        env_password = os.getenv('ORBIT_DEFAULT_ADMIN_PASSWORD')
        if env_password:
            logger.info(f"ORBIT_DEFAULT_ADMIN_PASSWORD environment variable: {env_password}")
            if env_password != default_password:
                logger.warning("Environment variable password differs from config password!")
        else:
            logger.info("ORBIT_DEFAULT_ADMIN_PASSWORD environment variable: not set")
        
        return config, default_password
        
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
        return None, None


async def check_mongodb_users(config):
    """Check what users exist in MongoDB"""
    logger.info("\n=== Checking MongoDB Users ===")
    
    try:
        # Initialize MongoDB service
        mongodb_service = MongoDBService(config)
        await mongodb_service.initialize()
        
        # Get the users collection
        users_collection_name = config.get('internal_services', {}).get('mongodb', {}).get('users_collection', 'users')
        users_collection = mongodb_service.database[users_collection_name]
        
        # Find all users
        users = await users_collection.find({}).to_list(length=100)
        
        if not users:
            logger.info("No users found in MongoDB")
            return []
        
        logger.info(f"Found {len(users)} users in MongoDB:")
        for user in users:
            username = user.get('username', 'unknown')
            role = user.get('role', 'unknown')
            active = user.get('active', False)
            created_at = user.get('created_at', 'unknown')
            logger.info(f"  - Username: {username}, Role: {role}, Active: {active}, Created: {created_at}")
        
        return users
        
    except Exception as e:
        logger.error(f"Error checking MongoDB users: {str(e)}")
        return []


async def reset_admin_password(config, new_password: str):
    """Reset the admin user password"""
    logger.info(f"\n=== Resetting Admin Password to: {new_password[:3]}*** ===")
    
    try:
        # Initialize auth service
        mongodb_service = MongoDBService(config)
        await mongodb_service.initialize()
        
        auth_service = AuthService(config, mongodb_service)
        await auth_service.initialize()
        
        # Get the users collection
        users_collection_name = config.get('internal_services', {}).get('mongodb', {}).get('users_collection', 'users')
        users_collection = mongodb_service.database[users_collection_name]
        
        # Find admin user
        admin_user = await users_collection.find_one({"username": "admin"})
        
        if not admin_user:
            logger.error("Admin user not found in MongoDB")
            return False
        
        # Update the password
        salt, hash_bytes = auth_service._hash_password(new_password)
        encoded_password = auth_service._encode_password(salt, hash_bytes)
        
        result = await users_collection.update_one(
            {"username": "admin"},
            {"$set": {"password": encoded_password}}
        )
        
        if result.modified_count > 0:
            logger.info("✓ Admin password updated successfully")
            return True
        else:
            logger.error("Failed to update admin password")
            return False
        
    except Exception as e:
        logger.error(f"Error resetting admin password: {str(e)}")
        return False


async def create_admin_user(config, username: str, password: str):
    """Create a new admin user"""
    logger.info(f"\n=== Creating Admin User: {username} ===")
    
    try:
        # Initialize auth service
        mongodb_service = MongoDBService(config)
        await mongodb_service.initialize()
        
        auth_service = AuthService(config, mongodb_service)
        await auth_service.initialize()
        
        # Create the user
        user_id = await auth_service.create_user(username, password, "admin")
        
        if user_id:
            logger.info(f"✓ Admin user created successfully with ID: {user_id}")
            return True
        else:
            logger.error("Failed to create admin user")
            return False
        
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        return False


async def main():
    """Main function"""
    logger.info("Authentication Debug Script")
    logger.info("=" * 50)
    
    # Check configuration
    config, default_password = await check_config_password()
    if not config:
        return
    
    # Check existing users
    users = await check_mongodb_users(config)
    
    # Provide options
    logger.info("\n=== Available Actions ===")
    logger.info("1. Reset admin password")
    logger.info("2. Create new admin user")
    logger.info("3. Exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice == "1":
                new_password = input("Enter new password for admin user: ").strip()
                if new_password:
                    await reset_admin_password(config, new_password)
                else:
                    logger.error("Password cannot be empty")
                    
            elif choice == "2":
                username = input("Enter username for new admin user: ").strip()
                password = input("Enter password for new admin user: ").strip()
                if username and password:
                    await create_admin_user(config, username, password)
                else:
                    logger.error("Username and password cannot be empty")
                    
            elif choice == "3":
                logger.info("Exiting...")
                break
                
            else:
                logger.error("Invalid choice. Please enter 1, 2, or 3.")
                
        except KeyboardInterrupt:
            logger.info("\nExiting...")
            break
        except Exception as e:
            logger.error(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main()) 