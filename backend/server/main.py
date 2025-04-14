"""
Open Inference Server - Main Application
=======================================

Entry point for the Open Inference Server application.
This script creates and runs the InferenceServer class.

Usage:
    python main.py [--config CONFIG_PATH]
"""

import argparse
from server import InferenceServer

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Open Inference Server')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    return parser.parse_args()

def main():
    """Main entry point for the application."""
    args = parse_arguments()
    
    # Create and run the inference server
    server = InferenceServer(config_path=args.config)
    server.run()

if __name__ == "__main__":
    main()