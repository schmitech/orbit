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
#   Quick start (recommended for newcomers):
#     ./setup.sh --profile default --download-gguf gemma3-270m
#
#   List available profiles:
#     ./setup.sh --list-profiles
#
#   Install default dependencies only (minimal server, use API mode or Ollama):
#     ./setup.sh
#
#   Install with specific profile(s):
#     ./setup.sh --profile llama-cpp              # Direct GGUF model loading
#     ./setup.sh --profile default                # Recommended default (llama-cpp + providers + ollama)
#     ./setup.sh --profile providers              # Cloud providers (OpenAI, Anthropic, etc.)
#     ./setup.sh --profile all                    # Everything
#
#   Install multiple profiles (space-separated or comma-separated):
#     ./setup.sh --profile llama-cpp providers files
#     ./setup.sh --profiles "default, database, files"
#     ./setup.sh --profiles "llama-cpp,providers,embeddings"
#
#   With GGUF model download:
#     ./setup.sh --profile llama-cpp --download-gguf gemma3-270m
#     ./setup.sh --profile default --download-gguf gemma3-270m
#     ./setup.sh --download-gguf gemma3-270m      # Download only, no dependency installation
#     ./setup.sh --download-gguf gemma3-270m --gguf-models-config ./gguf-models.json
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
# If --download-gguf is used without a value, it defaults to gemma3-270m if present in the config.
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

# Wrapper to run Python with the selected interpreter or active virtualenv
python_exec() {
    if [ -n "$VIRTUAL_ENV" ]; then
        python "$@"
    else
        if [ -z "$PYTHON_CMD" ]; then
            print_message "red" "Internal error: PYTHON_CMD is not set."
            exit 1
        fi
        "$PYTHON_CMD" "$@"
    fi
}

# Remove temporary requirement files on exit
cleanup_temp_requirements() {
    if [ -n "$TEMP_REQUIREMENTS" ] && [ -f "$TEMP_REQUIREMENTS" ]; then
        rm -f "$TEMP_REQUIREMENTS"
    fi
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

def get_default_dependencies(config):
    """Get default dependencies (always installed)"""
    if "default" in config:
        return config["default"].get("dependencies", [])
    return []

def resolve_profile(config, profile_name, resolved=None):
    if resolved is None:
        resolved = set()
    
    if profile_name in resolved:
        return []
    
    resolved.add(profile_name)
    
    if profile_name not in config.get("profiles", {}):
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
    # Add default section info
    if "default" in config:
        profiles.append({
            "name": "default",
            "description": config["default"].get("description", "Core dependencies (always installed)"),
            "extends": []
        })
    # Add profile sections
    for name, profile in config.get("profiles", {}).items():
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
        # Always include default dependencies
        all_deps = get_default_dependencies(config)
        
        # Add profile dependencies if specified
        if len(sys.argv) >= 4:
            profiles = sys.argv[3:]
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
    python_exec -c "
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
    local result=$(python_exec -c "$PYTHON_PARSER" "$SCRIPT_DIR/dependencies.toml" list 2>&1)
    if [ $? -ne 0 ]; then
        print_message "red" "Error parsing dependencies.toml:"
        echo "$result" >&2
        exit 1
    fi
    echo "$result" | python_exec -m json.tool
}

# Function to resolve dependencies for profiles
resolve_dependencies() {
    local profiles=("$@")
    local result
    result=$(python_exec -c "$PYTHON_PARSER" "$SCRIPT_DIR/dependencies.toml" resolve "${profiles[@]}" 2>&1)
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        print_message "red" "Error resolving dependencies:"
        echo "$result" >&2
        exit 1
    fi
    echo "$result"
}

# Function to get model information from dependencies.toml via the parser
get_model_info_from_toml() {
    local model_name=$1
    local result=$(python_exec -c "$PYTHON_PARSER" "$SCRIPT_DIR/dependencies.toml" model "$model_name" 2>&1)
    if [ $? -ne 0 ]; then
        print_message "red" "Error getting model info:"
        echo "$result" >&2
        exit 1
    fi
    echo "$result"
}

# Function to get model info from JSON config file
get_model_info_from_config() {
    local model_name="$1"
    local config_file="$2"
    
    # Validate inputs
    if [ -z "$model_name" ] || [ -z "$config_file" ]; then
        return 1
    fi
    
    if [ ! -f "$config_file" ]; then
        return 1
    fi
    
    # Use Python's json module to safely parse and extract model info
    python_exec -c "
import json
import sys
import os

try:
    config_file = '$config_file'
    model_name = '$model_name'
    
    # Validate that config_file is a real file path (basic security check)
    if not os.path.isfile(config_file):
        sys.exit(1)
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    models = config.get('models', {})
    if model_name not in models:
        sys.exit(1)
    
    model_info = models[model_name]
    repo_id = model_info.get('repo_id', '')
    filename = model_info.get('filename', '')
    
    if not repo_id or not filename:
        sys.exit(1)
    
    print(repo_id)
    print(filename)
except Exception:
    sys.exit(1)
"
}

# Function to download GGUF models using the Python script
download_gguf_model() {
    local project_root
    project_root="$(cd "$SCRIPT_DIR/.." && pwd)"
    
    # Validate project root exists and is writable
    if [ ! -d "$project_root" ]; then
        print_message "red" "Error: Project root directory does not exist: $project_root"
        exit 1
    fi
    
    if [ ! -w "$project_root" ]; then
        print_message "red" "Error: Project root directory is not writable: $project_root"
        exit 1
    fi
    
    local models_dir="$project_root/models"
    mkdir -p "$models_dir"
    print_message "blue" "Models directory: $models_dir"
    local download_failed=false

    if [ ! -f "$GGUF_MODELS_CONFIG" ]; then
        print_message "red" "GGUF models config file not found: $GGUF_MODELS_CONFIG"
        exit 1
    fi

    if [ ${#GGUF_MODELS_TO_DOWNLOAD[@]} -eq 0 ]; then
        # Default to gemma3-270m if present in config
        GGUF_MODELS_TO_DOWNLOAD+=("gemma3-270m")
    fi

    print_message "yellow" "Downloading GGUF model(s) using download_hf_gguf_model.py..."
    for model in "${GGUF_MODELS_TO_DOWNLOAD[@]}"; do
        model_info=$(get_model_info_from_config "$model" "$GGUF_MODELS_CONFIG")
        if [ $? -ne 0 ]; then
            print_message "red" "Unknown GGUF model: $model (not found in $GGUF_MODELS_CONFIG)"
            download_failed=true
            continue
        fi
        
        # Parse the model info (repo_id and filename)
        repo_id=$(echo "$model_info" | head -n 1)
        filename=$(echo "$model_info" | tail -n 1)
        
        # Check if the actual downloaded file exists (using the filename from config)
        if [ ! -f "$models_dir/$filename" ]; then
            print_message "blue" "Downloading $model from $repo_id..."
            if python_exec "$SCRIPT_DIR/download_hf_gguf_model.py" \
                --repo-id "$repo_id" \
                --filename "$filename" \
                --output-dir "$models_dir"; then
                print_message "green" "$model downloaded successfully to: $models_dir/$filename"
                print_message "blue" "File size: $(du -h "$models_dir/$filename" | cut -f1)"
            else
                print_message "red" "Failed to download $model"
                exit 1
            fi
        else
            print_message "blue" "$model already exists at $models_dir/$filename"
        fi
    done

    if [ "$download_failed" = true ]; then
        print_message "red" "At least one GGUF model could not be downloaded."
        exit 1
    fi
}

# Default values
DOWNLOAD_GGUF=false
PROFILES=()
LIST_PROFILES=false
GGUF_MODELS_TO_DOWNLOAD=()
GGUF_MODELS_CONFIG="$SCRIPT_DIR/gguf-models.json"
PYTHON_CMD_OVERRIDE=""
PYTHON_CMD=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile|-p)
            if [ -z "$2" ] || [[ "${2:0:1}" == "-" ]]; then
                print_message "red" "Error: --profile requires at least one value"
                exit 1
            fi
            # Accept multiple profile names until we hit another flag or end of args
            shift
            while [[ $# -gt 0 && "${1:0:1}" != "-" ]]; do
                PROFILES+=("$1")
                shift
            done
            ;;
        --profiles)
            if [ -z "$2" ]; then
                print_message "red" "Error: --profiles requires a comma-separated list"
                exit 1
            fi
            # Parse comma-separated list, trimming whitespace from each item
            IFS=',' read -ra PROFILE_LIST <<< "$2"
            for profile in "${PROFILE_LIST[@]}"; do
                # Trim leading/trailing whitespace
                profile=$(echo "$profile" | xargs)
                if [ -n "$profile" ]; then
                    PROFILES+=("$profile")
                fi
            done
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
        --python-cmd)
            if [ -z "$2" ]; then
                print_message "red" "Error: --python-cmd requires a value"
                exit 1
            fi
            PYTHON_CMD_OVERRIDE="$2"
            shift 2
            ;;
        --help|-h)
            print_message "blue" "Orbit Server Setup Script (TOML-based)"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --profile, -p <names>   Install dependencies for specified profile(s)"
            echo "                          Accepts multiple space-separated names"
            echo "  --profiles <list>       Comma-separated list of profiles (e.g., \"default, database, files\")"
            echo "  --list-profiles, --list List available dependency profiles"
            echo "  --download-gguf [model] Download GGUF model(s) by name (optional model name)"
            echo "  --gguf-models-config <f>Path to GGUF models .json config (default: ./gguf-models.json)"
            echo "  --python-cmd <cmd>      Python executable to use (skips interactive selection)"
            echo "  --help, -h              Show this help message"
            echo ""
            echo "Quick Start (Recommended for Newcomers):"
            echo "  $0 --profile default --download-gguf gemma3-270m"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Minimal server (use API mode or Ollama)"
            echo "  $0 --profile llama-cpp                # Direct GGUF model loading"
            echo "  $0 --profile default                  # Recommended default setup"
            echo "  $0 --list-profiles                    # List all available profiles"
            echo "  $0 --profile llama-cpp --download-gguf gemma3-270m"
            echo "  $0 --profile default --download-gguf gemma3-270m"
            echo "  $0 --download-gguf gemma3-270m        # Download only, no dependency installation"
            echo "  $0 --profile llama-cpp providers files # Space-separated profiles"
            echo "  $0 --profiles \"default, database, files\" # Comma-separated profiles"
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

# Function to get Python version
get_python_version() {
    local cmd=$1
    if command -v "$cmd" &> /dev/null; then
        $cmd -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null
    fi
}

# Function to display interactive Python version menu
select_python_version() {
    local interactive=true
    if [ ! -t 0 ] || [ ! -t 1 ]; then
        interactive=false
    fi

    if [ "$interactive" = true ]; then
        echo "" >&2
        print_message "blue" "╔════════════════════════════════════════════════════════════════════╗" >&2
        print_message "blue" "║           Orbit Server Setup - Python Version Selector            ║" >&2
        print_message "blue" "╚════════════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
    fi

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

    if [ "$interactive" = false ]; then
        local selected_cmd="${PYTHON_COMMANDS[0]}"
        local selected_version="${PYTHON_VERSIONS[0]}"
        print_message "green" "✓ Selected Python $selected_version ($selected_cmd) - non-interactive mode" >&2
        echo "$selected_cmd"
        return 0
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

# Determine Python interpreter
if [ -n "$PYTHON_CMD_OVERRIDE" ]; then
    if ! command -v "$PYTHON_CMD_OVERRIDE" &> /dev/null; then
        print_message "red" "Error: Python command '$PYTHON_CMD_OVERRIDE' not found."
        exit 1
    fi
    PYTHON_CMD="$PYTHON_CMD_OVERRIDE"
    selected_version=$(get_python_version "$PYTHON_CMD")
    if [ -n "$selected_version" ]; then
        print_message "green" "✓ Selected: Python $selected_version ($PYTHON_CMD) via --python-cmd"
    else
        print_message "yellow" "Using provided Python command: $PYTHON_CMD"
    fi
else
    PYTHON_CMD=$(select_python_version)
fi

# If list profiles is requested, show them and exit
if [ "$LIST_PROFILES" = true ]; then
    print_message "blue" "Available dependency profiles:"
    list_profiles
    exit 0
fi

# Determine project root (one level up from install directory)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check if only GGUF download is requested (no profiles specified)
if [ ${#PROFILES[@]} -eq 0 ] && [ "$DOWNLOAD_GGUF" = true ]; then
    print_message "blue" "GGUF model download only mode - skipping dependency installation"
    
    # Create virtual environment if it doesn't exist (needed for download script)
    VENV_DIR="$PROJECT_ROOT/venv"
    if [ ! -d "$VENV_DIR" ]; then
        print_message "yellow" "Creating Python virtual environment for download script with $PYTHON_CMD..."
        if ! $PYTHON_CMD -m venv "$VENV_DIR"; then
            print_message "red" "Error: Failed to create virtual environment."
            exit 1
        fi
        print_message "green" "Virtual environment created successfully."
    fi
    
    # Activate virtual environment (needed for download script dependencies)
    print_message "yellow" "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    
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
    if [ -f "$PROJECT_ROOT/server/env.example" ] && [ ! -f "$PROJECT_ROOT/server/.env" ]; then
        cp "$PROJECT_ROOT/server/env.example" "$PROJECT_ROOT/server/.env"
        print_message "green" "Created .env from template in server directory."
    fi
    
    # Summary for download-only mode
    print_message "green" "\n=== GGUF model download completed! ==="
    if [ "$DOWNLOAD_GGUF" = true ]; then
        print_message "blue" "  ✓ GGUF model downloaded"
    fi
    exit 0
fi

# Default dependencies are always installed, profiles are optional
if [ ${#PROFILES[@]} -eq 0 ]; then
    print_message "blue" "No profiles specified - installing default dependencies only"
fi

# Determine project root if not already set
if [ -z "$PROJECT_ROOT" ]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Validate project root exists and is writable
if [ ! -d "$PROJECT_ROOT" ]; then
    print_message "red" "Error: Project root directory does not exist: $PROJECT_ROOT"
    exit 1
fi

if [ ! -w "$PROJECT_ROOT" ]; then
    print_message "red" "Error: Project root directory is not writable: $PROJECT_ROOT"
    exit 1
fi

# Create virtual environment if it doesn't exist
VENV_DIR="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_DIR" ]; then
    print_message "yellow" "Creating Python virtual environment with $PYTHON_CMD..."
    if ! $PYTHON_CMD -m venv "$VENV_DIR"; then
        print_message "red" "Error: Failed to create virtual environment."
        exit 1
    fi
    print_message "green" "Virtual environment created successfully."
fi

# Activate virtual environment
print_message "yellow" "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
print_message "yellow" "Upgrading pip..."
if ! pip install --upgrade pip; then
    print_message "red" "Error: Failed to upgrade pip."
    exit 1
fi

# Install TOML parser if needed
install_toml_parser

# Resolve dependencies (default + selected profiles)
if [ ${#PROFILES[@]} -eq 0 ]; then
    print_message "yellow" "Resolving default dependencies..."
    DEPENDENCIES=$(resolve_dependencies)
else
    print_message "yellow" "Resolving dependencies for profiles: ${PROFILES[*]}"
    DEPENDENCIES=$(resolve_dependencies "${PROFILES[@]}")
fi
resolve_exit_code=$?

if [ $resolve_exit_code -ne 0 ] || [ -z "$DEPENDENCIES" ]; then
    print_message "red" "Error: Failed to resolve dependencies"
    exit 1
fi

# Create temporary requirements file
TEMP_REQUIREMENTS="/tmp/orbit_requirements_$(date +%s)_$$.txt"
trap cleanup_temp_requirements EXIT
echo "$DEPENDENCIES" | python_exec -c "import json, sys; deps = json.load(sys.stdin); print('\n'.join(deps))" > "$TEMP_REQUIREMENTS"

# Show what will be installed
print_message "blue" "\nInstalling default dependencies"
if [ ${#PROFILES[@]} -gt 0 ]; then
    print_message "blue" "Additional profiles: ${PROFILES[*]}"
fi
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
if [ -f "$PROJECT_ROOT/server/env.example" ] && [ ! -f "$PROJECT_ROOT/server/.env" ]; then
    cp "$PROJECT_ROOT/server/env.example" "$PROJECT_ROOT/server/.env"
    print_message "green" "Created .env from template in server directory."
fi

# Summary
print_message "green" "\n=== Setup completed successfully! ==="
print_message "green" "Installed default dependencies"
if [ ${#PROFILES[@]} -gt 0 ]; then
    print_message "green" "Additional profiles: ${PROFILES[*]}"
fi

if [ "$DOWNLOAD_GGUF" = true ]; then
    print_message "blue" "  ✓ GGUF model downloaded"
fi

print_message "yellow" "\nTo activate the virtual environment, run:"
print_message "green" "  source venv/bin/activate"

print_message "yellow" "\nTo start the server, run:"
print_message "green" "  ./bin/orbit.sh start"
