#!/usr/bin/env python3
"""
Remove Empty Markdown Files

This script analyzes markdown files in a directory and removes those with insufficient content.
It filters out files that only contain frontmatter, navigation links, or minimal content.

Usage:
    python remove_empty_md.py --directory /path/to/md/files [--dry-run] [--min-content-length 100]

Features:
- Removes frontmatter (YAML between --- markers)
- Filters out navigation links and common non-content elements
- Configurable minimum content length
- Dry-run mode to preview what would be deleted
- Detailed logging of what's being removed and why
"""

import os
import re
import argparse
import glob
from pathlib import Path


def remove_frontmatter(content):
    """Remove YAML frontmatter from markdown content."""
    # Remove content between --- markers at the beginning
    lines = content.split('\n')
    if lines and lines[0].strip() == '---':
        try:
            end_index = lines[1:].index('---') + 1
            return '\n'.join(lines[end_index + 1:])
        except ValueError:
            # No closing --- found, return original content
            return content
    return content


def clean_content(content):
    """Clean markdown content by removing navigation and non-content elements."""
    # Remove common navigation elements
    patterns_to_remove = [
        r'\[Skip to content\].*',  # Skip to content links
        r'\[Read More ›\].*',      # Read more links
        r'\[.*?\]\(.*?\)',         # Any markdown links
        r'!\[.*?\]\(.*?\)',        # Image markdown
        r'^\s*[-*]\s*$',           # Empty list items
        r'^\s*$',                  # Empty lines
        r'^\s*#\s*$',             # Empty headings
    ]
    
    cleaned = content
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE)
    
    # Remove multiple consecutive empty lines
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
    
    return cleaned.strip()


def analyze_markdown_file(file_path, min_content_length=100):
    """
    Analyze a markdown file to determine if it has sufficient content.
    
    Args:
        file_path (str): Path to the markdown file
        min_content_length (int): Minimum content length required
        
    Returns:
        tuple: (has_content, content_length, reason)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove frontmatter
        content_without_frontmatter = remove_frontmatter(content)
        
        # Clean the content
        cleaned_content = clean_content(content_without_frontmatter)
        
        # Calculate content length
        content_length = len(cleaned_content)
        
        # Check if content is sufficient
        if content_length < min_content_length:
            return False, content_length, f"Content too short ({content_length} chars, need {min_content_length})"
        
        # Check if content is mostly empty after cleaning
        if not cleaned_content or cleaned_content.isspace():
            return False, content_length, "No meaningful content after cleaning"
        
        # Check if content has substantial structure (headings, paragraphs, lists)
        has_headings = bool(re.search(r'^#{1,6}\s+', cleaned_content, re.MULTILINE))
        has_paragraphs = bool(re.search(r'\n\s*\n', cleaned_content))
        has_lists = bool(re.search(r'^\s*[-*+]\s+', cleaned_content, re.MULTILINE))
        
        if not (has_headings or has_paragraphs or has_lists):
            return False, content_length, "No substantial content structure (headings, paragraphs, lists)"
        
        return True, content_length, "Sufficient content"
        
    except Exception as e:
        return False, 0, f"Error reading file: {e}"


def process_directory(directory, min_content_length=100, dry_run=False):
    """
    Process all markdown files in a directory.
    
    Args:
        directory (str): Directory path to process
        min_content_length (int): Minimum content length required
        dry_run (bool): If True, don't actually delete files
    """
    directory_path = Path(directory)
    if not directory_path.exists() or not directory_path.is_dir():
        print(f"Error: {directory} is not a valid directory")
        return
    
    # Find all markdown files
    md_files = list(directory_path.glob('*.md'))
    print(f"Found {len(md_files)} markdown files in {directory}")
    print(f"Minimum content length required: {min_content_length} characters")
    print(f"Mode: {'DRY RUN' if dry_run else 'ACTUAL DELETION'}")
    print("-" * 60)
    
    files_to_remove = []
    files_to_keep = []
    
    for md_file in md_files:
        has_content, content_length, reason = analyze_markdown_file(md_file, min_content_length)
        
        if has_content:
            files_to_keep.append((md_file, content_length, reason))
            print(f"✓ KEEP: {md_file.name} ({content_length} chars) - {reason}")
        else:
            files_to_remove.append((md_file, content_length, reason))
            print(f"✗ REMOVE: {md_file.name} ({content_length} chars) - {reason}")
    
    print("-" * 60)
    print(f"Summary: {len(files_to_keep)} files to keep, {len(files_to_remove)} files to remove")
    
    if files_to_remove:
        if dry_run:
            print("\nFiles that would be removed (dry run):")
            for file_path, content_length, reason in files_to_remove:
                print(f"  - {file_path.name}: {reason}")
        else:
            print("\nRemoving files...")
            for file_path, content_length, reason in files_to_remove:
                try:
                    os.remove(file_path)
                    print(f"  ✓ Removed: {file_path.name}")
                except Exception as e:
                    print(f"  ✗ Error removing {file_path.name}: {e}")
    
    if not dry_run:
        print(f"\nOperation completed. {len(files_to_remove)} files removed.")


def main():
    parser = argparse.ArgumentParser(
        description='Remove markdown files with insufficient content',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--directory', '-d',
        required=True,
        help='Directory containing markdown files to process'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be deleted without actually deleting'
    )
    parser.add_argument(
        '--min-content-length',
        type=int,
        default=100,
        help='Minimum content length required (default: 100 characters)'
    )
    
    args = parser.parse_args()
    
    process_directory(
        directory=args.directory,
        min_content_length=args.min_content_length,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    main()
