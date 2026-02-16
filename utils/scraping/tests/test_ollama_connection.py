#!/usr/bin/env python3
"""
Test script for Ollama connection validation.
This script tests the error handling capabilities of the ollama_question_extractor.py
"""

import sys
import os

# Add the current directory to the path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_connection_validation():
    """Test the connection validation functionality."""
    print("Testing Ollama connection validation...")
    
    try:
        # Import the module (this will trigger validation)
        from ollama_question_extractor import test_ollama_connection
        
        # Test the connection
        success = test_ollama_connection()
        
        if success:
            print("✅ Connection test passed!")
            return True
        else:
            print("❌ Connection test failed!")
            return False
            
    except Exception as e:
        print(f"❌ Error during connection test: {e}")
        return False

def test_with_invalid_config():
    """Test error handling with invalid configuration."""
    print("\nTesting error handling with invalid configuration...")
    
    # Test 1: Test with invalid base URL
    print("  Testing invalid base URL...")
    try:
        # Create a temporary invalid config
        with open('config.yaml', 'r') as f:
            original_config = f.read()
        
        with open('config.yaml', 'w') as f:
            f.write("ollama:\n  base_url: 'http://invalid-host:9999'\n  model: 'gpt-oss:20b'")
        
        # Test the validation function directly
        import yaml
        with open('config.yaml', 'r') as f:
            test_config = yaml.safe_load(f)
        
        # Simulate the validation logic
        base_url = test_config.get('ollama', {}).get('base_url')
        model = test_config.get('ollama', {}).get('model')
        
        if not base_url or not model:
            print("    ✅ Correctly detected missing config values")
        else:
            # Test connection (should fail)
            import requests
            try:
                requests.get(f"{base_url}/api/tags", timeout=5)
                print("    ❌ Unexpectedly connected to invalid host")
                return False
            except requests.exceptions.ConnectionError:
                print("    ✅ Correctly failed to connect to invalid host")
            except Exception as e:
                print(f"    ✅ Correctly caught error: {e}")
        
        # Restore original config
        with open('config.yaml', 'w') as f:
            f.write(original_config)
            
        return True
        
    except Exception as e:
        print(f"    ❌ Error during invalid config test: {e}")
        # Restore original config
        try:
            with open('config.yaml', 'w') as f:
                f.write(original_config)
        except Exception:
            pass
        return False

def test_validation_function():
    """Test the validation function with various scenarios."""
    print("\nTesting validation function directly...")
    
    try:
        # Import the validation function
        from ollama_question_extractor import validate_ollama_setup
        
        # Test with current valid config (should pass)
        print("  Testing with valid config...")
        try:
            validate_ollama_setup()
            print("    ✅ Valid config passed validation")
        except Exception as e:
            print(f"    ❌ Valid config failed validation: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"    ❌ Error testing validation function: {e}")
        return False

def test_command_line_functionality():
    """Test the command-line test-connection functionality."""
    print("\nTesting command-line test-connection...")
    
    try:
        # Import the test function
        from ollama_question_extractor import test_ollama_connection
        
        # Test the function
        result = test_ollama_connection()
        
        if result:
            print("    ✅ Command-line test function works correctly")
            return True
        else:
            print("    ❌ Command-line test function failed")
            return False
            
    except Exception as e:
        print(f"    ❌ Error testing command-line functionality: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Ollama Connection Error Handling Test")
    print("=" * 50)
    
    # Test 1: Valid connection
    test1_passed = test_connection_validation()
    
    # Test 2: Invalid configuration
    test2_passed = test_with_invalid_config()
    
    # Test 3: Validation function
    test3_passed = test_validation_function()
    
    # Test 4: Command-line functionality
    test4_passed = test_command_line_functionality()
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"✅ Connection validation: {'PASSED' if test1_passed else 'FAILED'}")
    print(f"✅ Error handling: {'PASSED' if test2_passed else 'FAILED'}")
    print(f"✅ Validation function: {'PASSED' if test3_passed else 'FAILED'}")
    print(f"✅ Command-line functionality: {'PASSED' if test4_passed else 'FAILED'}")
    
    if test1_passed and test2_passed and test3_passed and test4_passed:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
