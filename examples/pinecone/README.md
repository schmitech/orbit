# Pinecone Examples for Orbit

This directory contains example scripts for using Pinecone as a vector database with the Orbit server. These scripts demonstrate how to create, populate, query, and manage Pinecone indexes for RAG (Retrieval-Augmented Generation) applications.

## Prerequisites

1. **Pinecone Account**: Sign up for a free account at [pinecone.io](https://www.pinecone.io/)

2. **API Key**: Get your API key from the Pinecone console and set it as an environment variable:
   ```bash
   export DATASOURCE_PINECONE_API_KEY="your-api-key-here"
   ```
   
   Or add it to your `.env` file in the project root:
   ```
   DATASOURCE_PINECONE_API_KEY=your-api-key-here
   ```

3. **Python Dependencies**: Install the required packages:
   ```bash
   pip install pinecone>=7.3.0
   ```

4. **Embedding Service**: Ensure you have an embedding service configured in `config/embeddings.yaml`. The scripts support multiple providers (Ollama, OpenAI, etc.).

## Available Scripts

### 1. Create and Populate an Index
Creates a new Pinecone index and populates it with Q&A pairs from a JSON file.

```bash
python create_pinecone_index.py <index_name> <json_file_path>

# Example:
python create_pinecone_index.py city-faq data/city_faq.json
```

**Features:**
- Creates a serverless index in AWS us-east-1 region
- Generates embeddings for questions
- Stores answers as metadata for retrieval
- Performs a test query after ingestion

### 2. Query an Index
Performs semantic search on a Pinecone index to retrieve relevant Q&A pairs.

```bash
python query_pinecone_index.py [index_name] <query_text>

# Examples:
# Query the first available index
python query_pinecone_index.py "What are the parking rules?"

# Query a specific index
python query_pinecone_index.py city-faq "How do I pay property taxes?"
```

### 3. List All Indexes
Shows all indexes in your Pinecone account with their details.

```bash
python list_pinecone_indexes.py
```

**Displays:**
- Index names
- Dimensions
- Metric type (cosine, euclidean, dotproduct)
- Vector count
- Index type (serverless or pod-based)

### 4. Delete an Index
Removes an index from Pinecone.

```bash
python delete_pinecone_index.py <index_name>

# Example:
python delete_pinecone_index.py city-faq
```

## JSON Data Format

The scripts expect Q&A data in the following JSON format:

```json
[
  {
    "question": "What are the library hours?",
    "answer": "The library is open Monday-Friday 9am-8pm, Saturday 10am-6pm, and Sunday 12pm-5pm."
  },
  {
    "question": "How do I get a library card?",
    "answer": "Visit any branch with a photo ID and proof of address. Cards are free for residents."
  }
]
```

## Configuration

The scripts use configuration from:
- `config/config.yaml` - Main configuration
- `config/embeddings.yaml` - Embedding provider settings
- `config/datasources.yaml` - Database connection settings

### Embedding Providers

The scripts support multiple embedding providers configured in `embeddings.yaml`:
- Ollama (local)
- OpenAI
- Anthropic
- Google
- And more...

## Index Specifications

By default, indexes are created with:
- **Type**: Serverless
- **Cloud**: AWS
- **Region**: us-east-1
- **Metric**: Cosine similarity
- **Dimensions**: Automatically detected from embedding model

You can modify these settings in `create_pinecone_index.py` if needed.

## Troubleshooting

### Connection Issues
- Verify your API key is correctly set
- Check network connectivity to Pinecone servers
- Ensure your API key has the necessary permissions

### Index Creation Errors
- Index names must be lowercase and contain only alphanumeric characters and hyphens
- Free tier limits may apply (check Pinecone console)
- Dimensions must match your embedding model

### Query Issues
- Ensure the index exists and contains data
- Verify you're using the same embedding model as during creation
- Check that the embedding service is running

## Integration with Orbit Server

These scripts are designed to work with the Orbit server's embedding services. They:
1. Use the same embedding configuration as the server
2. Create indexes compatible with Orbit's RAG pipeline
3. Store metadata in a format Orbit expects

## Best Practices

1. **Index Naming**: Use descriptive, lowercase names with hyphens (e.g., `customer-support-faq`)

2. **Batch Size**: The default batch size of 100 vectors works well for most cases

3. **Metadata**: Store relevant metadata for filtering and enhanced retrieval:
   - question: The original question
   - answer: The complete answer
   - source: Data source identifier
   - category: Optional categorization

4. **Testing**: Always test queries after creating an index to verify embeddings are working correctly

## Example Workflow

```bash
# 1. Set up environment
export DATASOURCE_PINECONE_API_KEY="your-api-key"

# 2. Create and populate an index
python create_pinecone_index.py product-faq data/product_qa.json

# 3. List indexes to verify
python list_pinecone_indexes.py

# 4. Test with queries
python query_pinecone_index.py product-faq "How do I return a product?"

# 5. Clean up when done
python delete_pinecone_index.py product-faq
```

## Support

For issues or questions:
- Check the [Pinecone documentation](https://docs.pinecone.io/)
- Review the Orbit server documentation
- Check the script's inline documentation and error messages