#!/usr/bin/env python
"""
Test runner script for retriever tests
"""

import pytest
import os
import sys

# Add the server directory to path to fix import issues 
server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, server_dir)

def main():
    """Run the tests"""
    test_files = [
        "test_base_retriever.py",
        "test_retriever_types.py"
    ]
    
    # Create the full paths to the test files
    test_paths = [os.path.join(os.path.dirname(__file__), test_file) for test_file in test_files]
    
    # Run the tests
    pytest.main(['-xvs'] + test_paths)

if __name__ == "__main__":
    main() 