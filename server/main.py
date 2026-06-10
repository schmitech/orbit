"""
ORBIT Server - Main Application
=======================================

Entry point for the ORBIT server.
This script creates and runs the InferenceServer class.

Architecture Overview:
    - FastAPI-based web server with async support
    - Modular design with separate services for different functionalities
    - Support for multiple LLM providers (Ollama, HuggingFace, etc.)
    - SQL and Vector database integration for RAG capabilities
    - API key management and authentication
    - Session management
    - Logging and Health monitoring

Usage:
    python main.py [--config CONFIG_PATH]
"""

import os
import argparse
from pathlib import Path

from fastapi import FastAPI
from inference_server import InferenceServer

# Configure MongoDB logging
from utils.mongodb_utils import configure_mongodb_logging
configure_mongodb_logging()

_environment_loaded = False


def load_environment() -> None:
    """Load .env once at process startup, before configuration is read."""
    global _environment_loaded
    if _environment_loaded:
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _environment_loaded = True
        return

    current_dir = Path.cwd()
    env_paths = [
        current_dir / '.env',
        current_dir.parent / '.env',
        current_dir.parent.parent / '.env',
        Path('.env'),
    ]

    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path, override=True)
            _environment_loaded = True
            return

    _environment_loaded = True


def create_app() -> FastAPI:
    """
    Factory function to create a FastAPI application instance.
    
    This function is used by uvicorn's multiple worker mode to create
    separate application instances for each worker process.
    
    The configuration path is read from the OIS_CONFIG_PATH environment variable.
    If not set, the default configuration will be used.
    
    Returns:
        A configured FastAPI application instance
    """
    load_environment()
    config_path = os.environ.get('OIS_CONFIG_PATH')
    
    # Create server instance
    server = InferenceServer(config_path=config_path)
    
    # Return just the FastAPI app instance
    return server.app

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='ORBIT')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    return parser.parse_args()

def main():
    """Main entry point for the application."""
    args = parse_arguments()
    load_environment()
    
    # Create and run the inference server
    server = InferenceServer(config_path=args.config)
    server.run()

if __name__ == "__main__":
    main()
else:
    app: FastAPI = create_app()
