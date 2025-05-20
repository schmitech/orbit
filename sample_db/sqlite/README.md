# Sample SQLite DB

A simple SQLite for storing and retrieving city information. This project provides tools for setting up a question-answering database, querying with fuzzy search.

## Installation & Setup

### 1. Initialize the Database

```bash
python rag_cli.py setup --data-path sample-data/city-qa-pairs.json
```

This will:
- Create the SQLite database (`rag_database.db`)
- Set up the necessary tables and indexes
- Load the sample city Q&A data

## Using the CLI

The project provides a command-line interface (`rag_cli.py`) with several commands:

### Query the Database

```bash
# Basic query
python rag_cli.py query "How do I report a pothole on my street?"

# Get more results
python rag_cli.py query "Where can I pay my water bill?" --top-n 5

# Format for RAG prompt
python rag_cli.py query "What are the hours for the recycling center?" --rag-format
```

### Interactive Mode

For multiple queries in a session:

```bash
python rag_cli.py interactive
```

This allows you to enter multiple queries without restarting the program. Type `exit`, `quit`, or `q` to exit, and `stats` to see database statistics.

### Database Management

```bash
# View database statistics
python rag_cli.py stats

# List QA pairs
python rag_cli.py list --limit 10 --offset 0

# Add a new QA pair
python rag_cli.py add --question "How do I contact the mayor?" --answer "The mayor can be contacted via email at mayor@city.gov or by phone at 555-123-4567."

# Delete a QA pair
python rag_cli.py delete-qa 123

# Clear all data (while preserving structure)
python rag_cli.py clear

# Delete the entire database
python rag_cli.py delete-db
```

## How It Works

### Fuzzy Search Implementation

The system uses a combination of techniques for effective fuzzy search without requiring vector embeddings:

1. **Tokenization**: Questions are broken down into meaningful tokens, with stopwords removed
2. **Token Matching**: Finds documents containing tokens from the query
3. **String Similarity**: Uses sequence matching to calculate similarity scores
4. **Combined Scoring**: Weights token matching and string similarity for better results

### Database Structure

The SQLite database contains two main tables:

1. **city_qa**: Stores question-answer pairs with tokenized questions
2. **search_tokens**: Maps tokens to questions for efficient search

## Extending the System

### Adding More Data

To add more question-answer pairs:

1. Create a JSON file in the same format as `city-qa-pairs.json`:
```json
[
    {
        "question": "Your question here?",
        "answer": "Your answer here."
    },
    ...
]
```

2. Load it using the CLI:
```bash
python rag_cli.py setup --data-path your-data.json
```

Or add individual pairs:
```bash
python rag_cli.py add --question "Your question?" --answer "Your answer."
```

## Troubleshooting

### Common Issues

1. **"No such table" error**
   - Run the setup command: `python rag_cli.py setup`

2. **No results for a query**
   - Try using more generic terms
   - Reduce the relevance threshold in config.json
   - Check if the database has relevant data with `python rag_cli.py list`

3. **LLM integration not working**
   - Ensure you have the required packages installed (openai, anthropic, or ollama)
   - Check API keys are set as environment variables
   - For Ollama, ensure the local server is running

## License

[Specify your license here]

## Contributing

[Contribution guidelines if applicable]

## Acknowledgments

This project uses the BaseRetriever pattern which can be extended to support other retrieval systems like ChromaDB, Pinecone, or other vector databases.