#!/usr/bin/env python3
"""
Download GGUF models from Hugging Face for llama-cpp-python.

This script downloads GGUF (GPT-Generated Unified Format) model files from Hugging Face Hub
and prepares them for use with the llama-cpp-python library. It handles downloading of
quantized models that are optimized for CPU inference.

GGUF is a file format for storing models for inference with GGML and executors based on GGML.
These models are typically quantized (compressed) versions of larger models that can run
efficiently on consumer hardware without requiring a GPU.

Examples of free models (no authentication required):
    
    # Download TinyLlama Chat (very small and fast, ~600MB)
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "*q4_0.gguf"
    
    # Download TinyLlama Chat (very small and fast, ~600MB)
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "*q4_0.gguf"
    
    # Download Phi-2 model (Microsoft, ~1.5GB)
    python download_hf_gguf_model.py --repo-id "TheBloke/phi-2-GGUF" --filename "*q4_0.gguf"
    
    # Download Code Llama 7B (good for code generation, ~4GB)
    python download_hf_gguf_model.py --repo-id "TheBloke/CodeLlama-7B-Instruct-GGUF" --filename "*q4_0.gguf"
    
    # Download Mistral 7B (popular general-purpose model, ~4GB)
    python download_hf_gguf_model.py --repo-id "TheBloke/Mistral-7B-Instruct-v0.1-GGUF" --filename "*q4_0.gguf"
    
    # Download Zephyr 7B Beta (fine-tuned for chat, ~4GB)
    python download_hf_gguf_model.py --repo-id "TheBloke/zephyr-7B-beta-GGUF" --filename "*q4_0.gguf"
    
    # List all available files in a repository before downloading
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --list-files
    
    # Download to a specific directory (creates directory if it doesn't exist)
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --output-dir "./gguf"
    python download_hf_gguf_model.py --repo-id "microsoft/phi-2-GGUF" --output-dir "./my_models/chat"
    python download_hf_gguf_model.py --repo-id "TheBloke/CodeLlama-7B-Instruct-GGUF" --output-dir "../models/code"
    
    # Download a specific file by exact name
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "tinyllama-1.1b-chat-v1.0.q4_0.gguf"

Directory handling:
    The script automatically creates the output directory and any parent directories
    if they don't exist. Examples:
    - "./gguf" - Creates gguf folder in current directory
    - "./models/gguf/chat" - Creates nested directory structure
    - "../shared_models" - Creates directory relative to parent folder
    
    No need to manually create directories before running the script.

Quantization levels explained:
    - q2_k: Smallest size, lowest quality (~2-3 bits per weight)
    - q3_k_m: Small size, good quality (~3-4 bits per weight)
    - q4_0, q4_k_m: Good balance of size and quality (~4 bits per weight) [RECOMMENDED]
    - q5_0, q5_k_m: Larger size, better quality (~5 bits per weight)
    - q6_k: Large size, high quality (~6 bits per weight)
    - q8_0: Largest size, best quality (~8 bits per weight)

For most use cases, q4_0 or q4_k_m provide the best balance of model size and performance.

Repository naming conventions:
    - TheBloke/*-GGUF: Popular quantized versions of many models
    - microsoft/*-GGUF: Official Microsoft model quantizations
    - Original model authors sometimes provide GGUF versions directly

Requirements:
    pip install requests tqdm pyyaml

**Important Note about Model Access:**
    Some models on Hugging Face require authentication or accepting terms of use:
    
    - **Public models** (like TheBloke repositories) can be downloaded directly with this script
    - **Gated models** (like Meta's Llama models) require:
      1. Creating a Hugging Face account at https://huggingface.co
      2. Accepting the model's license/terms on the model page
      3. Using the Hugging Face CLI instead of this script
    
    For gated models, use the official Hugging Face CLI:
      pip install huggingface-hub
      huggingface-cli login  # Enter your HF token
      huggingface-cli download "meta-llama/Llama-2-7b-chat-hf" --include="*.gguf"
    
    If you get a 401 Unauthorized error, the model likely requires authentication.
    This script is designed for public, freely accessible GGUF repositories.

Requirements:
    pip install requests tqdm pyyaml

Usage with llama-cpp-python:
    After downloading, you can use the model with llama-cpp-python:
    
    from llama_cpp import Llama
    
    # Load the downloaded model
    llm = Llama(model_path="./models/your-downloaded-model.gguf")
    
    # Generate text
    output = llm("Hello, how are you?", max_tokens=100)
    print(output['choices'][0]['text'])
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

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def setup_argparse():
    """
    Setup command line argument parsing with detailed help.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description='Download GGUF models from Hugging Face for llama-cpp-python',
        epilog='''
Examples:
  %(prog)s --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "*q4_0.gguf"
  %(prog)s --repo-id "microsoft/phi-2-GGUF" --list-files
  %(prog)s --repo-id "TheBloke/Mistral-7B-Instruct-v0.1-GGUF" --output-dir "./models"
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--repo-id',
        type=str,
        required=True,
        help='Hugging Face repository ID. Examples: '
             '"TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", '
             '"microsoft/phi-2-GGUF", '
             '"TheBloke/Mistral-7B-Instruct-v0.1-GGUF"'
    )
    
    parser.add_argument(
        '--filename',
        type=str,
        default="*q4_0.gguf",
        help='Filename pattern or exact file name to download. '
             'Use wildcards like "*q4_0.gguf" to match quantization levels. '
             'Common patterns: "*q4_0.gguf", "*q4_k_m.gguf", "*q5_0.gguf" '
             '(default: %(default)s)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default="models",
        help='Directory to save the downloaded models (default: %(default)s)'
    )
    
    parser.add_argument(
        '--list-files',
        action='store_true',
        help='List all available GGUF files in the repository and exit without downloading'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging output'
    )
    
    return parser

def list_files_in_repo(repo_id):
    """
    List all files in a Hugging Face repository using the API.
    
    Args:
        repo_id (str): Hugging Face repository ID (e.g., "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
    
    Returns:
        list: List of file paths in the repository
    
    Raises:
        requests.RequestException: If the API request fails
    """
    api_url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
    
    logger.info(f"Fetching file list from: {api_url}")
    
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch repository information: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"HTTP Status: {e.response.status_code}")
            logger.error(f"Response: {e.response.text}")
        raise
    
    files = []
    try:
        repo_data = response.json()
        for item in repo_data:
            if item.get("type") == "file":
                files.append(item.get("path"))
    except (ValueError, KeyError) as e:
        logger.error(f"Failed to parse repository response: {e}")
        raise
    
    logger.info(f"Found {len(files)} files in repository")
    return files

def download_file(url, dest_path, file_name):
    """
    Download a file from URL with progress bar and resume capability.
    
    Args:
        url (str): URL to download from
        dest_path (Path): Destination path for the file
        file_name (str): Name of the file for display purposes
    
    Returns:
        bool: True if download was successful, False otherwise
    """
    # Check if file already exists and get its size
    resume_byte_pos = 0
    if dest_path.exists():
        resume_byte_pos = dest_path.stat().st_size
        logger.info(f"File partially exists ({resume_byte_pos} bytes), attempting to resume download")
    
    # Create destination directory if it doesn't exist
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Set up headers for resume capability
    headers = {}
    if resume_byte_pos > 0:
        headers['Range'] = f'bytes={resume_byte_pos}-'
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        # Get total file size
        if 'content-range' in response.headers:
            # Resuming download
            total_size = int(response.headers['content-range'].split('/')[-1])
        else:
            # New download
            total_size = int(response.headers.get('content-length', 0))
        
        # Open file in appropriate mode
        mode = 'ab' if resume_byte_pos > 0 else 'wb'
        
        # Setup progress bar
        progress_bar = tqdm(
            desc=f"Downloading {file_name}",
            initial=resume_byte_pos,
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024
        )
        
        with open(dest_path, mode) as file:
            for chunk in response.iter_content(chunk_size=1024*1024):  # 1MB chunks
                if chunk:  # Filter out keep-alive chunks
                    file.write(chunk)
                    progress_bar.update(len(chunk))
        
        progress_bar.close()
        
        # Verify download completion
        final_size = dest_path.stat().st_size
        if total_size > 0 and final_size != total_size:
            logger.error(f"Download incomplete: expected {total_size} bytes, got {final_size} bytes")
            return False
        
        logger.info(f"Successfully downloaded {file_name} ({final_size:,} bytes)")
        return True
        
    except requests.RequestException as e:
        logger.error(f"Download failed: {e}")
        return False
    except IOError as e:
        logger.error(f"File write error: {e}")
        return False

def find_matching_file(files, pattern):
    """
    Find a file that matches the given pattern.
    
    Args:
        files (list): List of available files
        pattern (str): Pattern to match (supports wildcards)
    
    Returns:
        str or None: Matching file path, or None if no match found
    """
    import fnmatch
    
    # Filter to only GGUF files first
    gguf_files = [f for f in files if f.lower().endswith('.gguf')]
    
    # Make pattern lowercase for case-insensitive matching
    pattern_lower = pattern.lower()
    
    if '*' in pattern or '?' in pattern:
        # Wildcard match (case-insensitive)
        matching_files = [f for f in gguf_files if fnmatch.fnmatch(f.lower(), pattern_lower)]
        if matching_files:
            # Sort alphabetically and pick the first one
            matching_files.sort()
            logger.info(f"Pattern '{pattern}' matched {len(matching_files)} files, selecting: {matching_files[0]}")
            return matching_files[0]
    else:
        # Exact match (case-insensitive)
        for file in gguf_files:
            if file.lower() == pattern_lower or file.lower().endswith('/' + pattern_lower):
                return file
    
    return None

def format_file_size(size_bytes):
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes (int): Size in bytes
    
    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.1f} PB"

def main():
    """
    Main function to download GGUF models from Hugging Face.
    
    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    parser = setup_argparse()
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate and create output directory
    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {output_dir.absolute()}")
    except OSError as e:
        logger.error(f"Cannot create output directory {output_dir}: {e}")
        return 1
    
    repo_id = args.repo_id
    filename_pattern = args.filename
    
    # Validate repository ID format
    if '/' not in repo_id:
        logger.error(f"Invalid repository ID format: {repo_id}")
        logger.error("Repository ID should be in format 'username/repository-name'")
        return 1
    
    logger.info(f"Repository: {repo_id}")
    logger.info(f"Filename pattern: {filename_pattern}")
    
    try:
        # List files in the repository
        files = list_files_in_repo(repo_id)
        
        if not files:
            logger.error(f"No files found in repository {repo_id}")
            logger.error("This could mean:")
            logger.error("  - The repository doesn't exist")
            logger.error("  - The repository is private")
            logger.error("  - There's a network connectivity issue")
            return 1
        
        # Filter for GGUF files
        gguf_files = [f for f in files if f.lower().endswith('.gguf')]
        
        if not gguf_files:
            logger.error(f"No GGUF files found in repository {repo_id}")
            logger.info("This repository might not contain quantized models.")
            logger.info("Try looking for repositories with '-GGUF' in the name.")
            return 1
        
        # If listing files, display them and exit
        if args.list_files:
            print(f"\nAvailable GGUF files in {repo_id}:")
            print("-" * 60)
            for file in sorted(gguf_files):
                print(f"  {file}")
            print(f"\nTotal: {len(gguf_files)} GGUF files")
            print("\nTo download a specific file, use:")
            print(f"  python {sys.argv[0]} --repo-id \"{repo_id}\" --filename \"<filename>\"")
            return 0
        
        # Find matching file
        matching_file = find_matching_file(files, filename_pattern)
        
        if not matching_file:
            logger.error(f"No file matching pattern '{filename_pattern}' found in repository {repo_id}")
            logger.info("\nAvailable GGUF files:")
            for file in sorted(gguf_files)[:10]:  # Show first 10 files
                logger.info(f"  {file}")
            if len(gguf_files) > 10:
                logger.info(f"  ... and {len(gguf_files) - 10} more files")
            logger.info(f"\nUse --list-files to see all available files")
            return 1
        
        # Prepare download
        file_url = f"https://huggingface.co/{repo_id}/resolve/main/{matching_file}"
        dest_path = output_dir / Path(matching_file).name
        
        logger.info(f"Downloading: {matching_file}")
        logger.info(f"Destination: {dest_path}")
        logger.info(f"URL: {file_url}")
        
        # Download the file
        success = download_file(file_url, dest_path, Path(matching_file).name)
        
        if success:
            file_size = dest_path.stat().st_size
            logger.info(f"✅ Successfully downloaded model to: {dest_path}")
            logger.info(f"📁 File size: {format_file_size(file_size)}")
            logger.info(f"🚀 To use this model with llama-cpp-python:")
            logger.info(f"     from llama_cpp import Llama")
            logger.info(f"     llm = Llama(model_path='{dest_path}')")
            return 0
        else:
            logger.error("❌ Download failed")
            # Clean up partial download
            if dest_path.exists():
                dest_path.unlink()
                logger.info("Cleaned up partial download")
            return 1
            
    except KeyboardInterrupt:
        logger.info("\n⏹️ Download cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())