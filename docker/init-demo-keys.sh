#!/bin/bash

# Initialize demo API keys for ORBIT
# Creates default-key for simple-chat adapter if it doesn't exist

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

ORBIT_CLI="/app/bin/orbit.sh"
MAX_WAIT=60
WAIT_INTERVAL=2
ELAPSED=0

echo -e "${BLUE}Initializing demo API keys...${NC}"

# Wait for server to be ready
echo -e "${YELLOW}Waiting for ORBIT server to be ready...${NC}"
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Server is ready${NC}"
        break
    fi
    
    echo -e "${YELLOW}  Waiting... (${ELAPSED}s/${MAX_WAIT}s)${NC}"
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo -e "${RED}✗ Server did not become ready within ${MAX_WAIT} seconds${NC}"
    exit 1
fi

# Wait a bit more for database initialization
sleep 3

# Check if we need to login as admin first
echo -e "${YELLOW}Checking authentication...${NC}"
AUTH_STATUS=$($ORBIT_CLI auth-status 2>&1 || true)
echo -e "${BLUE}Auth status output: $AUTH_STATUS${NC}"

if echo "$AUTH_STATUS" | grep -qiE "(not authenticated|not logged in|bc: command not found)"; then
    echo -e "${YELLOW}Not authenticated, logging in with default admin credentials...${NC}"
    ADMIN_PASSWORD="${ORBIT_DEFAULT_ADMIN_PASSWORD:-admin123}"
    
    # The server automatically creates a default admin user on startup
    # We just need to login with the default credentials
    # Retry login a few times in case the server is still initializing
    MAX_RETRIES=5
    RETRY_DELAY=2
    LOGIN_SUCCESS=false
    
    for i in $(seq 1 $MAX_RETRIES); do
        echo -e "${YELLOW}Login attempt $i/$MAX_RETRIES...${NC}"
        LOGIN_OUTPUT=$(echo "$ADMIN_PASSWORD" | $ORBIT_CLI login --username admin --password-stdin 2>&1)
        LOGIN_EXIT=$?
        
        if [ $LOGIN_EXIT -eq 0 ]; then
            echo -e "${GREEN}✓ Authenticated as admin${NC}"
            LOGIN_SUCCESS=true
            break
        else
            if [ $i -lt $MAX_RETRIES ]; then
                echo -e "${YELLOW}Login failed, waiting ${RETRY_DELAY}s before retry...${NC}"
                echo -e "${BLUE}Login output: $LOGIN_OUTPUT${NC}"
                sleep $RETRY_DELAY
            else
                echo -e "${RED}✗ Failed to authenticate after $MAX_RETRIES attempts${NC}"
                echo -e "${RED}Login output: $LOGIN_OUTPUT${NC}"
                echo -e "${YELLOW}The default admin user should be created automatically by the server.${NC}"
                echo -e "${YELLOW}Attempting to continue anyway - key creation may fail${NC}"
            fi
        fi
    done
else
    echo -e "${GREEN}✓ Already authenticated${NC}"
fi

# Function to check if key exists
check_key_exists() {
    local key_name=$1
    local list_output
    list_output=$($ORBIT_CLI key list --output json 2>&1 || echo "[]")
    
    if command -v jq &> /dev/null; then
        local matching_keys
        matching_keys=$(echo "$list_output" | jq -r ".[] | select(.client_name == \"$key_name\") | .client_name" 2>/dev/null || echo "")
        if [ -n "$matching_keys" ]; then
            return 0  # Key exists
        fi
    else
        if echo "$list_output" | grep -q "\"client_name\":\s*\"$key_name\""; then
            return 0  # Key exists
        fi
    fi
    
    return 1  # Key doesn't exist
}

# Create default-key for simple-chat adapter
if check_key_exists "default-key"; then
    echo -e "${GREEN}✓ API key 'default-key' already exists${NC}"
else
    echo -e "${YELLOW}Creating API key 'default-key' for simple-chat adapter...${NC}"
    
    # Check if prompt file exists (optional)
    PROMPT_FILE="/app/examples/prompts/examples/default-conversational-adapter-prompt.txt"
    CREATE_CMD="$ORBIT_CLI key create --adapter simple-chat --name \"default-key\""
    
    if [ -f "$PROMPT_FILE" ]; then
        CREATE_CMD="$CREATE_CMD --prompt-file \"$PROMPT_FILE\" --prompt-name \"Conversational Prompt\""
    fi
    
    CREATE_OUTPUT=$(eval "$CREATE_CMD" 2>&1 || {
        echo -e "${RED}✗ Failed to create API key${NC}"
        exit 1
    })
    
    # Extract the API key from output
    API_KEY=$(echo "$CREATE_OUTPUT" | grep -oE '(orbit_|api_)[a-zA-Z0-9]{20,}' | head -1)
    
    if [ -z "$API_KEY" ]; then
        # Try JSON format
        API_KEY=$(echo "$CREATE_OUTPUT" | grep -oE '"api_key"\s*:\s*"[^"]+"' | grep -oE '(orbit_|api_)[a-zA-Z0-9]+' | head -1)
    fi
    
    if [ -n "$API_KEY" ]; then
        echo -e "${GREEN}✓ Created API key: $API_KEY${NC}"
        echo -e "${BLUE}  Key name: default-key${NC}"
        echo -e "${BLUE}  Adapter: simple-chat${NC}"
    else
        echo -e "${YELLOW}⚠ Created key but could not extract API key from output${NC}"
        echo -e "${YELLOW}  Output: $CREATE_OUTPUT${NC}"
    fi
fi

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Demo API key initialization complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

