import sqlite3
import os

def create_database(db_path="rag_database.db"):
    """Create the SQLite database with necessary tables."""
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
    
    # Connect to database (creates it if it doesn't exist)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create city table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS city (
        id INTEGER PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        question_tokens TEXT,
        source TEXT DEFAULT 'city-qa-pairs.json'
    )
    ''')
    
    # Create a table for search tokens to enable basic fuzzy matching
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS search_tokens (
        id INTEGER PRIMARY KEY,
        token TEXT NOT NULL,
        question_id INTEGER,
        FOREIGN KEY (question_id) REFERENCES city(id)
    )
    ''')
    
    # Add indexes for better performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_question_tokens ON city(question_tokens)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_token ON search_tokens(token)')
    
    # Commit changes
    conn.commit()
    
    # Check if tables were created successfully
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='city' OR name='search_tokens')")
    tables = cursor.fetchall()
    
    if len(tables) != 2:
        conn.close()
        raise RuntimeError(f"Failed to create all necessary tables. Only created: {tables}")
    
    # Close connection
    conn.close()
    
    print(f"Database created successfully at {db_path}")

if __name__ == "__main__":
    create_database()