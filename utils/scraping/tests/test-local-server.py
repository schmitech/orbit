#!/usr/bin/env python3
"""
Simple HTTP Server for Testing

This script creates a local HTTP server to serve the test HTML file.
Useful for testing the firecrawl-url-extractor.py locally before using Firecrawl.

Usage:
    python test-local-server.py [port]

Default port is 8000.
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Default port
    port = 8000
    
    # Check if port is provided as command line argument
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            print("Using default port 8000")
    
    # Create the server
    handler = http.server.SimpleHTTPRequestHandler
    
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"Server started at http://localhost:{port}")
            print(f"Serving files from: {os.getcwd()}")
            print(f"Test HTML file available at: http://localhost:{port}/test-website.html")
            print("\nPress Ctrl+C to stop the server")
            print("-" * 50)
            
            # List available files
            print("Available files:")
            for file in os.listdir('.'):
                if file.endswith('.html'):
                    print(f"  - {file}")
            print("-" * 50)
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"Port {port} is already in use. Try a different port:")
            print(f"  python test-local-server.py {port + 1}")
        else:
            print(f"Error starting server: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
