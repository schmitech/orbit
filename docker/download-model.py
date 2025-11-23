#!/usr/bin/env python3
"""
Download gemma3-1b model if not already present.
This script is used during Docker build to conditionally download the model.
"""
import json
import sys
import os
import subprocess

def main():
    # Load model configuration
    config_path = '/orbit/install/gguf-models.json'
    model_name = 'gemma3-1b'
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f'Error: {config_path} not found', file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f'Error: Failed to parse {config_path}: {e}', file=sys.stderr)
        sys.exit(1)
    
    if model_name not in config['models']:
        print(f'Warning: {model_name} not found in config', file=sys.stderr)
        sys.exit(1)
    
    model_info = config['models'][model_name]
    repo_id = model_info['repo_id']
    filename = model_info['filename']
    model_path = f'/orbit/models/{filename}'
    
    # Check if model already exists
    if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
        file_size = os.path.getsize(model_path)
        print(f'Model {filename} already exists at {model_path}, skipping download')
        print(f'File size: {file_size:,} bytes')
        sys.exit(0)
    
    # Download the model
    print(f'Downloading {model_name} from {repo_id}...')
    result = subprocess.run(
        [
            'python3',
            '/orbit/install/download_hf_gguf_model.py',
            '--repo-id', repo_id,
            '--filename', filename,
            '--output-dir', '/orbit/models'
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f'Error: {result.stderr}', file=sys.stderr)
        sys.exit(1)
    
    print(f'Successfully downloaded {filename}')

if __name__ == '__main__':
    main()

