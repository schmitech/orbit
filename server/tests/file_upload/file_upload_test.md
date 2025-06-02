# Quick File Upload Test Commands

## 1. Basic CSV Upload Test

```bash
curl -X POST "http://localhost:3000/files/upload" \
  -H "X-API-Key: your-api-key-here" \
  -H "X-Session-ID: test-session-123" \
  -F "file=@test_data.csv" \
  -F "collection_name=employee_data" \
  -F "metadata_title=Employee Test Data" \
  -F "metadata_description=Sample employee data for testing" \
  -F "metadata_tags=employees,test,csv"
```

## 2. Check Upload Service Status

```bash
curl -X GET "http://localhost:3000/files/status" \
  -H "X-API-Key: your-api-key-here"
```

## 3. Query the Uploaded File Content

```bash
curl -X POST "http://localhost:3000/v1/chat" \
  -H "X-API-Key: your-api-key-here" \
  -H "X-Session-ID: test-session-123" \
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
            "content": "What employees are in the CSV file? Can you show me their occupations?"
          }
        ]
      }
    },
    "id": "test-query"
  }'
```

## 4. Minimal Upload (No Metadata)

```bash
curl -X POST "http://localhost:3000/files/upload" \
  -H "X-API-Key: your-api-key-here" \
  -H "X-Session-ID: test-session-simple" \
  -F "file=@test_data.csv"
```

## Expected CSV Processing Result

Your `test_data.csv` contains:
- **8 employees** with Name, Age, City, Occupation
- Will be processed as **spreadsheet content type**
- Text extraction will show: `Name | Age | City | Occupation` format
- Each row will be: `John Doe | 30 | Ottawa | Software Engineer`

## Sample Expected Response

```json
{
  "success": true,
  "message": "File uploaded and processed successfully",
  "data": {
    "file_id": "uuid-here",
    "filename": "test_data.csv", 
    "file_size": 286,
    "mime_type": "text/csv",
    "text_length": 245,
    "text_preview": "Name | Age | City | Occupation\nJohn Doe | 30 | Ottawa | Software Engineer\nJane Smith | 25 | Toronto | Data Scientist...",
    "collection_name": "employee_data"
  }
}
```

## 📝 Notes

- Replace `your-api-key-here` with your actual API key
- Ensure ORBIT server is running on `localhost:3000`
- Install `jq` for pretty JSON formatting: `brew install jq` (macOS) or `sudo apt install jq` (Linux)
- The CSV will be automatically chunked and stored in your vector database if `auto_store_in_vector_db: true` 