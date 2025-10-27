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
#     ./setup.sh --profile torch
#     ./setup.sh --profile cloud
#     ./setup.sh --profile all
#
#   Install multiple profiles:
#     ./setup.sh --profile torch --profile cloud
#
#   With GGUF model:
#     ./setup.sh --profile minimal --download-gguf gemma3-1b.gguf
#     ./setup.sh --download-gguf gemma3-1b.gguf  # Download only, no dependency installation
#     ./setup.sh --download-gguf tinyllama-1b.gguf --gguf-models-config ./gguf-models.json
#     ./setup.sh --download-gguf gemma3-1b.gguf --download-gguf mistral-7b.gguf
#
#   Custom profile from TOML:
#     ./setup.sh --profile custom_example
#
# GGUF Model Download Options:
#   --download-gguf [model]    Download GGUF model(s) by name (can be used multiple times)
#   --gguf-models-config <f>   Path to GGUF models .json config (default: ./gguf-models.json)
#
# The GGUF model(s) to download must be defined in the config file as:
#   {
#     "models": {
#       "model-name.gguf": {
#         "repo_id": "username/repository-name",
#         "filename": "model-file.gguf"
#       }
#     }
#   }
#
# If --download-gguf is used without a value, it defaults to gemma3-1b.gguf if present in the config.
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

# Function to get model info from JSON config file
get_model_info() {
    local model_name="$1"
    local config_file="$2"
    if [ ! -f "$config_file" ]; then
        return 1
    fi
    python3 -c "
import json
import sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
    if '$model_name' in config['models']:
        model_info = config['models']['$model_name']
        print(f\"{model_info['repo_id']}\")
        print(f\"{model_info['filename']}\")
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
"
}

# Function to download GGUF models using the Python script
download_gguf_model() {
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
    MODELS_DIR="$PROJECT_ROOT/models"
    mkdir -p "$MODELS_DIR"
    print_message "blue" "Models directory: $MODELS_DIR"

    if [ ! -f "$GGUF_MODELS_CONFIG" ]; then
        print_message "red" "GGUF models config file not found: $GGUF_MODELS_CONFIG"
        exit 1
    fi

    if [ ${#GGUF_MODELS_TO_DOWNLOAD[@]} -eq 0 ]; then
        # Default to gemma3-1b.gguf if present in config
        GGUF_MODELS_TO_DOWNLOAD+=("gemma3-1b.gguf")
    fi

    print_message "yellow" "Downloading GGUF model(s) using download_hf_gguf_model.py..."
    for model in "${GGUF_MODELS_TO_DOWNLOAD[@]}"; do
        model_info=$(get_model_info "$model" "$GGUF_MODELS_CONFIG")
        if [ $? -ne 0 ]; then
            print_message "red" "Unknown GGUF model: $model (not found in $GGUF_MODELS_CONFIG)"
            continue
        fi
        
        # Parse the model info (repo_id and filename)
        repo_id=$(echo "$model_info" | head -n 1)
        filename=$(echo "$model_info" | tail -n 1)
        
        # Check if the actual downloaded file exists (using the filename from config)
        if [ ! -f "$MODELS_DIR/$filename" ]; then
            print_message "blue" "Downloading $model from $repo_id..."
            if python3 "$SCRIPT_DIR/download_hf_gguf_model.py" \
                --repo-id "$repo_id" \
                --filename "$filename" \
                --output-dir "$MODELS_DIR"; then
                print_message "green" "$model downloaded successfully to: $MODELS_DIR/$filename"
                print_message "blue" "File size: $(du -h "$MODELS_DIR/$filename" | cut -f1)"
            else
                print_message "red" "Failed to download $model"
                exit 1
            fi
        else
            print_message "blue" "$model already exists at $MODELS_DIR/$filename"
        fi
    done
}

# Default values
DOWNLOAD_GGUF=false
PROFILES=()
LIST_PROFILES=false
GGUF_MODELS_TO_DOWNLOAD=()
GGUF_MODELS_CONFIG="$SCRIPT_DIR/gguf-models.json"

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
            if [[ -n "$2" && "${2:0:1}" != "-" ]]; then
                GGUF_MODELS_TO_DOWNLOAD+=("$2")
                shift 2
            else
                shift
            fi
            ;;
        --gguf-models-config)
            if [ -z "$2" ]; then
                print_message "red" "Error: --gguf-models-config requires a value"
                exit 1
            fi
            GGUF_MODELS_CONFIG="$2"
            shift 2
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
            echo "  --download-gguf         Download GGUF model(s) as specified by --gguf-model"
            echo "  --gguf-models-config <f>Path to GGUF models .json config (default: ./gguf-models.json)"
            echo "  --help, -h              Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --list-profiles"
            echo "  $0 --profile minimal"
            echo "  $0 --profile torch --profile cloud"
            echo "  $0 --profile all --download-gguf gemma3-1b.gguf"
            echo "  $0 --download-gguf gemma3-1b.gguf  # Download only, no dependency installation"
            echo "  $0 --download-gguf tinyllama-1b.gguf --gguf-models-config ./gguf-models.json"
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

# Function to get Python version
get_python_version() {
    local cmd=$1
    if command -v "$cmd" &> /dev/null; then
        $cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null
    fi
}

# Function to display interactive Python version menu
select_python_version() {
    echo "" >&2
    print_message "blue" "╔════════════════════════════════════════════════════════════════════╗" >&2
    print_message "blue" "║           Orbit Server Setup - Python Version Selector            ║" >&2
    print_message "blue" "╚════════════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2

    # Detect available Python versions
    declare -a PYTHON_VERSIONS
    declare -a PYTHON_COMMANDS
    declare -a PYTHON_STATUS
    declare -a PYTHON_EMOJI

    for cmd in python3.12 python3.11 python3.10 python3.13 python3.9 python3; do
        version=$(get_python_version "$cmd")
        if [ -n "$version" ]; then
            # Check if we already have this version
            already_added=false
            for existing in "${PYTHON_VERSIONS[@]}"; do
                if [ "$existing" = "$version" ]; then
                    already_added=true
                    break
                fi
            done

            if [ "$already_added" = false ]; then
                PYTHON_VERSIONS+=("$version")
                PYTHON_COMMANDS+=("$cmd")

                # Determine status
                major=$(echo "$version" | cut -d. -f1)
                minor=$(echo "$version" | cut -d. -f2)

                if [ "$major" = "3" ] && [ "$minor" = "12" ]; then
                    PYTHON_STATUS+=("✓ Recommended")
                    PYTHON_EMOJI+=("🟢")
                elif [ "$major" = "3" ] && [ "$minor" = "11" ]; then
                    PYTHON_STATUS+=("✓ Compatible")
                    PYTHON_EMOJI+=("🟢")
                elif [ "$major" = "3" ] && [ "$minor" -ge "13" ]; then
                    PYTHON_STATUS+=("⚠  May have issues")
                    PYTHON_EMOJI+=("🟡")
                elif [ "$major" = "3" ] && [ "$minor" -ge "9" ]; then
                    PYTHON_STATUS+=("⚠  Older version")
                    PYTHON_EMOJI+=("🟡")
                else
                    PYTHON_STATUS+=("✗ Not supported")
                    PYTHON_EMOJI+=("🔴")
                fi
            fi
        fi
    done

    if [ ${#PYTHON_VERSIONS[@]} -eq 0 ]; then
        print_message "red" "No Python installations found!" >&2
        echo "" >&2
        print_message "yellow" "Install Python 3.12: brew install python@3.12" >&2
        exit 1
    fi

    # Show warning if default python3 is 3.13+
    default_version=$(get_python_version "python3")
    default_major=$(echo "$default_version" | cut -d. -f1)
    default_minor=$(echo "$default_version" | cut -d. -f2)

    if [ "$default_major" = "3" ] && [ "$default_minor" -ge "13" ]; then
        print_message "yellow" "⚠  WARNING: Default python3 is version $default_version" >&2
        print_message "yellow" "   Python 3.13+ may have compatibility issues with some packages (especially grpcio)." >&2
        print_message "yellow" "   We recommend using Python 3.12 or 3.11 for the best experience." >&2
        echo "" >&2
    fi

    # Display table
    print_message "cyan" "Available Python Versions:" >&2
    echo "────────────────────────────────────────────────────────────────────" >&2
    printf "%-6s %-4s %-15s %-18s %-25s\n" " #" "" "Version" "Command" "Status" >&2
    echo "────────────────────────────────────────────────────────────────────" >&2

    for i in "${!PYTHON_VERSIONS[@]}"; do
        idx=$((i + 1))
        printf "%-6s %-4s %-15s %-18s %-25s\n" \
            " $idx" \
            "${PYTHON_EMOJI[$i]}" \
            "${PYTHON_VERSIONS[$i]}" \
            "${PYTHON_COMMANDS[$i]}" \
            "${PYTHON_STATUS[$i]}" >&2
    done

    echo "────────────────────────────────────────────────────────────────────" >&2
    echo "" >&2
    echo "Legend:" >&2
    print_message "green" "  🟢 Recommended/Compatible - Fully tested and supported" >&2
    print_message "yellow" "  🟡 May have issues - Might require building packages from source" >&2
    print_message "red" "  🔴 Not supported - Not recommended for use" >&2
    echo "" >&2

    # Prompt for selection
    while true; do
        read -p "Select Python version [1-${#PYTHON_VERSIONS[@]}] (default: 1): " choice </dev/tty
        choice=${choice:-1}

        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#PYTHON_VERSIONS[@]}" ]; then
            idx=$((choice - 1))
            selected_cmd="${PYTHON_COMMANDS[$idx]}"
            selected_version="${PYTHON_VERSIONS[$idx]}"
            selected_status="${PYTHON_STATUS[$idx]}"

            # Confirm if selecting a problematic version
            if [[ "$selected_status" == *"issues"* ]] || [[ "$selected_status" == *"Not supported"* ]]; then
                echo "" >&2
                print_message "yellow" "⚠  You selected Python $selected_version which ${selected_status,,}." >&2
                read -p "   Are you sure you want to continue? [y/N]: " confirm </dev/tty
                if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                    echo "" >&2
                    continue
                fi
            fi

            echo "" >&2
            print_message "green" "✓ Selected: Python $selected_version ($selected_cmd)" >&2
            echo "" >&2

            echo "$selected_cmd"
            return 0
        else
            print_message "red" "Invalid selection. Please try again." >&2
        fi
    done
}

# Interactive Python version selection
PYTHON_CMD=$(select_python_version)
PYTHON_VERSION=$(get_python_version "$PYTHON_CMD")

# If list profiles is requested, show them and exit
if [ "$LIST_PROFILES" = true ]; then
    print_message "blue" "Available dependency profiles:"
    list_profiles
    exit 0
fi

# Check if only GGUF download is requested (no profiles specified)
if [ ${#PROFILES[@]} -eq 0 ] && [ "$DOWNLOAD_GGUF" = true ]; then
    print_message "blue" "GGUF model download only mode - skipping dependency installation"
    
    # Create virtual environment if it doesn't exist (needed for download script)
    if [ ! -d "venv" ]; then
        print_message "yellow" "Creating Python virtual environment for download script with $PYTHON_CMD..."
        if ! $PYTHON_CMD -m venv venv; then
            print_message "red" "Error: Failed to create virtual environment."
            exit 1
        fi
        print_message "green" "Virtual environment created successfully."
    fi
    
    # Activate virtual environment (needed for download script dependencies)
    print_message "yellow" "Activating virtual environment..."
    source venv/bin/activate
    
    # Install minimal dependencies needed for download script
    print_message "yellow" "Installing minimal dependencies for download script..."
    if ! pip install requests tqdm pyyaml; then
        print_message "red" "Error: Failed to install download script dependencies."
        exit 1
    fi
    
    # Download GGUF model if requested
    if [ "$DOWNLOAD_GGUF" = true ]; then
        download_gguf_model
    fi
    
    # Handle .env files in server directory
    if [ -f "server/env.example" ] && [ ! -f "server/.env" ]; then
        cp server/env.example server/.env
        print_message "green" "Created .env from template in server directory."
    fi
    
    # Summary for download-only mode
    print_message "green" "\n=== GGUF model download completed! ==="
    if [ "$DOWNLOAD_GGUF" = true ]; then
        print_message "blue" "  ✓ GGUF model downloaded"
    fi
    exit 0
fi

# If no profiles specified, default to minimal
if [ ${#PROFILES[@]} -eq 0 ]; then
    PROFILES=("minimal")
    print_message "yellow" "No profile specified, using default: minimal"
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    print_message "yellow" "Creating Python virtual environment with $PYTHON_CMD..."
    if ! $PYTHON_CMD -m venv venv; then
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
TEMP_REQUIREMENTS="/tmp/orbit_requirements_$(date +%s)_$$.txt"
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
if [ -f "server/env.example" ] && [ ! -f "server/.env" ]; then
    cp server/env.example server/.env
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