"""
This script is used to test the Google Gemini API.
It will try to use the model from the command line argument,
or use the model from the .env file if no argument is provided.

Usage:

python ./tests/gemini/test_google_gemini.py --model gemini-2.0-flash
"""
import os
import sys
import argparse

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

# Set up argument parser
parser = argparse.ArgumentParser(description='Test Google Gemini API')
parser.add_argument('--model', type=str, default='gemini-pro', 
                    help='The Gemini model to use (default: gemini-pro)')
args = parser.parse_args()

try:
    from dotenv import load_dotenv
    
    # Get the current file's directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Go up two directories to reach the server directory from tests/gemini/
    dotenv_path = os.path.join(current_dir, "..", "..", ".env")
    print(f"Looking for .env at: {dotenv_path}")  # Debug print
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from: {dotenv_path}")
        # Use override=True to force reload
        load_dotenv(dotenv_path, override=True)
    else:
        print(f"Warning: .env file not found at {dotenv_path}")
except ImportError:
    print("python-dotenv package not found. Install it with: pip install python-dotenv")
    print("Continuing without loading .env file...")

# Get the API key
api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("Error: GOOGLE_API_KEY not found in environment variables")
    exit(1)

print(f"API key found: {api_key[:5]}...{api_key[-4:]}")
print(f"API key length: {len(api_key)} characters")
print(f"DEFAULT_AI_PROVIDER: {os.environ.get('DEFAULT_AI_PROVIDER', 'not set')}")

# Use the model from command line argument
google_model = args.model
print(f"Using model: {google_model}")

# Check for GOOGLE_GENAI_MODEL environment variable
if google_model:
    print(f"GOOGLE_GENAI_MODEL: {google_model}")
else:
    print("GOOGLE_GENAI_MODEL not found in environment variables")
    print("Using default model: gemini-pro")
    
    # Add GOOGLE_GENAI_MODEL to .env file
    try:
        with open(dotenv_path, 'r') as file:
            lines = file.readlines()
        
        # Check if GOOGLE_GENAI_MODEL already exists
        model_exists = False
        for i, line in enumerate(lines):
            if line.strip().startswith("GOOGLE_GENAI_MODEL="):
                lines[i] = "GOOGLE_GENAI_MODEL=gemini-pro\n"
                model_exists = True
                break
        
        # If it doesn't exist, add it
        if not model_exists:
            lines.append("\n# Google Gemini model to use\nGOOGLE_GENAI_MODEL=gemini-pro\n")
        
        # Write the updated content back to the file
        with open(dotenv_path, 'w') as file:
            file.writelines(lines)
        
        print("Added GOOGLE_GENAI_MODEL=gemini-pro to .env file")
        
        # Reload environment variables
        load_dotenv(dotenv_path, override=True)
        google_model = "gemini-pro"
    except Exception as e:
        print(f"Error adding GOOGLE_GENAI_MODEL to .env file: {e}")

# Try to import Google Generative AI
try:
    import google.generativeai as genai
    print(f"Google Generative AI library imported successfully")
    
    # Configure the API
    genai.configure(api_key=api_key)
    print("Google Gemini API configured successfully")
    
    # Try a simple API call
    try:
        print("\nTesting API connection...")
        
        # List available models
        models = genai.list_models()
        gemini_models = [model for model in models if "gemini" in model.name.lower()]
        
        print(f"Success! API connection works. Available Gemini models: {len(gemini_models)}")
        print("\nSample Gemini models:")
        for i, model in enumerate(gemini_models[:5]):  # Show first 5 models
            print(f"  {i+1}. {model.name}")
        
        # Try a simple completion with Gemini using the model from command line
        print("\nTesting Gemini completion...")
        print(f"Using model: {google_model}")
        
        # Create a generative model instance with the specified model
        model = genai.GenerativeModel(google_model)
        
        # Generate content
        response = model.generate_content("Say hello!")
        
        print(f"Success! Gemini completion works. Response: {response.text}")
        print("\nYour Google Gemini API key is working correctly!")
        
    except Exception as api_error:
        print(f"\nAPI Error: {api_error}")
        print("\nPossible issues:")
        print("1. The API key may be invalid or expired")
        print("2. You may not have access to the requested models")
        print("3. There may be an issue with your Google Cloud account")
        print("4. The Gemini API may be unavailable in your region")
        print("5. The model name may be incorrect")
        
        # Try an alternative approach if the first one fails
        try:
            print("\nTrying alternative API approach with a different model...")
            # Try with a different model name
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content("Say hello!")
            print(f"Success! Gemini completion works with 'gemini-pro' model. Response: {response.text}")
            print("\nYour Google Gemini API key is working correctly!")
            print("Note: Please use 'gemini-pro' as your model name in your application.")
        except Exception as alt_error:
            print(f"\nAlternative approach also failed: {alt_error}")
            
            # Try the legacy approach as a last resort
            try:
                print("\nTrying legacy API approach...")
                response = genai.generate_text(
                    model="gemini-pro",
                    prompt="Say hello!"
                )
                print(f"Success! Legacy API works. Response: {response.text}")
                print("\nYour Google Gemini API key is working correctly with the legacy API!")
            except Exception as legacy_error:
                print(f"\nLegacy approach also failed: {legacy_error}")
                print("Please check the Google Generative AI documentation for the latest API usage.")
        
except ImportError as e:
    print(f"Error importing Google Generative AI: {e}")
    print("Try installing the Google Generative AI library: pip install google-generativeai")
except Exception as e:
    print(f"Unexpected error: {e}") 