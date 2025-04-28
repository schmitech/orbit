import sqlite3
import os

def delete_all_data(db_path="rag_database.db"):
    """Delete all data from the database tables while keeping the structure."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Delete all data from tables
    cursor.execute("DELETE FROM search_tokens")
    cursor.execute("DELETE FROM city")
    
    # Reset auto-increment counters
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='search_tokens'")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='city'")
    
    conn.commit()
    conn.close()
    print("All data has been deleted from the database.")

def delete_database(db_path="rag_database.db"):
    """Delete the entire database file."""
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"Database file {db_path} has been deleted.")
        except Exception as e:
            print(f"Error deleting database file: {e}")
    else:
        print(f"Database file {db_path} does not exist.")

def get_database_stats(db_path="rag_database.db"):
    """Get statistics about the database."""
    if not os.path.exists(db_path):
        return "Database does not exist."
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get row counts
    cursor.execute("SELECT COUNT(*) FROM city")
    qa_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM search_tokens")
    token_count = cursor.fetchone()[0]
    
    # Get database file size
    db_size = os.path.getsize(db_path) / (1024 * 1024)  # Size in MB
    
    # Get some sample data
    cursor.execute("SELECT question, answer FROM city LIMIT 3")
    samples = cursor.fetchall()
    
    conn.close()
    
    stats = f"""
Database Statistics:
-------------------
Database file: {db_path}
Database size: {db_size:.2f} MB
Number of QA pairs: {qa_count}
Number of search tokens: {token_count}

Sample QA pairs:
"""
    
    for i, (question, answer) in enumerate(samples, 1):
        stats += f"\n{i}. Q: {question}\n   A: {answer}\n"
    
    return stats

def delete_qa_by_id(qa_id, db_path="rag_database.db"):
    """Delete a specific QA pair by ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # First delete related tokens
    cursor.execute("DELETE FROM search_tokens WHERE city_id = ?", (qa_id,))
    
    # Then delete the QA pair
    cursor.execute("DELETE FROM city WHERE id = ?", (qa_id,))
    
    rows_affected = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if rows_affected > 0:
        print(f"QA pair with ID {qa_id} has been deleted.")
    else:
        print(f"No QA pair found with ID {qa_id}.")

def list_all_qa_pairs(db_path="rag_database.db", limit=10, offset=0):
    """List all QA pairs with pagination."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM city")
    total_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT id, question, answer FROM city LIMIT ? OFFSET ?", (limit, offset))
    qa_pairs = cursor.fetchall()
    
    conn.close()
    
    print(f"Listing QA pairs {offset+1}-{min(offset+limit, total_count)} of {total_count}:")
    print("-" * 80)
    
    for qa_id, question, answer in qa_pairs:
        print(f"ID: {qa_id}")
        print(f"Q: {question}")
        print(f"A: {answer}")
        print("-" * 80)
    
    return qa_pairs

def add_qa_pair(question, answer, db_path="rag_database.db"):
    """Add a new QA pair to the database."""
    # Import tokenize_text from data_loader
    from data_loader import tokenize_text
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Tokenize question
    tokens = tokenize_text(question)
    question_tokens = ' '.join(tokens)
    
    # Insert QA pair
    cursor.execute(
        "INSERT INTO city (question, answer, question_tokens) VALUES (?, ?, ?)",
        (question, answer, question_tokens)
    )
    
    # Get the ID of the inserted row
    qa_id = cursor.lastrowid
    
    # Insert tokens
    for token in set(tokens):
        cursor.execute(
            "INSERT INTO search_tokens (token, city_id) VALUES (?, ?)",
            (token, qa_id)
        )
    
    conn.commit()
    conn.close()
    
    print(f"Added new QA pair with ID {qa_id}.")
    return qa_id

if __name__ == "__main__":
    # Example usage
    print(get_database_stats())
    
    # Uncomment to test other functions
    # delete_all_data()
    # list_all_qa_pairs(limit=5)
    # add_qa_pair("What's the process for getting a driver's license?", "Visit the DMV with identification and proof of residence.")
    # delete_qa_by_id(1)