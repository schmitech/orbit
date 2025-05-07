import sqlite3
import string
import re
from difflib import SequenceMatcher
from collections import Counter

def tokenize_query(query):
    """Tokenize the user query similarly to how we tokenized the stored data."""
    # Convert to lowercase
    query = query.lower()
    
    # Remove punctuation
    query = query.translate(str.maketrans('', '', string.punctuation))
    
    # Split into tokens
    tokens = query.split()
    
    # Remove stopwords (same as in data_loader.py)
    stopwords = {'the', 'a', 'an', 'and', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'about',
                'that', 'this', 'these', 'those', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'can', 'be',
                'have', 'has', 'had', 'do', 'does', 'did', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what',
                'where', 'when', 'why', 'how', 'which', 'who', 'whom', 'from'}
    
    filtered_tokens = [token for token in tokens if token not in stopwords and len(token) > 1]
    
    return filtered_tokens

def similarity_score(s1, s2):
    """Calculate similarity between two strings using SequenceMatcher."""
    return SequenceMatcher(None, s1, s2).ratio()

def search_qa(query, db_path="rag_database.db", top_n=5, similarity_threshold=0.5):
    """
    Search for relevant QA pairs given a query.
    
    Args:
        query: User's question or keywords
        db_path: Path to the SQLite database
        top_n: Number of results to return
        similarity_threshold: Minimum similarity score to consider a match
        
    Returns:
        List of tuples (question, answer, similarity_score)
    """
    # Tokenize query
    query_tokens = tokenize_query(query)
    
    # If no valid tokens after filtering
    if not query_tokens:
        return []
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # This enables accessing columns by name
    cursor = conn.cursor()
    
    # First approach: Token-based matching
    placeholders = ','.join(['?'] * len(query_tokens))
    cursor.execute(f"""
        SELECT question_id, COUNT(*) as match_count 
        FROM search_tokens 
        WHERE token IN ({placeholders})
        GROUP BY question_id 
        ORDER BY match_count DESC
        LIMIT 20
    """, query_tokens)
    
    candidate_ids = [row['question_id'] for row in cursor.fetchall()]
    
    # If no token matches, try direct fuzzy matching on questions
    if not candidate_ids:
        cursor.execute("SELECT id, question, answer FROM city")
        all_qa = cursor.fetchall()
        
        results = []
        for row in all_qa:
            question_similarity = similarity_score(query.lower(), row['question'].lower())
            if question_similarity >= similarity_threshold:
                results.append((row['question'], row['answer'], question_similarity))
                
        results.sort(key=lambda x: x[2], reverse=True)
        conn.close()
        return results[:top_n]
    
    # Get the full QA pairs for candidate IDs
    placeholders = ','.join(['?'] * len(candidate_ids))
    cursor.execute(f"""
        SELECT id, question, answer
        FROM city
        WHERE id IN ({placeholders})
    """, candidate_ids)
    
    candidate_qa = cursor.fetchall()
    
    # Calculate similarity scores
    results = []
    for row in candidate_qa:
        # Exact token match score (percentage of query tokens found in the question)
        question_tokens = set(tokenize_query(row['question']))
        token_match_ratio = len(set(query_tokens) & question_tokens) / len(query_tokens) if query_tokens else 0
        
        # String similarity score
        string_similarity = similarity_score(query.lower(), row['question'].lower())
        
        # Combined score (weighted average)
        combined_score = (0.7 * token_match_ratio) + (0.3 * string_similarity)
        
        if combined_score >= similarity_threshold:
            results.append((row['question'], row['answer'], combined_score))
    
    # Sort by similarity score and return top N
    results.sort(key=lambda x: x[2], reverse=True)
    
    conn.close()
    return results[:top_n]

def format_results_for_rag(results):
    """Format search results into a context string for RAG."""
    if not results:
        return "No relevant information found."
    
    context = "Here are some relevant city information that might help answer the question:\n\n"
    
    for i, (question, answer, score) in enumerate(results, 1):
        context += f"Q: {question}\nA: {answer}\n\n"
    
    return context

def query_for_rag(query, db_path="rag_database.db", top_n=3):
    """Simple wrapper function that searches and formats results for RAG."""
    results = search_qa(query, db_path, top_n)
    return format_results_for_rag(results)

if __name__ == "__main__":
    # Example usage
    test_query = "How do I report a pothole on my street?"
    results = search_qa(test_query)
    
    print(f"Query: {test_query}\n")
    print("Top Results:")
    for i, (question, answer, score) in enumerate(results, 1):
        print(f"{i}. [Score: {score:.2f}]")
        print(f"Q: {question}")
        print(f"A: {answer}")
        print()
    
    # Example RAG context
    print("\nFormatted for RAG:")
    print(query_for_rag(test_query))