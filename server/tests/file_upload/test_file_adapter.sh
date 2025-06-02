#!/bin/bash

# ORBIT File Adapter Test Script
# Tests the new file-vector adapter with uploaded CSV data

# Configuration
SERVER_URL="http://localhost:3000"
API_KEY="orbit_uTXkrbm53o8RCc08f9LhVYDUMfT8GB2r"  # API key for test_collection
CSV_FILE="test_data_complex.csv"

echo "🧪 ORBIT File Adapter Test Suite"
echo "=================================="
echo "Server: $SERVER_URL"
echo "Collection: test_collection (file-vector adapter)"
echo ""

# Function to check if server is running
check_server() {
    if ! curl -s "$SERVER_URL/health" > /dev/null 2>&1; then
        echo "❌ Error: ORBIT server is not running at $SERVER_URL"
        echo "   Please start the server with: python3 bin/orbit.py --inference-server"
        exit 1
    fi
    echo "✅ Server is running"
}

# Function to upload test file if it doesn't exist in the collection
upload_test_file() {
    if [ ! -f "$CSV_FILE" ]; then
        echo "❌ Error: $CSV_FILE not found!"
        echo "   Creating sample CSV file..."
        
        cat > "$CSV_FILE" << 'EOF'
Name,Position,Department,Salary,Start Date,Email,Phone
John Doe,Software Engineer,Engineering,75000,2022-01-15,john.doe@company.com,555-0101
Jane Smith,Product Manager,Product,85000,2021-06-01,jane.smith@company.com,555-0102
Bob Johnson,Data Scientist,Analytics,80000,2022-03-10,bob.johnson@company.com,555-0103
Alice Brown,UX Designer,Design,70000,2021-11-20,alice.brown@company.com,555-0104
Charlie Wilson,DevOps Engineer,Engineering,78000,2022-07-05,charlie.wilson@company.com,555-0105
Diana Davis,Marketing Specialist,Marketing,65000,2022-02-14,diana.davis@company.com,555-0106
Eve Martinez,Sales Manager,Sales,90000,2020-09-30,eve.martinez@company.com,555-0107
Frank Thompson,HR Manager,Human Resources,72000,2021-12-01,frank.thompson@company.com,555-0108
EOF
        echo "✅ Created sample CSV file: $CSV_FILE"
    fi
    
    echo "📤 Uploading test file..."
    
    UPLOAD_RESPONSE=$(curl -s -X POST "$SERVER_URL/files/upload" \
        -H "X-API-Key: $API_KEY" \
        -H "X-Session-ID: file-adapter-test-upload" \
        -F "file=@$CSV_FILE" \
        -F "metadata={\"description\": \"Employee test data for file adapter\", \"category\": \"HR\"}")
    
    if echo "$UPLOAD_RESPONSE" | grep -q '"success": true'; then
        echo "✅ File uploaded successfully"
    else
        echo "⚠️  Upload response: $UPLOAD_RESPONSE"
    fi
}

# Function to test file adapter with a query
test_file_query() {
    local query="$1"
    local test_name="$2"
    local session_id="file-adapter-test-$(date +%s)-$(echo "$test_name" | tr ' ' '-')"
    
    echo ""
    echo "🔍 Test: $test_name"
    echo "   Query: \"$query\""
    echo "   Adapter: file-vector"
    
    # Test with file-vector adapter
    RESPONSE=$(curl -s -X POST "$SERVER_URL/v1/chat" \
        -H "X-API-Key: $API_KEY" \
        -H "X-Session-ID: $session_id" \
        -H "Content-Type: application/json" \
        -d "{
            \"jsonrpc\": \"2.0\",
            \"method\": \"tools/call\",
            \"params\": {
                \"name\": \"chat\",
                \"arguments\": {
                    \"messages\": [{
                        \"role\": \"user\",
                        \"content\": \"$query\"
                    }],
                    \"adapter\": \"file-vector\"
                }
            },
            \"id\": \"file-adapter-test\"
        }")
    
    # Parse and display response
    if echo "$RESPONSE" | grep -q '"result"'; then
        CONTENT=$(echo "$RESPONSE" | jq -r '.result.choices[0].message.content // .result.content // "No content found"' 2>/dev/null || echo "Could not parse response")
        echo "   ✅ Response received:"
        echo "      $(echo "$CONTENT" | head -3 | sed 's/^/      /')"
        if [ "$(echo "$CONTENT" | wc -l)" -gt 3 ]; then
            echo "      ... (truncated)"
        fi
    else
        echo "   ❌ Error or no response:"
        echo "      $(echo "$RESPONSE" | head -2 | sed 's/^/      /')"
    fi
}

# Function to compare with qa-vector adapter
compare_with_qa_adapter() {
    local query="$1"
    local test_name="$2"
    local session_id="qa-adapter-comparison-$(date +%s)"
    
    echo ""
    echo "🔍 Comparison: $test_name (qa-vector adapter)"
    echo "   Query: \"$query\""
    echo "   Adapter: qa-vector"
    
    RESPONSE=$(curl -s -X POST "$SERVER_URL/v1/chat" \
        -H "X-API-Key: $API_KEY" \
        -H "X-Session-ID: $session_id" \
        -H "Content-Type: application/json" \
        -d "{
            \"jsonrpc\": \"2.0\",
            \"method\": \"tools/call\",
            \"params\": {
                \"name\": \"chat\",
                \"arguments\": {
                    \"messages\": [{
                        \"role\": \"user\",
                        \"content\": \"$query\"
                    }],
                    \"adapter\": \"qa-vector\"
                }
            },
            \"id\": \"qa-adapter-comparison\"
        }")
    
    if echo "$RESPONSE" | grep -q '"result"'; then
        CONTENT=$(echo "$RESPONSE" | jq -r '.result.choices[0].message.content // .result.content // "No content found"' 2>/dev/null || echo "Could not parse response")
        echo "   📋 QA Adapter Response:"
        echo "      $(echo "$CONTENT" | head -2 | sed 's/^/      /')"
    else
        echo "   ❌ QA Adapter Error:"
        echo "      $(echo "$RESPONSE" | head -1 | sed 's/^/      /')"
    fi
}

# Main test execution
main() {
    echo "Starting File Adapter Test Suite..."
    echo ""
    
    # Pre-flight checks
    check_server
    upload_test_file
    
    echo ""
    echo "🚀 Running File Adapter Tests..."
    echo "================================"
    
    # Test 1: Specific employee lookup
    test_file_query "Who is John Doe?" "Employee Lookup"
    compare_with_qa_adapter "Who is John Doe?" "Employee Lookup"
    
    # Test 2: Department-based query
    test_file_query "Show me all engineers" "Department Search"
    compare_with_qa_adapter "Show me all engineers" "Department Search"
    
    # Test 3: Salary information
    test_file_query "What is the salary information for employees?" "Salary Query"
    compare_with_qa_adapter "What is the salary information for employees?" "Salary Query"
    
    # Test 4: Job position search
    test_file_query "Software Engineer" "Position Search"
    compare_with_qa_adapter "Software Engineer" "Position Search"
    
    # Test 5: Contact information
    test_file_query "How can I contact Diana Davis?" "Contact Information"
    compare_with_qa_adapter "How can I contact Diana Davis?" "Contact Information"
    
    # Test 6: Department statistics
    test_file_query "How many employees are in each department?" "Department Statistics"
    
    # Test 7: File-specific query
    test_file_query "What data is in the uploaded CSV file?" "File Content Query"
    
    echo ""
    echo "🎯 File Adapter Tests Complete!"
    echo "==============================="
    echo "Check the responses above to verify that the file-vector adapter"
    echo "is properly retrieving and formatting data from uploaded files."
    echo ""
    echo "Expected behavior:"
    echo "• File adapter should identify content as coming from uploaded CSV"
    echo "• Responses should include file metadata (filename, upload time)"
    echo "• Structured data should be well-formatted"
    echo "• File adapter should outperform qa-vector for file-specific queries"
}

# Run the test suite
main 