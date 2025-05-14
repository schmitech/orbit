#!/bin/bash

# =============================================================================
# Orbit Server Setup Script (TOML-based)
# =============================================================================
#
# This script sets up the development environment using dependency profiles
# defined in dependencies.toml
#
# Requirements:
#   - Python 3 (with toml module)
#   - Bash shell
#   - Internet connection (for downloading dependencies and models)
#
# Usage:
#   List available profiles:
#     ./setup.sh --list-profiles
#
#   Install specific profile:
#     ./setup.sh --profile minimal
#     ./setup.sh --profile huggingface
#     ./setup.sh --profile commercial
#     ./setup.sh --profile all
#
#   Install multiple profiles:
#     ./setup.sh --profile huggingface --profile commercial
#
#   With GGUF model:
#     ./setup.sh --profile minimal --download-gguf
#
#   Custom profile from TOML:
#     ./setup.sh --profile custom_example
#
# =============================================================================

# Exit on error
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    case $color in
        "red") echo -e "\033[0;31m$message\033[0m" ;;
        "green") echo -e "\033[0;32m$message\033[0m" ;;
        "yellow") echo -e "\033[0;33m$message\033[0m" ;;
        "blue") echo -e "\033[0;34m$message\033[0m" ;;
        *) echo "$message" ;;
    esac
}

# Updated Python script with better error handling
PYTHON_PARSER='
import sys
import json
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: Neither tomllib (Python 3.11+) nor tomli is available", file=sys.stderr)
        sys.exit(1)

def read_dependencies_toml(toml_path):
    try:
        with open(toml_path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"Error parsing TOML file: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File {toml_path} not found", file=sys.stderr)
        sys.exit(1)

def resolve_profile(config, profile_name, resolved=None):
    if resolved is None:
        resolved = set()
    
    if profile_name in resolved:
        return []
    
    resolved.add(profile_name)
    
    if profile_name not in config["profiles"]:
        print(f"Error: Profile {profile_name} not found", file=sys.stderr)
        sys.exit(1)
    
    profile = config["profiles"][profile_name]
    dependencies = profile.get("dependencies", [])
    
    # Handle extends
    extends = profile.get("extends", [])
    if isinstance(extends, str):
        extends = [extends]
    
    for extend_profile in extends:
        dependencies = resolve_profile(config, extend_profile, resolved) + dependencies
    
    return dependencies

def list_profiles(config):
    profiles = []
    for name, profile in config["profiles"].items():
        profiles.append({
            "name": name,
            "description": profile.get("description", ""),
            "extends": profile.get("extends", [])
        })
    return profiles

def get_model_info(config, model_name):
    if "models" in config and "gguf" in config["models"]:
        return config["models"]["gguf"].get(model_name)
    return None

if len(sys.argv) < 3:
    print("Usage: parser.py <toml_file> <command> [args...]", file=sys.stderr)
    sys.exit(1)

toml_file = sys.argv[1]
command = sys.argv[2]

try:
    config = read_dependencies_toml(toml_file)
    
    if command == "list":
        profiles = list_profiles(config)
        print(json.dumps(profiles))
    
    elif command == "resolve":
        if len(sys.argv) < 4:
            print("Error: Profile name required", file=sys.stderr)
            sys.exit(1)
        
        profiles = sys.argv[3:]
        all_deps = []
        for profile in profiles:
            deps = resolve_profile(config, profile)
            all_deps.extend(deps)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_deps = []
        for dep in all_deps:
            if dep not in seen:
                seen.add(dep)
                unique_deps.append(dep)
        
        print(json.dumps(unique_deps))
    
    elif command == "model":
        if len(sys.argv) < 4:
            print("Error: Model name required", file=sys.stderr)
            sys.exit(1)
        
        model_name = sys.argv[3]
        model_info = get_model_info(config, model_name)
        print(json.dumps(model_info))
    
    else:
        print(f"Error: Unknown command {command}", file=sys.stderr)
        sys.exit(1)

except Exception as e:
    print(f"Error: {str(e)}", file=sys.stderr)
    sys.exit(1)
'

# Function to check if TOML dependency is available
check_toml_dependency() {
    python3 -c "
try:
    import tomllib
except ImportError:
    try:
        import tomli
    except ImportError:
        print('missing')
        exit(1)
print('available')
"
}

# Function to install TOML parser if needed
install_toml_parser() {
    local toml_status=$(check_toml_dependency)
    if [ "$toml_status" = "missing" ]; then
        print_message "yellow" "Installing TOML parser (tomli)..."
        pip install tomli
    fi
}

# Function to list available profiles
list_profiles() {
    local result=$(python3 -c "$PYTHON_PARSER" "$SCRIPT_DIR/dependencies.toml" list 2>&1)
    if [ $? -ne 0 ]; then
        print_message "red" "Error parsing dependencies.toml:"
        echo "$result" >&2
        exit 1
    fi
    echo "$result" | python3 -m json.tool
}

# Function to resolve dependencies for profiles
resolve_dependencies() {
    local profiles="$@"
    local result=$(python3 -c "$PYTHON_PARSER" "$SCRIPT_DIR/dependencies.toml" resolve $profiles 2>&1)
    if [ $? -ne 0 ]; then
        print_message "red" "Error resolving dependencies:"
        echo "$result" >&2
        exit 1
    fi
    echo "$result"
}

# Function to get model information
get_model_info() {
    local model_name=$1
    local result=$(python3 -c "$PYTHON_PARSER" "$SCRIPT_DIR/dependencies.toml" model "$model_name" 2>&1)
    if [ $? -ne 0 ]; then
        print_message "red" "Error getting model info:"
        echo "$result" >&2
        exit 1
    fi
    echo "$result"
}

# Function to download GGUF model
# Function to download GGUF model
download_gguf_model() {
    print_message "yellow" "Downloading Gemma 3 1B GGUF model..."
    
    # Get the actual directory of this script (setup.sh)
    SCRIPT_PATH="${BASH_SOURCE[0]}"
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
    
    # Debug: Show current working directory and calculated paths
    print_message "blue" "Current working directory: $(pwd)"
    print_message "blue" "Script directory: $SCRIPT_DIR"
    print_message "blue" "Project root: $PROJECT_ROOT"
    
    # Create gguf directory in project root if it doesn't exist
    GGUF_DIR="$PROJECT_ROOT/gguf"
    mkdir -p "$GGUF_DIR"
    
    print_message "blue" "Creating GGUF directory at: $GGUF_DIR"
    
    # Verify the directory exists and show its absolute path
    if [ ! -d "$GGUF_DIR" ]; then
        print_message "red" "Error: Failed to create GGUF directory at $GGUF_DIR"
        exit 1
    fi
    
    # Download the model to project root gguf directory
    print_message "blue" "Downloading to: $GGUF_DIR/gemma-3-1b-it-Q4_0.gguf"
    if ! curl -L "https://huggingface.co/unsloth/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_0.gguf" -o "$GGUF_DIR/gemma-3-1b-it-Q4_0.gguf"; then
        print_message "red" "Error: Failed to download GGUF model."
        exit 1
    fi
    
    # Verify the file was created in the correct location
    if [ -f "$GGUF_DIR/gemma-3-1b-it-Q4_0.gguf" ]; then
        print_message "green" "GGUF model downloaded successfully to: $GGUF_DIR/gemma-3-1b-it-Q4_0.gguf"
        print_message "blue" "File size: $(du -h "$GGUF_DIR/gemma-3-1b-it-Q4_0.gguf" | cut -f1)"
    else
        print_message "red" "Error: GGUF model was not found at expected location: $GGUF_DIR/gemma-3-1b-it-Q4_0.gguf"
        exit 1
    fi
}

# Default values
DOWNLOAD_GGUF=false
PROFILES=()
LIST_PROFILES=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile|-p)
            if [ -z "$2" ]; then
                print_message "red" "Error: --profile requires a value"
                exit 1
            fi
            PROFILES+=("$2")
            shift 2
            ;;
        --download-gguf)
            DOWNLOAD_GGUF=true
            shift
            ;;
        --list-profiles|--list)
            LIST_PROFILES=true
            shift
            ;;
        --help|-h)
            print_message "blue" "Orbit Server Setup Script (TOML-based)"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --profile, -p <name>    Install dependencies for specified profile"
            echo "                          Can be used multiple times"
            echo "  --list-profiles, --list List available dependency profiles"
            echo "  --download-gguf         Download Gemma 3 1B GGUF model"
            echo "  --help, -h              Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --list-profiles"
            echo "  $0 --profile minimal"
            echo "  $0 --profile huggingface --profile commercial"
            echo "  $0 --profile all --download-gguf"
            exit 0
            ;;
        *)
            print_message "red" "Unknown option: $1"
            echo "Use --help to see available options"
            exit 1
            ;;
    esac
done

# Check if dependencies.toml exists
if [ ! -f "$SCRIPT_DIR/dependencies.toml" ]; then
    print_message "red" "Error: dependencies.toml not found in install directory: $SCRIPT_DIR"
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_message "red" "Error: Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# If list profiles is requested, show them and exit
if [ "$LIST_PROFILES" = true ]; then
    print_message "blue" "Available dependency profiles:"
    list_profiles
    exit 0
fi

# If no profiles specified, default to minimal
if [ ${#PROFILES[@]} -eq 0 ]; then
    PROFILES=("minimal")
    print_message "yellow" "No profile specified, using default: minimal"
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    print_message "yellow" "Creating Python virtual environment..."
    if ! python3 -m venv venv; then
        print_message "red" "Error: Failed to create virtual environment."
        exit 1
    fi
    print_message "green" "Virtual environment created successfully."
fi

# Activate virtual environment
print_message "yellow" "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
print_message "yellow" "Upgrading pip..."
if ! pip install --upgrade pip; then
    print_message "red" "Error: Failed to upgrade pip."
    exit 1
fi

# Install TOML parser if needed
install_toml_parser

# Resolve dependencies for selected profiles
print_message "yellow" "Resolving dependencies for profiles: ${PROFILES[*]}"
DEPENDENCIES=$(resolve_dependencies "${PROFILES[@]}")

if [ $? -ne 0 ]; then
    print_message "red" "Error: Failed to resolve dependencies"
    exit 1
fi

# Create temporary requirements file
TEMP_REQUIREMENTS=$(mktemp /tmp/orbit_requirements.XXXXXX.txt)
echo "$DEPENDENCIES" | python3 -c "import json, sys; deps = json.load(sys.stdin); print('\n'.join(deps))" > "$TEMP_REQUIREMENTS"

# Show what will be installed
print_message "blue" "\nSelected profiles: ${PROFILES[*]}"
print_message "blue" "Dependencies to install:"
echo "----------------------------------------"
cat "$TEMP_REQUIREMENTS"
echo "----------------------------------------"

# Install requirements
print_message "yellow" "\nInstalling dependencies..."
if ! pip install -r "$TEMP_REQUIREMENTS"; then
    print_message "red" "Error: Failed to install requirements."
    rm -f "$TEMP_REQUIREMENTS"
    exit 1
fi

# Clean up temporary file
rm -f "$TEMP_REQUIREMENTS"

# Download GGUF model if requested
if [ "$DOWNLOAD_GGUF" = true ]; then
    download_gguf_model
fi

# Handle .env files in server directory
if [ -f "server/.env.example" ] && [ ! -f "server/.env" ]; then
    cp server/.env.example server/.env
    print_message "green" "Created .env from template in server directory."
fi

# Summary
print_message "green" "\n=== Setup completed successfully! ==="
print_message "green" "Installed profiles: ${PROFILES[*]}"

if [ "$DOWNLOAD_GGUF" = true ]; then
    print_message "blue" "  ✓ GGUF model downloaded"
fi

print_message "yellow" "\nTo activate the virtual environment, run:"
print_message "green" "  source venv/bin/activate"

print_message "yellow" "\nTo start the server, run:"
print_message "green" "  ./bin/orbit.sh start"