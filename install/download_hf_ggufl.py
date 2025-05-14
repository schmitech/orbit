#!/usr/bin/env python3
"""
Download models from Hugging Face for llama-cpp-python.

This script downloads model files from Hugging Face Hub and prepares them for use with
the llama-cpp-python library. It handles downloading and extraction of models.
"""

import os
import sys
import argparse
import logging
import requests
import shutil
from pathlib import Path
from tqdm import tqdm
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_argparse():
    """Setup command line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Download models from Hugging Face for llama-cpp-python'
    )
    
    parser.add_argument(
        '--repo-id',
        type=str,
        required=True,
        help='Hugging Face repository ID (e.g., "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")'
    )
    
    parser.add_argument(
        '--filename',
        type=str,
        default="*q4_0.gguf",
        help='Filename or exact file name to download from the repo'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default="models",
        help='Directory to save the downloaded models'
    )
    
    parser.add_argument(
        '--list-files',
        action='store_true',
        help='List available files in the repository and exit'
    )
    
    return parser

def list_files_in_repo(repo_id):
    """List all files in a Hugging Face repository."""
    url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
    response = requests.get(url)
    
    if response.status_code != 200:
        logger.error(f"Failed to list files: HTTP {response.status_code}")
        logger.error(f"Response: {response.text}")
        return []
    
    files = []
    for item in response.json():
        if item.get("type") == "file":
            files.append(item.get("path"))
    
    return files

def download_file(url, dest_path, file_name):
    """Download a file with progress bar."""
    response = requests.get(url, stream=True)
    total_size_in_bytes = int(response.headers.get('content-length', 0))
    
    # Create destination directory if it doesn't exist
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    # Show progress bar during download
    progress_bar = tqdm(
        desc=f"Downloading {file_name}",
        total=total_size_in_bytes,
        unit='iB',
        unit_scale=True
    )
    
    with open(dest_path, 'wb') as file:
        for data in response.iter_content(chunk_size=1024*1024):  # 1MB chunks
            progress_bar.update(len(data))
            file.write(data)
    
    progress_bar.close()
    
    if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
        logger.error("ERROR, something went wrong during download")
        return False
    
    return True

def find_matching_file(files, pattern):
    """Find a file that matches the pattern."""
    import fnmatch
    
    # Make pattern lowercase for case-insensitive matching
    pattern_lower = pattern.lower()
    
    if pattern.startswith('*'):
        # Wildcard match (case-insensitive)
        matching_files = [f for f in files if fnmatch.fnmatch(f.lower(), pattern_lower)]
        if matching_files:
            # Sort by size (ascending) and pick the smallest one
            return matching_files[0]
    else:
        # Exact match
        for file in files:
            if file.lower() == pattern_lower:
                return file
    
    return None

def main():
    """Main function to download models."""
    parser = setup_argparse()
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    repo_id = args.repo_id
    filename = args.filename
    
    # List files in the repository
    logger.info(f"Listing files in repository: {repo_id}")
    try:
        files = list_files_in_repo(repo_id)
        
        if not files:
            logger.error(f"No files found in repository {repo_id}")
            return 1
        
        gguf_files = [f for f in files if f.endswith('.gguf')]
        
        if args.list_files:
            print(f"Files available in {repo_id}:")
            for file in gguf_files:
                print(f"  {file}")
            return 0
        
        # Find matching file
        matching_file = find_matching_file(gguf_files, filename)
        
        if not matching_file:
            logger.error(f"No file matching '{filename}' found in repository {repo_id}")
            logger.info("Available GGUF files:")
            for file in gguf_files:
                logger.info(f"  {file}")
            return 1
        
        # Download the file
        file_url = f"https://huggingface.co/{repo_id}/resolve/main/{matching_file}"
        dest_path = output_dir / os.path.basename(matching_file)
        
        logger.info(f"Downloading {matching_file} to {dest_path}")
        
        success = download_file(file_url, dest_path, os.path.basename(matching_file))
        
        if success:
            logger.info(f"Successfully downloaded model to {dest_path}")
            logger.info(f"To use this model, manually update the model_path in config.yaml to: {dest_path}")
            return 0
        else:
            logger.error("Download failed")
            return 1
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 