#!/usr/bin/env python3
"""
Vacuum Files Database Script
=============================

This script vacuums the SQLite database (files.db) used for file metadata to reclaim space
after deletions. VACUUM rebuilds the database file, removing unused space.

Usage:
    python vacuum_files_db.py [options]

Options:
    --dry-run       Show what would be vacuumed without actually vacuuming
    --stats-only    Only show database statistics without vacuuming
"""

import argparse
import logging
import os
import sys
import sqlite3
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FilesDatabaseVacuum:
    """Vacuum the files.db SQLite database to reclaim space."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db_path = None
        self.conn = None
        
        # Load configuration
        self.config = self._load_config()
    
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
                        logger.debug(f"Loaded config from: {config_path}")
                        return config
                except Exception as e:
                    logger.warning(f"Error loading config from {config_path}: {e}")
        
        logger.warning("Could not load config.yaml, using defaults")
        return {}
    
    def _get_db_path(self) -> Optional[str]:
        """Get database path from config"""
        try:
            # Get from config: files.metadata_db_path
            db_path = self.config.get('files', {}).get('metadata_db_path', 'files.db')
            
            # If relative path, try to find it relative to project root
            if not os.path.isabs(db_path):
                # Try project root (2 levels up from server/tests/cleanup)
                project_root = Path(__file__).parent.parent.parent.parent
                abs_path = project_root / db_path
                if abs_path.exists():
                    return str(abs_path)
                
                # Try server directory
                server_dir = Path(__file__).parent.parent.parent
                abs_path = server_dir / db_path
                if abs_path.exists():
                    return str(abs_path)
                
                # Try current directory
                if os.path.exists(db_path):
                    return os.path.abspath(db_path)
                
                # If doesn't exist, return the path anyway (will check existence later)
                return str(project_root / db_path)
            
            return db_path
        except Exception as e:
            logger.error(f"Error getting database path: {e}")
            return None
    
    def connect(self) -> bool:
        """Connect to the SQLite database"""
        try:
            self.db_path = self._get_db_path()
            if not self.db_path:
                logger.error("Could not determine database path")
                return False
            
            if not os.path.exists(self.db_path):
                logger.error(f"Database file does not exist: {self.db_path}")
                return False
            
            logger.info(f"Connecting to database: {self.db_path}")
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            
            logger.debug("Successfully connected to database")
            
            return True
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about the database"""
        try:
            stats = {}
            
            # Get database file size
            if os.path.exists(self.db_path):
                stats['file_size_bytes'] = os.path.getsize(self.db_path)
                stats['file_size_mb'] = round(stats['file_size_bytes'] / (1024 * 1024), 2)
            else:
                stats['file_size_bytes'] = 0
                stats['file_size_mb'] = 0
            
            cursor = self.conn.cursor()
            
            # Count files
            try:
                cursor.execute("SELECT COUNT(*) FROM uploaded_files")
                result = cursor.fetchone()
                stats['file_count'] = result[0] if result else 0
            except sqlite3.OperationalError:
                stats['file_count'] = 0
            
            # Count chunks
            try:
                cursor.execute("SELECT COUNT(*) FROM file_chunks")
                result = cursor.fetchone()
                stats['chunk_count'] = result[0] if result else 0
            except sqlite3.OperationalError:
                stats['chunk_count'] = 0
            
            # Get database page info
            try:
                cursor.execute("PRAGMA page_count")
                result = cursor.fetchone()
                stats['page_count'] = result[0] if result and result[0] is not None else 0
            except (TypeError, IndexError, sqlite3.OperationalError):
                stats['page_count'] = 0
            
            try:
                cursor.execute("PRAGMA page_size")
                result = cursor.fetchone()
                stats['page_size'] = result[0] if result and result[0] is not None else 4096
            except (TypeError, IndexError, sqlite3.OperationalError):
                stats['page_size'] = 4096  # Default SQLite page size
            
            # Calculate used space
            stats['estimated_used_bytes'] = stats['page_count'] * stats['page_size']
            stats['estimated_used_mb'] = round(stats['estimated_used_bytes'] / (1024 * 1024), 2) if stats['estimated_used_bytes'] > 0 else 0
            
            # Get free pages (space that can be reclaimed with VACUUM)
            try:
                cursor.execute("PRAGMA freelist_count")
                result = cursor.fetchone()
                stats['free_pages'] = result[0] if result and result[0] is not None else 0
            except (TypeError, IndexError, sqlite3.OperationalError):
                stats['free_pages'] = 0
            
            stats['estimated_free_bytes'] = stats['free_pages'] * stats['page_size']
            stats['estimated_free_mb'] = round(stats['estimated_free_bytes'] / (1024 * 1024), 2) if stats['estimated_free_bytes'] > 0 else 0
            
            # Get free list pages
            try:
                cursor.execute("PRAGMA freelist_pages")
                result = cursor.fetchone()
                stats['freelist_pages'] = result[0] if result and result[0] is not None else 0
            except (TypeError, IndexError, sqlite3.OperationalError):
                stats['freelist_pages'] = 0
            
            # Calculate fragmentation
            if stats['page_count'] > 0:
                stats['fragmentation_percent'] = round(
                    (stats['free_pages'] / stats['page_count']) * 100, 2
                )
            else:
                stats['fragmentation_percent'] = 0.0
            
            return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return {}
    
    def vacuum(self) -> bool:
        """Vacuum the database to reclaim space"""
        try:
            if self.dry_run:
                logger.info("[DRY RUN] Would vacuum database")
                return True
            
            logger.info("Starting VACUUM operation...")
            logger.info("This may take a few moments for large databases...")
            
            cursor = self.conn.cursor()
            cursor.execute("VACUUM")
            self.conn.commit()
            
            logger.info("VACUUM completed successfully")
            return True
        except Exception as e:
            logger.error(f"Error vacuuming database: {e}")
            return False
    
    def print_stats(self, stats: Dict[str, Any], label: str = "Current"):
        """Print database statistics"""
        print("\n" + "=" * 60)
        print(f"{label} Database Statistics")
        print("=" * 60)
        
        if not stats:
            print("  No statistics available")
            return
        
        print(f"  Database file: {self.db_path}")
        print(f"  File size: {stats.get('file_size_mb', 0):.2f} MB ({stats.get('file_size_bytes', 0):,} bytes)")
        print(f"  Files: {stats.get('file_count', 0):,}")
        print(f"  Chunks: {stats.get('chunk_count', 0):,}")
        print(f"  Pages: {stats.get('page_count', 0):,}")
        print(f"  Page size: {stats.get('page_size', 0):,} bytes")
        print(f"  Estimated used: {stats.get('estimated_used_mb', 0):.2f} MB ({stats.get('estimated_used_bytes', 0):,} bytes)")
        print(f"  Free pages: {stats.get('free_pages', 0):,}")
        print(f"  Estimated free space: {stats.get('estimated_free_mb', 0):.2f} MB ({stats.get('estimated_free_bytes', 0):,} bytes)")
        print(f"  Fragmentation: {stats.get('fragmentation_percent', 0):.2f}%")
        print("=" * 60)
    
    def run(self, stats_only: bool = False) -> bool:
        """Run the vacuum operation"""
        try:
            # Connect to database
            if not self.connect():
                logger.error("Failed to connect to database")
                return False
            
            # Get stats before vacuum
            logger.info("Gathering database statistics...")
            stats_before = self.get_database_stats()
            self.print_stats(stats_before, "Before VACUUM")
            
            if stats_only:
                logger.info("Stats-only mode - skipping VACUUM operation")
                return True
            
            # Check if there's any free space to reclaim
            free_mb = stats_before.get('estimated_free_mb', 0)
            if free_mb < 0.1:  # Less than 100KB
                logger.info(f"Database has minimal free space ({free_mb:.2f} MB). VACUUM may not reclaim significant space.")
            else:
                logger.info(f"Database has {free_mb:.2f} MB of free space that can be reclaimed.")
            
            # Perform vacuum
            if not self.vacuum():
                logger.error("Failed to vacuum database")
                return False
            
            # Get stats after vacuum
            logger.info("Gathering post-vacuum statistics...")
            stats_after = self.get_database_stats()
            self.print_stats(stats_after, "After VACUUM")
            
            # Calculate space reclaimed
            size_before = stats_before.get('file_size_bytes', 0)
            size_after = stats_after.get('file_size_bytes', 0)
            space_reclaimed = size_before - size_after
            
            if space_reclaimed > 0:
                reclaimed_mb = space_reclaimed / (1024 * 1024)
                logger.info(f"\n✓ Successfully reclaimed {reclaimed_mb:.2f} MB ({space_reclaimed:,} bytes)")
                reduction_percent = (space_reclaimed / size_before * 100) if size_before > 0 else 0
                logger.info(f"  Database size reduced by {reduction_percent:.2f}%")
            elif space_reclaimed == 0:
                logger.info("\n✓ VACUUM completed. No space was reclaimed (database may already be compact)")
            else:
                logger.warning(f"\n⚠ Database size increased by {abs(space_reclaimed):,} bytes (this is normal for VACUUM on active databases)")
            
            return True
            
        except Exception as e:
            logger.error(f"Error during vacuum operation: {e}")
            return False
        finally:
            self.disconnect()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Vacuum the files.db SQLite database to reclaim space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show database statistics only
  python vacuum_files_db.py --stats-only

  # Dry run (show what would happen)
  python vacuum_files_db.py --dry-run

  # Vacuum database (default)
  python vacuum_files_db.py

        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be vacuumed without actually vacuuming'
    )
    
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only show database statistics without vacuuming'
    )
    
    args = parser.parse_args()
    
    # Create vacuum instance
    vacuum = FilesDatabaseVacuum(dry_run=args.dry_run)
    
    # Run vacuum
    success = vacuum.run(stats_only=args.stats_only)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

