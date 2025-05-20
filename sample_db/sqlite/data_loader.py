import json
import sqlite3
import os
import re
import string

def tokenize_text(text):
    """Convert text to lowercase, remove punctuation and create tokens."""
    # Convert to lowercase
    text = text.lower()
    
    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Split into tokens (words)
    tokens = text.split()
    
    # Remove stopwords (very basic implementation)
    stopwords = {'the', 'a', 'an', 'and', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'about',
                'that', 'this', 'these', 'those', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'can', 'be',
                'have', 'has', 'had', 'do', 'does', 'did', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what',
                'where', 'when', 'why', 'how', 'which', 'who', 'whom', 'from'}
    
    filtered_tokens = [token for token in tokens if token not in stopwords and len(token) > 1]
    
    return filtered_tokens

def load_city_qa_data(json_path="../sample-data/city-qa-pairs.json", db_path="rag_database.db"):
    """Load QA pairs from JSON into SQLite database."""
    
    if not os.path.exists(json_path):
        print(f"Error: File {json_path} not found.")
        return
    
    # Read JSON data
    with open(json_path, 'r') as file:
        qa_data = json.load(file)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # First clear existing data if any
    cursor.execute("DELETE FROM search_tokens")
    cursor.execute("DELETE FROM city")
    
    # Reset sequence for primary key - safely check if table exists first
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
    if cursor.fetchone():
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='city'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='search_tokens'")
    
    # Insert QA pairs
    for qa_pair in qa_data:
        question = qa_pair['question']
        answer = qa_pair['answer']
        
        # Tokenize question for better search
        tokens = tokenize_text(question)
        question_tokens = ' '.join(tokens)
        
        # Insert into city_qa table
        cursor.execute(
            "INSERT INTO city (question, answer, question_tokens) VALUES (?, ?, ?)",
            (question, answer, question_tokens)
        )
        
        # Get the ID of the inserted row
        qa_id = cursor.lastrowid
        
        # Insert tokens into search_tokens table
        for token in set(tokens):  # Using set to avoid duplicates
            cursor.execute(
                "INSERT INTO search_tokens (token, question_id) VALUES (?, ?)",
                (token, qa_id)
            )
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print(f"Successfully loaded {len(qa_data)} QA pairs into the database.")

if __name__ == "__main__":
    # Check if the database exists, if not create it
    if not os.path.exists("rag_database.db"):
        from create_database import create_database
        create_database()
    
    # Load the data
    load_city_qa_data()