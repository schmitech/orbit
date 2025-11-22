#!/bin/bash

# ORBIT CLI Bash Wrapper
# Enterprise-grade shell wrapper for the ORBIT Python CLI
# Version: 2.0.2

set -euo pipefail  # Exit on error, undefined variables, and pipe failures

# Color codes for output (if terminal supports it)
if [[ -t 1 ]] && [[ "${NO_COLOR:-}" != "1" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORBIT_PY="$SCRIPT_DIR/orbit.py"

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ${NC} $1" >&2
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}✓${NC} $1" >&2
}

# Function to check Python version
check_python_version() {
    local python_cmd="$1"
    local min_version="3.12"
    
    if ! command -v "$python_cmd" &> /dev/null; then
        return 1
    fi
    
    local version=$("$python_cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ $(echo "$version >= $min_version" | bc) -eq 1 ]]; then
        return 0
    else
        return 1
    fi
}

# Find the best Python interpreter
find_python() {
    local python_cmds=("python3.12" "python3.11" "python3.10" "python3.9" "python3.8" "python3.7" "python3" "python")
    
    for cmd in "${python_cmds[@]}"; do
        if check_python_version "$cmd"; then
            echo "$cmd"
            return 0
        fi
    done
    
    return 1
}

# Check if required dependencies are installed
check_dependencies() {
    local python_cmd="$1"
    local missing_deps=()
    
    # Check for required Python packages
    local required_packages=("colorama" "rich" "click" "psutil" "python-dotenv" "requests")
    
    for package in "${required_packages[@]}"; do
        if ! "$python_cmd" -c "import $package" 2>/dev/null; then
            # Handle special case for python-dotenv
            if [[ "$package" == "python-dotenv" ]]; then
                if ! "$python_cmd" -c "import dotenv" 2>/dev/null; then
                    missing_deps+=("$package")
                fi
            else
                missing_deps+=("$package")
            fi
        fi
    done
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        print_warning "Missing required Python packages: ${missing_deps[*]}"
        print_info "Install them with: pip install ${missing_deps[*]}"
        return 1
    fi
    
    return 0
}

# Set up Python path to include the project root (parent of bin directory)
# This allows imports like "from bin.orbit.cli import main" to work
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# Check if we're in a virtual environment, if not try to activate one
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    # Check for common virtual environment locations
    venv_locations=(
        "${SCRIPT_DIR}/../venv/bin/activate"
        "${SCRIPT_DIR}/../.venv/bin/activate"
        "${SCRIPT_DIR}/venv/bin/activate"
        "${SCRIPT_DIR}/.venv/bin/activate"
    )
    
    for venv in "${venv_locations[@]}"; do
        if [[ -f "$venv" ]]; then
            print_info "Activating virtual environment: $(dirname $(dirname "$venv"))"
            source "$venv"
            break
        fi
    done
fi

# Find Python interpreter
PYTHON_CMD=$(find_python)
if [[ -z "$PYTHON_CMD" ]]; then
    print_error "Python 3.12 or higher is required but not found"
    print_info "Please install Python 3.12+ or activate a virtual environment"
    exit 1
fi

# Check if orbit.py exists
if [[ ! -f "$ORBIT_PY" ]]; then
    print_error "orbit.py not found at: $ORBIT_PY"
    exit 1
fi

# Make the Python script executable if it isn't already
if [[ ! -x "$ORBIT_PY" ]]; then
    chmod +x "$ORBIT_PY"
fi

# Check dependencies only if not in help mode or version check
if [[ $# -eq 0 ]] || [[ ! "${1:-}" =~ ^(-h|--help|--version|help)$ ]]; then
    if ! check_dependencies "$PYTHON_CMD"; then
        print_warning "Some functionality may not work without all dependencies"
    fi
fi

# Handle special cases for better user experience
case "${1:-}" in
    # Add shell completion support
    --install-completion)
        print_info "Installing shell completion..."
        # TODO: Implement shell completion installation
        print_warning "Shell completion installation not yet implemented"
        exit 0
        ;;
    
    # Quick status check
    --quick-status)
        if "$PYTHON_CMD" "$ORBIT_PY" status 2>/dev/null | grep -q "running"; then
            print_success "ORBIT server is running"
            exit 0
        else
            print_warning "ORBIT server is not running"
            exit 1
        fi
        ;;
    
    # Version check with additional info
    --version-full)
        echo "ORBIT CLI Shell Wrapper v2.0.2"
        echo "Python: $("$PYTHON_CMD" --version)"
        echo "Script: $ORBIT_PY"
        "$PYTHON_CMD" "$ORBIT_PY" --version
        exit 0
        ;;
esac

# Set up environment for better subprocess handling
export PYTHONUNBUFFERED=1

# Forward all arguments to the Python script
exec "$PYTHON_CMD" "$ORBIT_PY" "$@"