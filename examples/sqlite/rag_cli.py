#!/usr/bin/env python3
"""
RAG Database CLI - A command-line tool for managing the RAG database system
"""

import argparse
import os
import sys
import sqlite3
import traceback

# Ensure all modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our modules
from db_schema import create_database
from data_loader import load_city_qa_data
from query_engine import search_qa, query_for_rag
from db_manager import (
    delete_all_data, delete_database, get_database_stats,
    list_all_qa_pairs, delete_qa_by_id, add_qa_pair
)

def setup_argparse():
    """Set up command-line argument parsing."""
    parser = argparse.ArgumentParser(description='RAG Database CLI Tool')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Setup database
    setup_parser = subparsers.add_parser('setup', help='Create database and load data')
    setup_parser.add_argument('--data-path', default='../sample-data/city-qa-pairs.json', 
                            help='Path to JSON data file')
    setup_parser.add_argument('--db-path', default='rag_database.db',
                            help='Path to SQLite database file')
    
    # Query
    query_parser = subparsers.add_parser('query', help='Search the database')
    query_parser.add_argument('query', help='Query text')
    query_parser.add_argument('--top-n', type=int, default=3, help='Number of results to return')
    query_parser.add_argument('--db-path', default='rag_database.db',
                            help='Path to SQLite database file')
    query_parser.add_argument('--rag-format', action='store_true', 
                            help='Format results for RAG context')
    
    # Stats
    stats_parser = subparsers.add_parser('stats', help='Get database statistics')
    stats_parser.add_argument('--db-path', default='rag_database.db',
                            help='Path to SQLite database file')
    
    # List QA pairs
    list_parser = subparsers.add_parser('list', help='List QA pairs')
    list_parser.add_argument('--limit', type=int, default=10, help='Number of results to show')
    list_parser.add_argument('--offset', type=int, default=0, help='Offset for pagination')
    list_parser.add_argument('--db-path', default='rag_database.db',
                            help='Path to SQLite database file')
    
    # Add QA pair
    add_parser = subparsers.add_parser('add', help='Add a new QA pair')
    add_parser.add_argument('--question', required=True, help='Question text')
    add_parser.add_argument('--answer', required=True, help='Answer text')
    add_parser.add_argument('--db-path', default='rag_database.db',
                          help='Path to SQLite database file')
    
    # Delete QA pair
    delete_qa_parser = subparsers.add_parser('delete-qa', help='Delete a QA pair by ID')
    delete_qa_parser.add_argument('qa_id', type=int, help='ID of QA pair to delete')
    delete_qa_parser.add_argument('--db-path', default='rag_database.db',
                                help='Path to SQLite database file')
    
    # Clear data
    clear_parser = subparsers.add_parser('clear', help='Clear all data')
    clear_parser.add_argument('--db-path', default='rag_database.db',
                            help='Path to SQLite database file')
    
    # Delete database
    delete_parser = subparsers.add_parser('delete-db', help='Delete the database file')
    delete_parser.add_argument('--db-path', default='rag_database.db',
                             help='Path to SQLite database file')
    
    # Interactive mode
    interactive_parser = subparsers.add_parser('interactive', help='Run in interactive query mode')
    interactive_parser.add_argument('--db-path', default='rag_database.db',
                                  help='Path to SQLite database file')
    
    return parser

def run_interactive_mode(db_path):
    """Run an interactive query session."""
    print("=== RAG Database Interactive Query Mode ===")
    print("Type your questions and get answers from the database.")
    print("Type 'exit', 'quit', or 'q' to exit.")
    print("Type 'stats' to see database statistics.")
    print()
    
    while True:
        query = input("\nEnter your question: ").strip()
        
        if query.lower() in ('exit', 'quit', 'q'):
            print("Exiting interactive mode.")
            break
        
        if query.lower() == 'stats':
            print(get_database_stats(db_path))
            continue
        
        if not query:
            continue
        
        try:
            results = search_qa(query, db_path, top_n=3)
            
            if not results:
                print("No matching information found.")
                continue
            
            print("\nResults:")
            print("--------")
            for i, (question, answer, score) in enumerate(results, 1):
                print(f"{i}. [Relevance: {score:.2f}]")
                print(f"Q: {question}")
                print(f"A: {answer}")
                print()
        except Exception as e:
            print(f"Error executing search: {str(e)}")

def main():
    """Main entry point for the CLI tool."""
    parser = setup_argparse()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Handle commands
    try:
        if args.command == 'setup':
            print(f"Creating database at {args.db_path}...")
            create_database(args.db_path)
            print(f"Loading data from {args.data_path}...")
            load_city_qa_data(args.data_path, args.db_path)
            print("Setup completed successfully.")
        
        elif args.command == 'query':
            if args.rag_format:
                result = query_for_rag(args.query, args.db_path, args.top_n)
                print(result)
            else:
                results = search_qa(args.query, args.db_path, args.top_n)
                if not results:
                    print("No results found.")
                else:
                    for i, (question, answer, score) in enumerate(results, 1):
                        print(f"{i}. [Relevance: {score:.2f}]")
                        print(f"Q: {question}")
                        print(f"A: {answer}")
                        print()
        
        elif args.command == 'stats':
            print(get_database_stats(args.db_path))
        
        elif args.command == 'list':
            list_all_qa_pairs(args.db_path, args.limit, args.offset)
        
        elif args.command == 'add':
            add_qa_pair(args.question, args.answer, args.db_path)
        
        elif args.command == 'delete-qa':
            delete_qa_by_id(args.qa_id, args.db_path)
        
        elif args.command == 'clear':
            confirm = input("Are you sure you want to delete all data? (y/n): ")
            if confirm.lower() == 'y':
                delete_all_data(args.db_path)
            else:
                print("Operation cancelled.")
        
        elif args.command == 'delete-db':
            confirm = input("Are you sure you want to delete the database? (y/n): ")
            if confirm.lower() == 'y':
                delete_database(args.db_path)
            else:
                print("Operation cancelled.")
        
        elif args.command == 'interactive':
            run_interactive_mode(args.db_path)
    
    except sqlite3.Error as e:
        print(f"SQLite error: {str(e)}")
        print("\nDetailed error information:")
        traceback.print_exc()
        
        if "no such table" in str(e):
            print("\nIt looks like the database structure is missing or incomplete.")
            print("Try running the setup command first: python rag_cli.py setup")
    
    except FileNotFoundError as e:
        print(f"File not found: {str(e)}")
        print("Please check the path to the data file or database.")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        print("\nDetailed error information:")
        traceback.print_exc()

if __name__ == "__main__":
    main()