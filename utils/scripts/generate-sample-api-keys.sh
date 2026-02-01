#!/bin/bash

# Script to recreate all API keys for adapters when starting from scratch
# This script creates keys for each adapter and renames them to easier-to-remember names
#
# Usage:
#   ./utils/scripts/generate-sample-api-keys.sh                    # Create keys for all adapters
#   ./utils/scripts/generate-sample-api-keys.sh --adapter <name>   # Create key for a single adapter
#
# Examples:
#   ./utils/scripts/generate-sample-api-keys.sh --adapter simple-chat
#   ./utils/scripts/generate-sample-api-keys.sh --adapter file-document-qa
#
# Prerequisites:
#   - ORBIT server must be running
#   - You must be authenticated (run: ./bin/orbit.sh login)
#   - Database should be empty or you're okay with creating duplicate keys
#
# What this script does:
#   1. Creates API keys for each adapter listed below
#   2. Associates appropriate prompt files with each key
#   3. Adds intro notes (markdown) displayed in the chat interface
#   4. Renames each key to an easier-to-remember name
#
# Note: Adapters are now defined in config/adapters/*.yaml files (split by category).
#       This script uses a hardcoded list of adapters. If you add new adapters to the
#       YAML files, you'll need to add them to the all_adapters array below.
#
# Adapter to Key Name Mappings:
#   simple-chat -> default-key
#   simple-chat-with-files -> multimodal
#   math-teacher-quadratic-files -> math-teacher-quadratic
#   simple-chat-with-files-audio -> multimodal-audio
#   voice-chat -> voice-chat
#   audio-transcription -> transcription
#   multilingual-voice-assistant -> multilingual-voice-chat
#   premium-voice-chat -> premium-voice-chat
#   local-voice-chat -> whisper
#   real-time-voice-chat -> real-time-voice-chat
#   qa-sql -> sql-key
#   qa-vector-chroma -> chroma-key
#   qa-vector-qdrant-demo -> demo-key (EXCLUDED: requires special Qdrant deployment)
#   intent-sql-sqlite-hr -> hr
#   intent-duckdb-analytics -> analytical
#   intent-duckdb-ev-population -> ev
#   intent-sql-postgres -> postgres
#   intent-elasticsearch-app-logs -> elasticsearch
#   intent-firecrawl-webscrape -> web
#   intent-mongodb-mflix -> mflix
#   intent-http-jsonplaceholder -> rest
#   intent-http-paris-opendata -> paris
#   intent-graphql-spacex -> spacex
#   intent-agent-example -> agent
#   file-document-qa -> files
#
# Notes:
#   - Each adapter includes a markdown "notes" field that appears in the chat interface
#     as an intro message to help users understand what the agent can do.
#   - If a prompt file is not found, the key will be created without a prompt.
#     You can add the prompt later using the prompt associate command.

set -e  # Exit on error
set -o pipefail  # Exit on pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Error handling function
error_handler() {
    local exit_code=$?
    local line_number=$1
    local command=$2
    
    if [ $exit_code -ne 0 ]; then
        echo ""
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}✗ ERROR: Script failed at line $line_number${NC}"
        echo -e "${RED}  Command: $command${NC}"
        echo -e "${RED}  Exit code: $exit_code${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo -e "${YELLOW}Stack trace:${NC}"
        local frame=0
        while caller $frame; do
            ((frame++))
        done | sed 's/^/  /'
        echo ""
    fi
}

# Cleanup function for temporary files
cleanup_temp_files() {
    rm -f /tmp/orbit_key_create_stderr.$$ /tmp/orbit_key_rename_stderr.$$ /tmp/orbit_auth_stderr.$$
}

# Set trap to catch errors and cleanup
trap 'error_handler ${LINENO} "$BASH_COMMAND"; cleanup_temp_files' ERR
trap 'cleanup_temp_files' EXIT

# Parse command line arguments
FILTER_ADAPTER=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --adapter)
            FILTER_ADAPTER="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--adapter ADAPTER_NAME]"
            echo ""
            echo "Options:"
            echo "  --adapter ADAPTER_NAME    Create key for a single adapter only"
            echo "  --help, -h                Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                        # Create keys for all adapters"
            echo "  $0 --adapter simple-chat  # Create key for simple-chat adapter only"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORBIT_SCRIPT="$PROJECT_ROOT/bin/orbit.sh"

# Check if orbit.sh exists
if [ ! -f "$ORBIT_SCRIPT" ]; then
    echo -e "${RED}Error: orbit.sh not found at $ORBIT_SCRIPT${NC}"
    exit 1
fi

# Function to check if a key already exists by client_name (renamed key name)
check_key_exists() {
    local key_name=$1
    local list_cmd="$ORBIT_SCRIPT key list --output json"
    local list_output
    local stderr_output
    
    # Capture both stdout and stderr separately
    list_output=$(eval "$list_cmd" 2> >(tee /dev/stderr >&2)) || {
        local exit_code=$?
        echo -e "${YELLOW}    ⚠ Warning: Failed to list keys (exit code: $exit_code)${NC}" >&2
        echo -e "${YELLOW}    Command: $list_cmd${NC}" >&2
        echo -e "${YELLOW}    Assuming key '$key_name' doesn't exist to be safe${NC}" >&2
        return 1
    }
    
    # Check if any key has a matching client_name
    # Using jq if available for reliable JSON parsing, otherwise use grep
    if command -v jq &> /dev/null; then
        local matching_keys
        matching_keys=$(echo "$list_output" | jq -r ".[] | select(.client_name == \"$key_name\") | .client_name" 2>/dev/null)
        if [ -n "$matching_keys" ]; then
            return 0  # Key exists
        fi
    else
        # Fallback: use grep to check for client_name in JSON
        if echo "$list_output" | grep -q "\"client_name\":\s*\"$key_name\""; then
            return 0  # Key exists
        fi
    fi
    
    return 1  # Key doesn't exist
}

# Function to create and rename a key
create_and_rename_key() {
    local adapter=$1
    local key_name=$2
    local prompt_file=$3
    local prompt_name=$4
    local notes=$5
    
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Creating key for adapter: $adapter${NC}"
    echo -e "${YELLOW}Target key name: $key_name${NC}"
    
    # Build the create command
    local create_cmd="$ORBIT_SCRIPT key create --adapter $adapter --name \"$key_name\""
    echo -e "${YELLOW}  Step 1: Building create command...${NC}"
    
    # Add notes if provided
    if [ -n "$notes" ]; then
        echo -e "${GREEN}    ✓ Adding notes for chat interface${NC}"
        # Escape double quotes in notes to prevent command injection/breaking
        local escaped_notes="${notes//\"/\\\"}"
        create_cmd="$create_cmd --notes \"$escaped_notes\""
    fi
    
    # Add prompt file if provided
    if [ -n "$prompt_file" ]; then
        local full_prompt_path="$PROJECT_ROOT/$prompt_file"
        echo -e "${YELLOW}  Step 2: Checking prompt file: $full_prompt_path${NC}"
        if [ -f "$full_prompt_path" ]; then
            echo -e "${GREEN}    ✓ Prompt file found${NC}"
            create_cmd="$create_cmd --prompt-file \"$full_prompt_path\""
            if [ -n "$prompt_name" ]; then
                create_cmd="$create_cmd --prompt-name \"$prompt_name\""
                echo -e "${GREEN}    ✓ Using prompt name: $prompt_name${NC}"
            else
                # Use adapter name as prompt name if not specified
                create_cmd="$create_cmd --prompt-name \"$adapter Prompt\""
                echo -e "${GREEN}    ✓ Using default prompt name: $adapter Prompt${NC}"
            fi
        else
            echo -e "${YELLOW}    ⚠ Warning: Prompt file not found: $full_prompt_path${NC}"
            echo -e "${YELLOW}    Creating key without prompt (you can add it later)${NC}"
        fi
    else
        echo -e "${YELLOW}  Step 2: No prompt file specified${NC}"
    fi
    
    # Create the key and capture the output
    echo -e "${YELLOW}  Step 3: Creating API key...${NC}"
    echo -e "${YELLOW}    Command: $create_cmd${NC}"
    local output
    local stderr_output
    local exit_code
    
    # Capture stdout and stderr separately for better error reporting
    output=$(eval "$create_cmd" 2> >(tee /tmp/orbit_key_create_stderr.$$ >&2)) || {
        exit_code=$?
        stderr_output=$(cat /tmp/orbit_key_create_stderr.$$ 2>/dev/null || echo "")
        rm -f /tmp/orbit_key_create_stderr.$$
        
        echo ""
        echo -e "${RED}    ✗ Failed to create key for $adapter${NC}"
        echo -e "${RED}    Exit code: $exit_code${NC}"
        echo -e "${RED}    Command that failed: $create_cmd${NC}"
        if [ -n "$output" ]; then
            echo -e "${RED}    Stdout output:${NC}"
            echo "$output" | sed 's/^/      /'
        fi
        if [ -n "$stderr_output" ]; then
            echo -e "${RED}    Stderr output:${NC}"
            echo "$stderr_output" | sed 's/^/      /'
        fi
        if [ -z "$output" ] && [ -z "$stderr_output" ]; then
            echo -e "${RED}    No output captured (command may have failed silently)${NC}"
        fi
        echo ""
        return 1
    }
    rm -f /tmp/orbit_key_create_stderr.$$
    
    echo -e "${GREEN}    ✓ Command executed successfully${NC}"
    echo -e "${YELLOW}    Raw output:${NC}"
    echo "$output" | sed 's/^/      /'
    
    # Extract the API key from output
    echo -e "${YELLOW}  Step 4: Extracting API key from output...${NC}"
    # Try multiple patterns to handle different output formats
    local api_key
    # Pattern 1: "API Key: orbit_xxxxx" or "API Key: api_xxxxx"
    api_key=$(echo "$output" | grep -iE '(API Key|api_key)' | grep -oE '(orbit_|api_)[a-zA-Z0-9]+' | head -1)
    
    # Pattern 2: JSON format "api_key": "orbit_xxxxx"
    if [ -z "$api_key" ]; then
        echo -e "${YELLOW}    Trying pattern 2 (JSON format)...${NC}"
        api_key=$(echo "$output" | grep -oE '"api_key"\s*:\s*"[^"]+"' | grep -oE '(orbit_|api_)[a-zA-Z0-9]+' | head -1)
    fi
    
    # Pattern 3: Just look for orbit_ or api_ prefix anywhere in output
    if [ -z "$api_key" ]; then
        echo -e "${YELLOW}    Trying pattern 3 (generic search)...${NC}"
        api_key=$(echo "$output" | grep -oE '(orbit_|api_)[a-zA-Z0-9]{20,}' | head -1)
    fi
    
    if [ -z "$api_key" ]; then
        echo -e "${RED}    ✗ Could not extract API key from output${NC}"
        echo -e "${RED}    Full output was:${NC}"
        echo "$output" | sed 's/^/      /'
        return 1
    fi
    
    echo -e "${GREEN}    ✓ Extracted API key: $api_key${NC}"
    
    # Rename the key
    echo -e "${YELLOW}  Step 5: Renaming key from $api_key to $key_name...${NC}"
    local rename_cmd="$ORBIT_SCRIPT key rename --old-key $api_key --new-key $key_name"
    echo -e "${YELLOW}    Command: $rename_cmd${NC}"
    local rename_output
    local rename_stderr
    local rename_exit_code
    
    # Capture stdout and stderr separately for better error reporting
    rename_output=$(eval "$rename_cmd" 2> >(tee /tmp/orbit_key_rename_stderr.$$ >&2)) || {
        rename_exit_code=$?
        rename_stderr=$(cat /tmp/orbit_key_rename_stderr.$$ 2>/dev/null || echo "")
        rm -f /tmp/orbit_key_rename_stderr.$$
        
        echo ""
        echo -e "${RED}    ✗ Failed to rename key $api_key to $key_name${NC}"
        echo -e "${RED}    Exit code: $rename_exit_code${NC}"
        echo -e "${RED}    Command that failed: $rename_cmd${NC}"
        echo -e "${RED}    Original API key: $api_key${NC}"
        echo -e "${RED}    Target key name: $key_name${NC}"
        if [ -n "$rename_output" ]; then
            echo -e "${RED}    Stdout output:${NC}"
            echo "$rename_output" | sed 's/^/      /'
        fi
        if [ -n "$rename_stderr" ]; then
            echo -e "${RED}    Stderr output:${NC}"
            echo "$rename_stderr" | sed 's/^/      /'
        fi
        if [ -z "$rename_output" ] && [ -z "$rename_stderr" ]; then
            echo -e "${RED}    No output captured (command may have failed silently)${NC}"
        fi
        echo ""
        return 1
    }
    rm -f /tmp/orbit_key_rename_stderr.$$
    
    echo -e "${GREEN}    ✓ Rename command executed successfully${NC}"
    if [ -n "$rename_output" ]; then
        echo -e "${YELLOW}    Rename output:${NC}"
        echo "$rename_output" | sed 's/^/      /'
    fi
    
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ Successfully created and renamed key: $key_name${NC}"
    echo ""
    return 0
}

# Function to check if admin is authenticated
check_admin_auth() {
    echo -e "${YELLOW}Checking authentication status...${NC}"
    local auth_cmd="$ORBIT_SCRIPT auth-status"
    local auth_output
    local auth_stderr
    local exit_code
    
    # Capture stdout and stderr separately
    auth_output=$(eval "$auth_cmd" 2> >(tee /tmp/orbit_auth_stderr.$$ >&2)) || {
        exit_code=$?
        auth_stderr=$(cat /tmp/orbit_auth_stderr.$$ 2>/dev/null || echo "")
        rm -f /tmp/orbit_auth_stderr.$$
        
        echo -e "${RED}✗ Failed to check authentication status${NC}"
        echo -e "${RED}  Exit code: $exit_code${NC}"
        echo -e "${RED}  Command: $auth_cmd${NC}"
        if [ -n "$auth_output" ]; then
            echo -e "${RED}  Stdout: $auth_output${NC}"
        fi
        if [ -n "$auth_stderr" ]; then
            echo -e "${RED}  Stderr: $auth_stderr${NC}"
        fi
        echo -e "${YELLOW}  Please ensure the ORBIT server is running and try again${NC}"
        return 1
    }
    rm -f /tmp/orbit_auth_stderr.$$
    
    # Check if authenticated
    if ! echo "$auth_output" | grep -qiE "(✓ authenticated|authenticated)"; then
        echo -e "${RED}✗ Not authenticated${NC}"
        echo -e "${RED}  Auth output: $auth_output${NC}"
        echo -e "${YELLOW}  Please login as admin first using:${NC}"
        echo -e "${YELLOW}    $ORBIT_SCRIPT login${NC}"
        return 1
    fi
    
    # Check if user is admin
    if ! echo "$auth_output" | grep -qiE "Role:\s*admin"; then
        echo -e "${RED}✗ User is not an admin${NC}"
        echo -e "${RED}  Auth output: $auth_output${NC}"
        echo -e "${YELLOW}  Please login as admin first using:${NC}"
        echo -e "${YELLOW}    $ORBIT_SCRIPT login${NC}"
        return 1
    fi
    
    # Extract username for display
    local username
    username=$(echo "$auth_output" | grep -iE "Username:" | sed 's/.*Username:\s*//i' | head -1)
    
    echo -e "${GREEN}✓ Authenticated as admin${NC}"
    if [ -n "$username" ]; then
        echo -e "${GREEN}  Username: $username${NC}"
    fi
    echo ""
    return 0
}

# Main execution
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Recreating API Keys for All Adapters${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check admin authentication before proceeding
if ! check_admin_auth; then
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}Authentication check failed. Please login as admin first and try again.${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi

echo -e "${YELLOW}Script Configuration:${NC}"
echo -e "  Project Root: $PROJECT_ROOT"
echo -e "  Orbit Script: $ORBIT_SCRIPT"
echo -e "  Total Adapters: ${#adapters[@]}"
if [ -n "$FILTER_ADAPTER" ]; then
    echo -e "  Filter: $FILTER_ADAPTER (single adapter mode)"
fi
echo ""
echo -e "${YELLOW}Starting key creation process...${NC}"
echo ""

# Define adapter mappings: adapter_name -> key_name -> prompt_file -> prompt_name
# Format: "adapter|key_name|prompt_file|prompt_name"

declare -a all_adapters=(
    "simple-chat|default-key|examples/prompts/examples/default-conversational-adapter-prompt.md|Conversational Prompt"
    "simple-chat-with-files|multimodal|examples/prompts/examples/default-file-adapter-prompt.md|Multimodal Prompt"
    "simple-chat-with-files-audio|multimodal-audio|examples/prompts/audio/simple-chat-with-files-audio-prompt.md|Multimodal Audio Prompt"
    "voice-chat|voice-chat|examples/prompts/audio/voice-chat-prompt.md|Voice Chat Prompt"
    "audio-transcription|transcription|examples/prompts/audio/audio-transcription-prompt.md|Audio Transcription Prompt"
    "multilingual-voice-assistant|multilingual-voice-chat|examples/prompts/audio/multilingual-voice-assistant-prompt.md|Multilingual Voice Prompt"
    "premium-voice-chat|premium-voice-chat|examples/prompts/audio/premium-voice-chat-prompt.md|Premium Voice Prompt"
    "local-voice-chat|whisper|examples/prompts/audio/local-audio-transcription-prompt.md|Local Voice Prompt"
    "real-time-voice-chat|real-time-voice-chat|examples/prompts/audio/real-time-voice-chat-prompt.md|Real-Time Voice Chat Prompt"
    "qa-sql|sql-key|examples/prompts/examples/city/city-assistant-normal-prompt.md|SQL QA Prompt"
    "qa-vector-chroma|chroma-key|examples/prompts/examples/city/city-assistant-normal-prompt.md|Chroma QA Prompt"
    # "qa-vector-qdrant-demo|demo-key|..." excluded: requires special Qdrant deployment
    "intent-sql-sqlite-hr|hr|examples/intent-templates/sql-intent-template/examples/sqlite/hr/hr-assistant-prompt.md|HR Assistant Prompt"
    "intent-duckdb-analytics|analytical|examples/intent-templates/duckdb-intent-template/examples/analytics/analytics-assistant-prompt.md|DuckDB Analytics Prompt"
    "intent-duckdb-ev-population|ev|examples/intent-templates/duckdb-intent-template/examples/ev-population/ev-assistant-prompt.md|EV Population Prompt"
    "intent-sql-postgres|postgres|examples/postgres/prompts/customer-assistant-enhanced-prompt.txt|PostgreSQL Customer Orders Prompt"
    "intent-elasticsearch-app-logs|elasticsearch|examples/intent-templates/elasticsearch-intent-template/elasticsearch-log-assistant-prompt.md|Elasticsearch Logs Prompt"
    "intent-firecrawl-webscrape|web|examples/intent-templates/firecrawl-intent-template/firecrawl-knowledge-assistant-prompt.md|Firecrawl Web Prompt"
    "intent-mongodb-mflix|mflix|examples/intent-templates/mongodb-intent-template/mongodb-mflix-assistant-prompt.md|MongoDB MFlix Prompt"
    "intent-http-jsonplaceholder|rest|examples/intent-templates/http-intent-template/examples/jsonplaceholder/jsonplaceholder-api-assistant-prompt.md|JSONPlaceholder API Prompt"
    "intent-http-paris-opendata|paris|examples/intent-templates/http-intent-template/examples/paris-open-data/paris-assistant-prompt.txt|Paris Open Data Prompt"
    "intent-graphql-spacex|spacex|examples/intent-templates/graphql-intent-template/spacex-graphql-assistant-prompt.md|SpaceX GraphQL Prompt"
    "intent-agent-example|agent|examples/intent-templates/agent-template/agent-assistant-prompt.md|Agent Assistant Prompt"
    "file-document-qa|files|examples/prompts/examples/default-file-adapter-prompt.md|File Document QA Prompt"
    "math-teacher-quadratic-files|math-teacher-quadratic|examples/prompts/examples/math-teacher-quadratic/math-teacher-quadratic-prompt.md|Math Teacher Quadratic Prompt"
    "personaplex-assistant|personaplex||PersonaPlex Voice Assistant"
)

# Function to get notes for each adapter (bash 3.2 compatible - no associative arrays)
# These are displayed in the chat interface as intro messages
get_adapter_notes() {
    local adapter_name="$1"
    case "$adapter_name" in
        "simple-chat")
            cat <<'NOTES_EOF'
## Welcome to ORBIT 👋

I'm your **curious and friendly AI assistant**, ready to explore any topic with you!

Whether you want to:
- 🔭 Dive into science and technology
- 💡 Brainstorm creative ideas
- 📚 Learn something new together
- 🤔 Work through a tricky problem

I'll break down complex ideas into simple explanations and keep the conversation flowing.

**What would you like to talk about today?**
NOTES_EOF
            ;;
        "simple-chat-with-files")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Document Assistant 📄

I'm here to help you **understand and extract insights** from your uploaded documents — with complete privacy and no data sharing!

I can work with:
- 📑 PDFs and Word documents
- 📊 Spreadsheets and CSV files
- 🖼️ Images and diagrams
- 📝 JSON and data files
- 🎙️ Audio files for transcription

**What document would you like to explore?**
NOTES_EOF
            ;;
        "simple-chat-with-files-audio")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Multimodal Assistant 🎧

I can help you understand **documents, images, and audio recordings**!

I support:
- 📄 Documents (PDFs, Word, spreadsheets)
- 🖼️ Images and diagrams
- 🎙️ Audio files with transcription

Upload any file and I'll extract insights, summarize content, and answer your questions with precise citations.

**What would you like me to analyze?**
NOTES_EOF
            ;;
        "voice-chat")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Voice Assistant 🎙️

I'm your **conversational voice companion**, ready to chat naturally!

Just speak to me and I'll respond with clear, friendly answers. I keep things concise for voice and use natural language patterns.

**What would you like to talk about?**
NOTES_EOF
            ;;
        "audio-transcription")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Audio Transcription 🎧

I specialize in **transcribing and analyzing audio recordings**!

I can:
- 📝 Transcribe meetings and conversations
- 🔍 Extract key points and action items
- 👥 Identify speakers and topics
- ⏱️ Provide timestamped references

Upload an audio file and I'll help you understand what was said.

**What audio would you like me to transcribe?**
NOTES_EOF
            ;;
        "multilingual-voice-assistant")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Multilingual Voice 🌍

I'm your **multilingual voice assistant**, ready to chat in multiple languages!

I can:
- 🗣️ Detect and respond in your language
- 🔄 Translate between languages
- 🌐 Adapt to cultural context

Speak to me in English, French, Spanish, or many other languages.

**Comment puis-je vous aider? / How can I help you?**
NOTES_EOF
            ;;
        "premium-voice-chat")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Premium Voice ✨

I'm your **sophisticated voice assistant** with premium text-to-speech!

I provide:
- 🎙️ Natural, high-quality voice responses
- 💬 Engaging, thoughtful conversations
- 📚 Clear explanations of complex topics

Speak naturally and I'll respond with polished, professional answers.

**What would you like to discuss?**
NOTES_EOF
            ;;
        "local-voice-chat")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Local Transcription 🔒

I provide **private, local audio transcription** using Whisper!

Benefits:
- 🔐 100% local processing - your audio never leaves your device
- 🌍 Supports 99 languages
- 💰 No API costs
- 📴 Works offline

Upload an audio file and I'll transcribe it completely privately.

**What audio would you like me to transcribe?**
NOTES_EOF
            ;;
        "real-time-voice-chat")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Real-Time Voice 🎧

I'm your **live voice assistant** for real-time, WebSocket-based conversations—like a phone call with AI!

I support:
- 🎙️ **Bidirectional audio streaming** — speak and listen in real time
- ⚡ **Low-latency responses** — quick, natural turn-taking
- ✂️ **Interruption-friendly** — you can jump in anytime
- 🗣️ **Conversational flow** — optimized for voice, not text

Best for interactive voice assistants, customer service bots, and voice-controlled apps.

**Just start speaking—what would you like to talk about?**
NOTES_EOF
            ;;
        "qa-sql")
            cat <<'NOTES_EOF'
## Welcome to ORBIT City Assistant 🏙️

I'm your **municipal information assistant**!

I can help you with:
- 🏛️ City services and programs
- 📋 Permits and licensing
- 🏠 Property and tax information
- 🚧 Public works and infrastructure

Ask me about city regulations, services, or community programs.

**What city information do you need?**
NOTES_EOF
            ;;
        "qa-vector-chroma")
            cat <<'NOTES_EOF'
## Welcome to ORBIT City Assistant 🏙️

I'm your **municipal information assistant** powered by semantic search!

I can help you find information about:
- 🏛️ City services and programs
- 📋 Municipal regulations
- 🏠 Property information
- 🚧 Infrastructure and public works

**What would you like to know about your city?**
NOTES_EOF
            ;;
        "intent-sql-sqlite-hr")
            cat <<'NOTES_EOF'
## Welcome to ORBIT HR Assistant 👥

I'm your **HR data and workforce analytics assistant** for a Canadian organization!

I can help you with:
- 👤 Employee information and search
- 💰 Compensation analysis (all in CAD)
- 🏢 Department and position data
- 📊 Workforce analytics and trends

I support both English and French responses.

**What HR information do you need?**
NOTES_EOF
            ;;
        "intent-duckdb-analytics")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Analytics Assistant 📊

I'm your **business intelligence assistant** powered by DuckDB!

I can help you analyze:
- 💹 Sales performance and revenue
- 📈 Trends and growth patterns
- 🏆 Top performers and rankings
- 🌍 Regional comparisons

Ask me about sales, products, customers, or market trends.

**What business insights do you need?**
NOTES_EOF
            ;;
        "intent-duckdb-ev-population")
            cat <<'NOTES_EOF'
## Welcome to ORBIT EV Policy Analyst ⚡🚗

I'm your **electric vehicle policy analyst** for Washington State's DOL registration database!

I can help state officials analyze:
- 🔋 EV adoption trends (BEV vs PHEV breakdown)
- 🗺️ Geographic distribution by county and legislative district
- ⚡ Charging infrastructure needs and utility coverage
- 📋 CAFV eligibility and incentive program impact
- 🏭 Manufacturer market share and popular models

I support both **English** and **Spanish** responses.

**What EV policy insights do you need? / ¿Qué información sobre vehículos eléctricos necesita?**
NOTES_EOF
            ;;
        "intent-sql-postgres")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Customer Assistant 🛒

I'm your **e-commerce customer service assistant**!

I can help you with:
- 👤 Customer information and profiles
- 📦 Order details and history
- 💳 Payment and shipping status
- 📊 Customer analytics

I support both English and French responses.

**What customer or order information do you need?**
NOTES_EOF
            ;;
        "intent-elasticsearch-app-logs")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Log Analyst 🔍

I'm your friendly **application log analysis assistant**!

I can help you:
- 🚨 Find and analyze errors
- ⚡ Monitor service performance
- 📈 Track response times and trends
- 🔧 Troubleshoot issues

I'll help you understand what your logs are telling you about your system.

**What would you like to investigate?**
NOTES_EOF
            ;;
        "intent-firecrawl-webscrape")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Knowledge Assistant 🌐

I'm your **web knowledge retrieval assistant**!

I can find and present information from:
- 📚 Wikipedia and encyclopedias
- 📖 Official documentation
- 🎓 Educational websites
- 📰 Authoritative sources

Ask me about any topic and I'll retrieve reliable information for you.

**What would you like to learn about?**
NOTES_EOF
            ;;
        "intent-mongodb-mflix")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Movie Database 🎬

I'm your **movie and entertainment data assistant**!

I can help you discover:
- 🎥 Movies by genre, year, or director
- ⭐ Ratings and reviews
- 🏆 Award-winning films
- 📊 Trends and analytics

Explore our extensive film database and find your next favorite movie!

**What movies are you interested in?**
NOTES_EOF
            ;;
        "intent-http-jsonplaceholder")
            cat <<'NOTES_EOF'
## Welcome to ORBIT API Explorer 🔌

I'm your **REST API testing assistant** for JSONPlaceholder!

I can help you explore:
- 📝 Posts and content
- 👤 User profiles
- 💬 Comments and engagement
- ✅ Todos and task management

Perfect for development testing and learning API concepts.

**What API data would you like to explore?**
NOTES_EOF
            ;;
        "intent-http-paris-opendata")
            cat <<'NOTES_EOF'
## Bienvenue sur l'Assistant Paris / Welcome to Paris Assistant 🗼

I'm your **Paris events and activities guide** powered by the official city open data!

Je peux vous aider à découvrir / I can help you discover:
- 🎭 Concerts, exhibitions, and shows
- 🎨 Workshops and cultural activities
- 🏛️ Museum events and guided tours
- 👨‍👩‍👧‍👦 Family-friendly activities
- ♿ Accessible events (PMR, blind, deaf)
- 🆓 Free events across all arrondissements

I support both **English** and **French** responses.

**Que faire à Paris? / What's happening in Paris?**
NOTES_EOF
            ;;
        "intent-graphql-spacex")
            cat <<'NOTES_EOF'
## Welcome to ORBIT SpaceX Explorer 🚀

I'm your **space exploration data assistant**!

I can help you discover:
- 🛸 Launch missions and history
- 🔥 Rocket specifications (Falcon 9, Falcon Heavy)
- 🛰️ Dragon capsules and spacecraft
- 🌍 Launch sites and drone ships

Explore SpaceX's journey to revolutionize space travel!

**What SpaceX mission interests you?**
NOTES_EOF
            ;;
        "intent-agent-example")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Agent Assistant 🤖

I'm your **intelligent agent** powered by function calling!

I can help you with:
- 🧮 Calculations (percentages, arithmetic, averaging)
- 📅 Date & time operations (current time, date math, formatting)
- 🔄 JSON transformations (filter, sort, aggregate)
- 🌤️ Weather (current conditions and forecasts)
- 💱 Finance (stock quotes, currency conversion)
- 📍 Location search (geocoding, place lookup)
- ✅ Productivity (notifications, task creation)

I execute tools to provide accurate, computed answers rather than estimates.

I support both **English** and **French** responses.

**What would you like me to calculate or look up?**
NOTES_EOF
            ;;
        "file-document-qa")
            cat <<'NOTES_EOF'
## Welcome to ORBIT Document Q&A 📚

I'm here to help you **understand your uploaded documents**!

I can analyze:
- 📄 PDFs and Word documents
- 📊 Spreadsheets and data files
- 🖼️ Images and diagrams
- 📝 Any text-based content

Upload a document and ask me questions. I'll provide precise answers with source citations.

**What document would you like to explore?**
NOTES_EOF
            ;;
        "math-teacher-quadratic-files")
            cat <<'NOTES_EOF'
## Welcome to the Quadratic Functions Math Buddy 📐✨

I'm your **high school quadratic specialist**—patient, clear, and here to help with quadratics!

I can help with:
- 📐 Graphing parabolas (standard, vertex, factored form)
- 🧮 Solving quadratics: factoring, square roots, completing the square, quadratic formula
- 📊 Vertex, axis of symmetry, roots, discriminant
- 📄 **Upload exercise sheets, PDFs, or images** of problems and I'll work through them step-by-step

**What quadratic problem would you like to tackle?**
NOTES_EOF
            ;;
        "personaplex-assistant")
            cat <<'NOTES_EOF'
## Welcome to PersonaPlex Voice 🎙️✨

I'm your **full-duplex voice assistant** powered by NVIDIA's PersonaPlex-7B!

Unlike traditional voice assistants, I can:
- 🔄 **Listen while speaking** — true simultaneous conversation
- ⚡ **Respond naturally** — with backchannels like "mm-hmm" and "I see"
- ✂️ **Handle interruptions** — jump in anytime, I'll adapt
- 🗣️ **Speak fluidly** — no awkward turn-taking delays

This is a phone-call style experience—just start talking!

**Note:** Requires WebSocket audio streaming. Use a compatible voice client.
NOTES_EOF
            ;;
        *)
            # No notes for unknown adapters
            echo ""
            ;;
    esac
}

# Filter adapters if --adapter argument is provided
declare -a adapters=()
if [ -n "$FILTER_ADAPTER" ]; then
    echo -e "${BLUE}Filtering for adapter: $FILTER_ADAPTER${NC}"
    for entry in "${all_adapters[@]}"; do
        IFS='|' read -r adapter key_name prompt_file prompt_name <<< "$entry"
        if [ "$adapter" = "$FILTER_ADAPTER" ]; then
            adapters+=("$entry")
            echo -e "${GREEN}✓ Found adapter: $adapter${NC}"
            break
        fi
    done
    
    if [ ${#adapters[@]} -eq 0 ]; then
        echo -e "${RED}✗ Adapter '$FILTER_ADAPTER' not found in the adapter list${NC}"
        echo -e "${YELLOW}Available adapters:${NC}"
        for entry in "${all_adapters[@]}"; do
            IFS='|' read -r adapter key_name prompt_file prompt_name <<< "$entry"
            echo -e "  - $adapter"
        done
        exit 1
    fi
else
    # Use all adapters if no filter specified
    adapters=("${all_adapters[@]}")
fi

# Track success/failure
success_count=0
failure_count=0
skipped_count=0
existing_count=0

# Process each adapter
adapter_index=0
for entry in "${adapters[@]}"; do
    adapter_index=$((adapter_index + 1))  # Safe increment that always succeeds
    IFS='|' read -r adapter key_name prompt_file prompt_name <<< "$entry"
    
    # Look up notes using function (bash 3.2 compatible)
    notes="$(get_adapter_notes "$adapter")"
    
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}[$adapter_index/${#adapters[@]}] Processing Adapter: $adapter${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # Note: Adapters are now defined in config/adapters/*.yaml files (split by category)
    # The script will attempt to create keys for all listed adapters and handle errors
    
    # Check if key exists first (before calling create function which also checks)
    if check_key_exists "$key_name" 2>&1; then
        existing_count=$((existing_count + 1))  # Safe increment
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}[$adapter_index/${#adapters[@]}] Key '$key_name' already exists - skipping${NC}"
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
    elif create_and_rename_key "$adapter" "$key_name" "$prompt_file" "$prompt_name" "$notes" 2>&1; then
        success_count=$((success_count + 1))  # Safe increment
        echo -e "${GREEN}✓ Adapter $adapter_index/${#adapters[@]} completed successfully${NC}"
    else
        create_exit_code=$?
        failure_count=$((failure_count + 1))  # Safe increment
        echo ""
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}✗ Adapter $adapter_index/${#adapters[@]} FAILED: $adapter${NC}"
        echo -e "${RED}  Key name: $key_name${NC}"
        echo -e "${RED}  Exit code: $create_exit_code${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
    fi
    echo ""
done

# Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Summary${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Total Adapters Processed: ${#adapters[@]}${NC}"
if [ $existing_count -gt 0 ]; then
    echo -e "${GREEN}✓ Already existed (skipped): $existing_count keys${NC}"
fi
echo -e "${GREEN}✓ Successfully created: $success_count keys${NC}"
if [ $failure_count -gt 0 ]; then
    echo -e "${RED}✗ Failed: $failure_count keys${NC}"
fi
if [ $skipped_count -gt 0 ]; then
    echo -e "${YELLOW}⊘ Skipped: $skipped_count keys${NC}"
fi
echo ""

if [ $failure_count -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ All API keys created successfully!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 0
else
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}⚠ Some keys failed to create. Check the errors above.${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi
