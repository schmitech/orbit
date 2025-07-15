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
parser.add_argument('--model', type=str, default='gemini-1.5-pro-latest', 
                    help='The Gemini model to use (default: gemini-1.5-pro-latest)')

if __name__ == "__main__":
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        
        # Get the current file's directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Go up three directories to reach the project root from tests/gemini/
        # server/tests/gemini/ -> server/tests/ -> server/ -> project_root/
        dotenv_path = os.path.join(current_dir, "..", "..", "..", ".env")
        print(f"Looking for .env at: {dotenv_path}")  # Debug print
        if os.path.exists(dotenv_path):
            print(f"Loading environment variables from: {dotenv_path}")
            # Use override=True to force reload
            load_dotenv(dotenv_path, override=True)
        else:
            print(f"Warning: .env file not found at {dotenv_path}")
            # Try alternative paths
            alternative_paths = [
                os.path.join(current_dir, "..", "..", ".env"),  # server/.env
                os.path.join(os.getcwd(), ".env"),  # current working directory
                ".env"  # relative to current directory
            ]
            for alt_path in alternative_paths:
                print(f"Trying alternative path: {alt_path}")
                if os.path.exists(alt_path):
                    print(f"Found .env at: {alt_path}")
                    load_dotenv(alt_path, override=True)
                    break
            else:
                print("Could not find .env file in any expected location")
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
    env_model = os.environ.get("GOOGLE_GENAI_MODEL")
    if env_model:
        print(f"GOOGLE_GENAI_MODEL: {env_model}")
        google_model = env_model  # Use environment variable if set
    else:
        print("GOOGLE_GENAI_MODEL not found in environment variables")
        print(f"Using command line model: {google_model}")
        
        # Add GOOGLE_GENAI_MODEL to .env file
        try:
            # First try to find the .env file again if we haven't found it yet
            if not os.path.exists(dotenv_path):
                # Try to find it in alternative locations
                alternative_paths = [
                    os.path.join(current_dir, "..", "..", ".env"),  # server/.env
                    os.path.join(os.getcwd(), ".env"),  # current working directory
                    ".env"  # relative to current directory
                ]
                for alt_path in alternative_paths:
                    if os.path.exists(alt_path):
                        dotenv_path = alt_path
                        break
                else:
                    # If no .env file found, create one in the project root
                    dotenv_path = os.path.join(current_dir, "..", "..", "..", ".env")
                    print(f"Creating new .env file at: {dotenv_path}")
                    with open(dotenv_path, 'w') as file:
                        file.write("# Environment variables for Orbit\n")
            
            with open(dotenv_path, 'r') as file:
                lines = file.readlines()
            
            # Check if GOOGLE_GENAI_MODEL already exists
            model_exists = False
            for i, line in enumerate(lines):
                if line.strip().startswith("GOOGLE_GENAI_MODEL="):
                    lines[i] = f"GOOGLE_GENAI_MODEL={google_model}\n"
                    model_exists = True
                    break
            
            # If it doesn't exist, add it
            if not model_exists:
                lines.append(f"\n# Google Gemini model to use\nGOOGLE_GENAI_MODEL={google_model}\n")
            
            # Write the updated content back to the file
            with open(dotenv_path, 'w') as file:
                file.writelines(lines)
            
            print(f"Added GOOGLE_GENAI_MODEL={google_model} to .env file")
            
            # Reload environment variables
            load_dotenv(dotenv_path, override=True)
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
            try:
                model = genai.GenerativeModel(google_model)
                
                # Generate content
                response = model.generate_content("Say hello!")
                
                print(f"Success! Gemini completion works. Response: {response.text}")
                print("\nYour Google Gemini API key is working correctly!")
                
            except Exception as model_error:
                print(f"\nModel Error with '{google_model}': {model_error}")
                
                # Try with alternative models
                alternative_models = [
                    'gemini-1.5-pro-latest',
                    'gemini-1.5-pro',
                    'gemini-1.0-pro',
                    'models/gemini-1.5-pro-latest',
                    'models/gemini-1.5-pro',
                    'models/gemini-1.0-pro'
                ]
                
                for alt_model in alternative_models:
                    if alt_model == google_model:
                        continue  # Skip the model we already tried
                    
                    try:
                        print(f"\nTrying alternative model: {alt_model}")
                        model = genai.GenerativeModel(alt_model)
                        response = model.generate_content("Say hello!")
                        print(f"Success! Gemini completion works with '{alt_model}'. Response: {response.text}")
                        print(f"\nYour Google Gemini API key is working correctly!")
                        print(f"Note: Please use '{alt_model}' as your model name in your application.")
                        break
                    except Exception as alt_error:
                        print(f"Failed with {alt_model}: {alt_error}")
                        continue
                else:
                    print("\nAll alternative models failed. Please check the available models list above.")
            
        except Exception as api_error:
            print(f"\nAPI Error: {api_error}")
            print("\nPossible issues:")
            print("1. The API key may be invalid or expired")
            print("2. You may not have access to the requested models")
            print("3. There may be an issue with your Google Cloud account")
            print("4. The Gemini API may be unavailable in your region")
            print("5. The model name may be incorrect")
            
    except ImportError as e:
        print(f"Error importing Google Generative AI: {e}")
        print("Try installing the Google Generative AI library: pip install google-generativeai")
    except Exception as e:
        print(f"Unexpected error: {e}") 