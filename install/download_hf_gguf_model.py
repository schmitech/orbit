#!/usr/bin/env python3
"""
Download model files from Hugging Face Hub.

Supports any file format: GGUF, ONNX, safetensors, JSON config files, etc.
All files matching the --filename pattern are downloaded.

Examples:

    # Download all files from a repo (e.g. Supertonic TTS — ONNX + config files)
    python download_hf_gguf_model.py --repo-id "Supertone/supertonic-3" --output-dir "./models/supertonic-3"

    # Download a specific GGUF quantization
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "*q4_0.gguf"

    # Download Mistral 7B GGUF
    python download_hf_gguf_model.py --repo-id "TheBloke/Mistral-7B-Instruct-v0.1-GGUF" --filename "*q4_0.gguf"

    # Download all safetensors files
    python download_hf_gguf_model.py --repo-id "some-org/some-model" --filename "*.safetensors"

    # List all available files before downloading
    python download_hf_gguf_model.py --repo-id "Supertone/supertonic-3" --list-files

    # Download to a specific directory
    python download_hf_gguf_model.py --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --output-dir "./models/tinyllama"

Directory handling:
    The output directory (and any parents) is created automatically if it does not exist.

GGUF quantization levels:
    - q4_0, q4_k_m: Good balance of size and quality (~4 bits/weight) [RECOMMENDED]
    - q5_0, q5_k_m: Larger, better quality
    - q8_0: Largest, best quality

Model access:
    Public repositories are downloaded without authentication.
    Gated models require a Hugging Face account and token:
      pip install huggingface-hub
      huggingface-cli login
      huggingface-cli download "meta-llama/Llama-2-7b-chat-hf"

Requirements:
    pip install requests tqdm
"""

import sys
import argparse
import logging
import requests
from pathlib import Path
from tqdm import tqdm

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
        description='Download model files from Hugging Face Hub (GGUF, ONNX, safetensors, …)',
        epilog='''
Examples:
  %(prog)s --repo-id "Supertone/supertonic-3" --output-dir "./models/supertonic-3"
  %(prog)s --repo-id "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF" --filename "*q4_0.gguf"
  %(prog)s --repo-id "Supertone/supertonic-3" --list-files
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--repo-id',
        type=str,
        required=True,
        help='Hugging Face repository ID, e.g. "Supertone/supertonic-3" or '
             '"TheBloke/Mistral-7B-Instruct-v0.1-GGUF"'
    )

    parser.add_argument(
        '--filename',
        type=str,
        default="*",
        help='Filename pattern to download. Wildcards supported. '
             'All matching files are downloaded. '
             'Examples: "*" (all files), "*.gguf", "*q4_0.gguf", "*.onnx" '
             '(default: %(default)s)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default="models",
        help='Directory to save downloaded files (default: %(default)s)'
    )

    parser.add_argument(
        '--list-files',
        action='store_true',
        help='List all available files in the repository and exit without downloading'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging output'
    )
    
    return parser

def list_files_in_repo(repo_id):
    """
    List all files in a Hugging Face repository, recursing into subdirectories.

    Args:
        repo_id (str): Hugging Face repository ID

    Returns:
        list: List of all file paths in the repository

    Raises:
        requests.RequestException: If any API request fails
    """
    files = []
    dirs_to_visit = [""]  # empty string = repo root

    while dirs_to_visit:
        current_dir = dirs_to_visit.pop()
        path_segment = f"/{current_dir}" if current_dir else ""
        api_url = f"https://huggingface.co/api/models/{repo_id}/tree/main{path_segment}"

        logger.debug(f"Fetching tree: {api_url}")
        try:
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {api_url}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"HTTP {e.response.status_code}: {e.response.text}")
            raise

        try:
            for item in response.json():
                if item.get("type") == "file":
                    files.append(item["path"])
                elif item.get("type") == "directory":
                    dirs_to_visit.append(item["path"])
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

def find_matching_files(files, pattern):
    """
    Find all files matching the given pattern.

    Args:
        files (list): List of available file paths in the repository
        pattern (str): Glob pattern or exact filename (case-insensitive)

    Returns:
        list: Sorted list of matching file paths (may be empty)
    """
    import fnmatch

    pattern_lower = pattern.lower()

    if '*' in pattern or '?' in pattern:
        matched = sorted(f for f in files if fnmatch.fnmatch(f.lower(), pattern_lower))
    else:
        # Exact match against full path or basename
        matched = [
            f for f in files
            if f.lower() == pattern_lower or f.lower().endswith('/' + pattern_lower)
        ]

    logger.info(f"Pattern '{pattern}' matched {len(matched)} file(s)")
    return matched

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
    Download model files from a Hugging Face repository.

    Returns:
        int: Exit code (0 for success, 1 for error)
    """
    parser = setup_argparse()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {output_dir.absolute()}")
    except OSError as e:
        logger.error(f"Cannot create output directory {output_dir}: {e}")
        return 1

    repo_id = args.repo_id
    filename_pattern = args.filename

    if '/' not in repo_id:
        logger.error(f"Invalid repository ID format: {repo_id}")
        logger.error("Repository ID should be in format 'username/repository-name'")
        return 1

    logger.info(f"Repository: {repo_id}")
    logger.info(f"Filename pattern: {filename_pattern}")

    try:
        files = list_files_in_repo(repo_id)

        if not files:
            logger.error(f"No files found in repository {repo_id}")
            logger.error("This could mean the repository doesn't exist, is private, "
                         "or there's a network issue.")
            return 1

        if args.list_files:
            print(f"\nAvailable files in {repo_id}:")
            print("-" * 60)
            for file in sorted(files):
                print(f"  {file}")
            print(f"\nTotal: {len(files)} file(s)")
            print("\nTo download specific files use:")
            print(f"  python {sys.argv[0]} --repo-id \"{repo_id}\" --filename \"<pattern>\"")
            return 0

        matching_files = find_matching_files(files, filename_pattern)

        if not matching_files:
            logger.error(f"No files matching pattern '{filename_pattern}' found in {repo_id}")
            logger.info("Available files:")
            for file in sorted(files)[:10]:
                logger.info(f"  {file}")
            if len(files) > 10:
                logger.info(f"  ... and {len(files) - 10} more (use --list-files to see all)")
            return 1

        logger.info(f"Downloading {len(matching_files)} file(s) to {output_dir}")

        failed = []
        for remote_path in matching_files:
            file_url = f"https://huggingface.co/{repo_id}/resolve/main/{remote_path}"
            # Preserve subdirectory structure (e.g. onnx/model.onnx → output_dir/onnx/model.onnx)
            dest_path = output_dir / remote_path

            logger.info(f"Downloading: {remote_path}")
            success = download_file(file_url, dest_path, remote_path)

            if success:
                file_size = dest_path.stat().st_size
                logger.info(f"✅ {remote_path} ({format_file_size(file_size)})")
            else:
                logger.error(f"❌ Failed: {remote_path}")
                if dest_path.exists():
                    dest_path.unlink()
                    logger.info("Cleaned up partial download")
                failed.append(remote_path)

        if failed:
            logger.error(f"{len(failed)} file(s) failed to download: {failed}")
            return 1

        logger.info(f"✅ All {len(matching_files)} file(s) downloaded to: {output_dir.absolute()}")
        return 0

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