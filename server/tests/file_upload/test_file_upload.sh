#!/bin/bash

# ORBIT File Upload Test Script
# Tests file upload functionality with test_data.csv

# Configuration
SERVER_URL="http://localhost:3000"
API_KEY="orbit_uTXkrbm53o8RCc08f9LhVYDUMfT8GB2r"  # API key for test_collection
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CSV_FILE="$SCRIPT_DIR/test_data.csv"

echo "🚀 Testing ORBIT File Upload Endpoints"
echo "======================================"

# Check if CSV file exists
if [ ! -f "$CSV_FILE" ]; then
    echo "❌ Error: $CSV_FILE not found!"
    echo "📁 Current directory: $(pwd)"
    echo "📁 Script directory: $SCRIPT_DIR"
    echo "🔍 Looking for file at: $CSV_FILE"
    exit 1
fi

echo "📄 File to upload: $CSV_FILE"
echo "📊 File size: $(du -h $CSV_FILE | cut -f1)"
echo ""

# Test 1: Basic file upload
echo "🧪 Test 1: Basic CSV File Upload"
echo "--------------------------------"
curl -X POST "$SERVER_URL/files/upload" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: test-session-$(date +%s)" \
  -F "file=@$CSV_FILE" \
  -F "collection_name=test_collection" \
  -F "metadata_title=Employee Test Data" \
  -F "metadata_description=CSV file containing employee information for testing" \
  -F "metadata_tags=test,employees,csv,sample" \
  | jq '.' || echo "📝 Note: Install jq for pretty JSON formatting"

echo -e "\n"

# Test 2: File upload status check
echo "🧪 Test 2: File Upload Service Status"
echo "------------------------------------"
curl -X GET "$SERVER_URL/files/status" \
  -H "X-API-Key: $API_KEY" \
  | jq '.' || echo "📝 Note: Install jq for pretty JSON formatting"

echo -e "\n"

# Test 3: Upload without optional metadata
echo "🧪 Test 3: Simple Upload (No Metadata)"
echo "--------------------------------------"
curl -X POST "$SERVER_URL/files/upload" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: test-session-simple-$(date +%s)" \
  -F "file=@$CSV_FILE" \
  | jq '.' || echo "📝 Note: Install jq for pretty JSON formatting"

echo -e "\n"

# Test 4: Try to query the uploaded file content via chat
echo "🧪 Test 4: Query Uploaded File via Chat"
echo "---------------------------------------"
curl -X POST "$SERVER_URL/v1/chat" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: test-session-chat-$(date +%s)" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "chat",
      "arguments": {
        "messages": [
          {
            "role": "user", 
            "content": "What information is in the CSV file I just uploaded? Can you tell me about the employees?"
          }
        ]
      }
    },
    "id": "test-file-query"
  }' \
  | jq '.' || echo "📝 Note: Install jq for pretty JSON formatting"

echo -e "\n"

# Test 5: Batch upload (testing with the same file multiple times)
echo "🧪 Test 5: Batch Upload Test"
echo "----------------------------"
curl -X POST "$SERVER_URL/files/upload/batch" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Session-ID: test-session-batch-$(date +%s)" \
  -F "files=@$CSV_FILE" \
  -F "files=@$CSV_FILE" \
  -F "collection_name=batch_test_collection" \
  | jq '.' || echo "📝 Note: Install jq for pretty JSON formatting"

echo -e "\n"
echo "✅ File upload tests completed!"
echo ""
echo "📋 Quick Test Summary:"
echo "- Basic upload with metadata"
echo "- Service status check" 
echo "- Simple upload without metadata"
echo "- Chat query of uploaded content"
echo "- Batch upload test"
echo ""
echo "🔧 To customize this test:"
echo "1. Update API_KEY with your actual API key"
echo "2. Change SERVER_URL if running on different host/port"
echo "3. Modify collection names as needed" 