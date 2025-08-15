#!/usr/bin/env python3
"""
Cleanup Test Users Script
=========================

This script cleans up test users that may have been left behind by CLI integration tests.
It can be run manually to clean up any lingering test users in the MongoDB database.

Usage:
    python cleanup_test_users.py [--dry-run] [--verbose]

Options:
    --dry-run    Show what would be deleted without actually deleting
    --verbose    Show detailed output
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
ORBIT_CLI = PROJECT_ROOT / "bin" / "orbit.py"


class TestUserCleanup:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.logged_in = False
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
    
    def run_command(self, command: List[str], timeout: int = 30) -> Dict[str, Any]:
        """Run a CLI command and return result"""
        full_command = ["python", str(ORBIT_CLI)] + command
        if self.verbose:
            logger.debug(f"Running: {' '.join(full_command)}")
        
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=PROJECT_ROOT
            )
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Command timed out",
                "success": False
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    def extract_json_from_output(self, output: str) -> Optional[List[Dict[str, Any]]]:
        """Extract JSON from CLI output"""
        try:
            lines = output.strip().split('\n')
            json_lines = []
            
            # Look for the start of JSON
            json_started = False
            brace_count = 0
            bracket_count = 0
            
            for line in lines:
                stripped_line = line.strip()
                
                if not json_started:
                    if stripped_line.startswith('{') or stripped_line.startswith('['):
                        json_started = True
                    else:
                        continue
                
                if json_started:
                    json_lines.append(line)
                    
                    # Count braces and brackets
                    for char in stripped_line:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                        elif char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                    
                    if json_started and brace_count == 0 and bracket_count == 0:
                        break
            
            if json_lines:
                json_text = '\n'.join(json_lines)
                return json.loads(json_text)
                
        except Exception as e:
            logger.debug(f"Error extracting JSON: {e}")
        
        # Fallback: try to parse the entire output as JSON
        try:
            return json.loads(output.strip())
        except:
            return None
    
    def login(self) -> bool:
        """Login with admin credentials"""
        # First check if already authenticated
        logger.info("Checking authentication status...")
        auth_result = self.run_command(["auth-status"])
        if auth_result["success"] and "authenticated" in auth_result["stdout"].lower():
            self.logged_in = True
            logger.info("✓ Already authenticated")
            return True
        
        logger.info("Logging in with admin credentials...")
        result = self.run_command([
            "login",
            "--username", "admin",
            "--password", "admin123"
        ])
        
        if result["success"]:
            self.logged_in = True
            logger.info("✓ Login successful")
            return True
        else:
            logger.error(f"✗ Login failed: {result['stderr']}")
            return False
    
    def logout(self):
        """Logout"""
        if self.logged_in:
            self.run_command(["logout"])
            self.logged_in = False
            logger.info("Logged out")
    
    def get_users(self) -> List[Dict[str, Any]]:
        """Get list of all users"""
        result = self.run_command(["user", "list", "--output", "json"])
        if result["success"]:
            users_data = self.extract_json_from_output(result["stdout"])
            if users_data and isinstance(users_data, list):
                return users_data
            else:
                logger.warning("Could not parse user list JSON")
                return []
        else:
            logger.error(f"Failed to get user list: {result['stderr']}")
            return []
    
    def delete_user(self, user_id: str, username: str) -> bool:
        """Delete a user"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete user: {username} (ID: {user_id})")
            return True
        
        result = self.run_command(["user", "delete", "--user-id", user_id, "--force"])
        if result["success"]:
            logger.info(f"✓ Deleted user: {username} (ID: {user_id})")
            return True
        else:
            logger.error(f"✗ Failed to delete user {username}: {result['stderr']}")
            return False
    
    def cleanup_test_users(self) -> int:
        """Clean up test users and return count of deleted users"""
        if not self.login():
            logger.error("Cannot proceed without login")
            return 0
        
        try:
            users = self.get_users()
            if not users:
                logger.info("No users found")
                return 0
            
            # Define test patterns
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
            
            deleted_count = 0
            test_users_found = []
            
            # Find test users
            for user in users:
                username = user.get('username', '')
                if username == 'admin':  # Skip admin user
                    continue
                
                if any(pattern in username for pattern in test_patterns):
                    test_users_found.append(user)
            
            if not test_users_found:
                logger.info("No test users found to clean up")
                return 0
            
            logger.info(f"Found {len(test_users_found)} test users to clean up:")
            for user in test_users_found:
                username = user.get('username', 'N/A')
                user_id = user.get('_id') or user.get('id', 'N/A')
                logger.info(f"  - {username} (ID: {user_id})")
            
            # Delete test users
            for user in test_users_found:
                username = user.get('username', '')
                user_id = user.get('_id') or user.get('id')
                
                if user_id:
                    if self.delete_user(user_id, username):
                        deleted_count += 1
                else:
                    logger.warning(f"⚠ No user ID found for {username}")
            
            return deleted_count
            
        finally:
            self.logout()
    
    def show_current_users(self):
        """Show current users without deleting anything"""
        if not self.login():
            logger.error("Cannot proceed without login")
            return
        
        try:
            users = self.get_users()
            if not users:
                logger.info("No users found")
                return
            
            logger.info(f"Current users ({len(users)} total):")
            for user in users:
                username = user.get('username', 'N/A')
                user_id = user.get('_id') or user.get('id', 'N/A')
                role = user.get('role', 'N/A')
                active = user.get('active', True)
                status = "✓" if active else "✗"
                logger.info(f"  {status} {username} (ID: {user_id}, Role: {role})")
                
        finally:
            self.logout()


def main():
    parser = argparse.ArgumentParser(description="Clean up test users from CLI integration tests")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--list", action="store_true", help="List current users without deleting anything")
    
    args = parser.parse_args()
    
    cleanup = TestUserCleanup(dry_run=args.dry_run, verbose=args.verbose)
    
    if args.list:
        logger.info("Listing current users...")
        cleanup.show_current_users()
    else:
        logger.info("Starting test user cleanup...")
        if args.dry_run:
            logger.info("DRY RUN MODE - No users will be actually deleted")
        
        deleted_count = cleanup.cleanup_test_users()
        
        if args.dry_run:
            logger.info(f"DRY RUN: Would have deleted {deleted_count} test users")
        else:
            logger.info(f"Cleanup complete: Deleted {deleted_count} test users")


if __name__ == "__main__":
    main() 