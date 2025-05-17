"""
City Information Query Tool
==========================

This script queries the city information collection in Chroma using semantic search.
It uses the same embedding provider and configuration as the collection creation script.

Usage:
    python query_city_info.py <query_text> [--local] [--db-path PATH] [--results N] [--format {text,json}]

Arguments:
    query_text           The search query text (in quotes if it contains spaces)
    --local              Use local filesystem storage instead of remote Chroma server
    --db-path PATH       Path for local Chroma database (used only with --local)
                         Default: "./chroma_db"
    --results N          Number of results to return (default: 3)
    --format FORMAT      Output format: 'text' or 'json' (default: text)

Examples:
    # Query local database (default)
    python query_city_info.py "What are the parking rules?"
    
    # Query with specific local database path
    python query_city_info.py "How do I report a pothole?" --local --db-path /path/to/chroma_db
    
    # Get more results in JSON format
    python query_city_info.py "How do I pay my taxes?" --results 5 --format json
"""

import yaml
import os
import sys
import json
import asyncio
import chromadb
import argparse
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Dict, Any
import textwrap

# Add server directory to path for importing embedding services
server_path = Path(__file__).resolve().parents[4] / "server"
sys.path.append(str(server_path))

# Load environment variables from server's .env file
server_env_path = server_path / ".env"
if server_env_path.exists():
    load_dotenv(server_env_path)
else:
    print(f"Warning: .env file not found at {server_env_path}")

# Import the same embedding factory used during creation
from embeddings.base import EmbeddingServiceFactory

def load_config():
    """Load configuration from the config file"""
    # Try to find config.yaml in project root first, then in config subdirectory
    config_path = Path(__file__).resolve().parents[4] / "config.yaml"
    if not config_path.exists():
        config_path = Path(__file__).resolve().parents[4] / "config" / "config.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found in {config_path.parent} or {config_path.parent}/config/")
    
    print(f"Loading config from: {config_path}")
    return yaml.safe_load(config_path.read_text())

def format_value(value, indent=2, width=100):
    """Format a value nicely for display, handling different types appropriately"""
    if isinstance(value, dict):
        # Pretty format nested dictionary with indentation
        result = "{\n"
        for k, v in value.items():
            formatted_v = format_value(v, indent + 2, width)
            result += " " * (indent + 2) + f'"{k}": {formatted_v},\n'
        result += " " * indent + "}"
        return result
    elif isinstance(value, list):
        # Handle lists with proper formatting
        if not value:
            return "[]"
        elif all(isinstance(item, (str, int, float, bool)) for item in value):
            # Simple list with primitive types
            list_str = ", ".join([repr(item) for item in value])
            if len(list_str) > width - indent:
                result = "[\n"
                for item in value:
                    result += " " * (indent + 2) + repr(item) + ",\n"
                result += " " * indent + "]"
                return result
            else:
                return f"[{list_str}]"
        else:
            # Complex list with nested structures
            result = "[\n"
            for item in value:
                formatted_item = format_value(item, indent + 2, width)
                result += " " * (indent + 2) + formatted_item + ",\n"
            result += " " * indent + "]"
            return result
    elif isinstance(value, str):
        if "\n" in value or len(value) > width - indent:
            # Multiline or long string
            wrapped = textwrap.fill(
                value, 
                width=width - indent - 2,
                initial_indent=" " * indent,
                subsequent_indent=" " * indent
            )
            return f'"""\n{wrapped}\n""" '
        else:
            return repr(value)
    else:
        return repr(value)

def format_metadata_for_llm(metadata: Dict[str, Any], max_width: int = 100) -> str:
    """
    Format metadata to be more readable for an LLM, prioritizing important fields and
    presenting them in a structured way that facilitates summarization.
    """
    # Order metadata by priority of importance for LLM summarization
    priority_keys = [
        'question', 'department', 'answer', 'category', 'intent', 
        'keywords', 'question_variants'
    ]
    
    # Start with the priority keys in order
    formatted = []
    for key in priority_keys:
        if key in metadata:
            value = metadata[key]
            formatted_value = format_value(value, indent=2, width=max_width)
            formatted.append(f"{key}: {formatted_value}")
    
    # Then add all other keys not in the priority list
    for key, value in metadata.items():
        if key not in priority_keys:
            formatted_value = format_value(value, indent=2, width=max_width)
            formatted.append(f"{key}: {formatted_value}")
    
    return "\n".join(formatted)

def color_text(text, color_code):
    """Add color to text for terminal output"""
    return f"\033[{color_code}m{text}\033[0m"

def highlight_text(text, query_terms):
    """Highlight query terms in text for better visualization"""
    # Convert query terms to lowercase for case-insensitive matching
    query_terms = [term.lower() for term in query_terms]
    
    # Split text into words to highlight matches
    words = text.split()
    for i, word in enumerate(words):
        # Check if the lowercased word (stripped of punctuation) matches any query term
        if word.lower().strip('.,;:!?()[]{}"\'-') in query_terms:
            words[i] = color_text(word, "1;33")  # Bold yellow
    
    return " ".join(words)

async def query_city_info(
    test_query: str, 
    use_local: bool = False, 
    db_path: str = "./chroma_db",
    num_results: int = 3,
    output_format: str = "text"
):
    """Query the city information collection"""
    config = load_config()

    # Get the embedding provider from config
    embedding_provider = config['embedding']['provider']
    collection_name = "city_info"  # Fixed collection name for city information
    
    print("\nConfiguration:")
    print(f"Embedding Provider: {embedding_provider}")
    print(f"Collection: {collection_name}")
    print(f"Results Requested: {num_results}")
    print(f"Output Format: {output_format}")
    
    # Initialize client based on mode
    if use_local:
        local_db_path = Path(db_path).resolve()
        if not os.path.exists(local_db_path):
            print(f"Error: Local database path {local_db_path} does not exist.")
            return
        
        client = chromadb.PersistentClient(path=str(local_db_path))
        print(f"Using local filesystem persistence at: {local_db_path}")
    else:
        chroma_host = config['datasources']['chroma']['host']
        chroma_port = config['datasources']['chroma']['port']
        print(f"Using Chroma server at: {chroma_host}:{chroma_port}")
        client = chromadb.HttpClient(host=chroma_host, port=int(chroma_port))
    
    # Initialize embedding service
    embedding_service = EmbeddingServiceFactory.create_embedding_service(config, embedding_provider)
    await embedding_service.initialize()
    
    try:
        # Test connection by getting dimensions
        dimensions = await embedding_service.get_dimensions()
        print(f"Successfully connected to embedding service (dimensions: {dimensions})")
        
        # Generate embedding for query
        print(f"\nGenerating embedding for query: '{test_query}'")
        query_embedding = await embedding_service.embed_query(test_query)
        
        # Get the collection
        try:
            collection = client.get_collection(name=collection_name)
            print(f"Successfully connected to collection: {collection_name}")
        except Exception as e:
            print(f"Error accessing collection '{collection_name}': {str(e)}")
            return
            
        # Perform query
        print("\nExecuting query...")
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=num_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # Extract query terms for highlighting
        query_terms = [term.lower() for term in test_query.split() if len(term) > 3]
        
        # Prepare output based on format
        if output_format.lower() == 'json':
            # JSON output format for programmatic use
            output = {
                "query": test_query,
                "timestamp": datetime.now().isoformat(),
                "results": []
            }
            
            if results['metadatas'] and len(results['metadatas'][0]) > 0:
                for i, (doc, metadata, distance) in enumerate(zip(
                    results['documents'][0], 
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    similarity = 1 - distance
                    result_item = {
                        "rank": i + 1,
                        "similarity": round(similarity, 4),
                        "document": doc,
                        "metadata": metadata
                    }
                    output["results"].append(result_item)
            
            # Print JSON output
            print(json.dumps(output, indent=2))
            
        else:
            # Human-readable text output
            print(f"\n{'='*80}")
            print(f"QUERY: {color_text(test_query, '1;36')}")  # Cyan
            print(f"{'='*80}")
            
            if results['metadatas'] and len(results['metadatas'][0]) > 0:
                for i, (doc, metadata, distance) in enumerate(zip(
                    results['documents'][0], 
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    similarity = 1 - distance
                    
                    print(f"\n{color_text(f'RESULT #{i+1}', '1;32')} " + 
                          f"{color_text(f'(similarity: {similarity:.4f})', '0;32')}")
                    print(f"{'-'*80}")
                    
                    # Top section with key information
                    if 'department' in metadata and 'question' in metadata:
                        print(f"Department: {color_text(metadata['department'], '1;35')}")
                        print(f"Question: {color_text(metadata['question'], '1;34')}")
                        
                        # If answer exists, highlight query terms
                        if 'answer' in metadata:
                            print(f"\n{color_text('Answer:', '1;33')}")
                            highlighted_answer = highlight_text(metadata['answer'], query_terms)
                            print(textwrap.fill(highlighted_answer, width=80, 
                                              initial_indent="  ", subsequent_indent="  "))
                    
                    # Full LLM-friendly metadata
                    print(f"\n{color_text('Enhanced Metadata for LLM:', '1;36')}")
                    print(f"{'-'*40}")
                    formatted_metadata = format_metadata_for_llm(metadata)
                    print(formatted_metadata)
                    
                    # Document content
                    print(f"\n{color_text('Document Content:', '1;36')}")
                    print(f"{'-'*40}")
                    print(textwrap.fill(doc, width=80, initial_indent="  ", subsequent_indent="  "))
                    
                    print(f"\n{'='*80}")
            else:
                print(f"\n{color_text('No results found', '1;31')}")
    
    except Exception as e:
        print(f"Error during query execution: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up
        await embedding_service.close()

async def main():
    parser = argparse.ArgumentParser(description='Query the city information collection')
    parser.add_argument('query', help='The search query text')
    parser.add_argument('--local', action='store_true', help='Use local filesystem storage instead of remote Chroma server')
    parser.add_argument('--db-path', type=str, default='./chroma_db', help='Path for local Chroma database (used only with --local)')
    parser.add_argument('--results', type=int, default=3, help='Number of results to return (default: 3)')
    parser.add_argument('--format', type=str, choices=['text', 'json'], default='text', 
                        help='Output format: text (human-readable) or json (machine-readable)')
    args = parser.parse_args()
    
    await query_city_info(
        args.query,
        use_local=args.local,
        db_path=args.db_path,
        num_results=args.results,
        output_format=args.format
    )

if __name__ == "__main__":
    asyncio.run(main())