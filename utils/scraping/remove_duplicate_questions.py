#!/usr/bin/env python3
"""
Remove Duplicate Questions Script

This script detects and removes duplicate questions from a JSON file containing 
question-answer pairs. It preserves the first occurrence of each unique question
and removes subsequent duplicates.

USAGE:
    python remove_duplicate_questions.py <input_file.json>

EXAMPLES:
    # Remove duplicates from a file named 'questions.json'
    python remove_duplicate_questions.py questions.json
    
    # Remove duplicates from a file in a subdirectory
    python remove_duplicate_questions.py data/qa_pairs.json

INPUT FORMAT:
    The script expects a JSON file containing an array of objects with at least
    a "question" field. Example:
    [
        {"question": "What is Python?", "answer": "A programming language"},
        {"question": "What is Python?", "answer": "A programming language"},  # Duplicate
        {"question": "What is JavaScript?", "answer": "Another language"}
    ]

OUTPUT:
    - If duplicates are found: Creates a new file with ".clean.json" extension
      (e.g., "questions.json" → "questions.clean.json")
    - If no duplicates: Prints a message and doesn't create a new file
    - Console output shows which duplicates were removed and final count

FEATURES:
    - Case-sensitive duplicate detection
    - Preserves the first occurrence of each question
    - Maintains original JSON structure and formatting
    - Provides detailed console feedback
    - Handles file I/O errors gracefully

AUTHOR: QA Pipeline Team
VERSION: 1.0
"""

import json
import argparse
import os

def load_json_file(file_path):
    """Load the JSON file and return its contents."""
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []
    except json.JSONDecodeError:
        print(f"Error: Unable to parse JSON from '{file_path}'.")
        return []

def detect_and_remove_duplicates(data):
    """Detect duplicated questions and return a list with duplicates removed."""
    # Dictionary to track seen questions and their first occurrence
    seen_questions = {}
    cleaned_data = []
    duplicates_found = False
    
    # Process each item
    for item in data:
        question = item.get("question", "")
        if question:  # Only process if question exists
            if question not in seen_questions:
                # First occurrence, keep it
                seen_questions[question] = item
                cleaned_data.append(item)
            else:
                # Duplicate found
                duplicates_found = True
                print(f"Duplicate removed: '{question}'")
    
    if not duplicates_found:
        print("No duplicated questions found. No cleaned file will be created.")
    else:
        print(f"Total unique questions retained: {len(cleaned_data)}")
    
    return cleaned_data, duplicates_found

def save_cleaned_file(data, original_file_path):
    """Save the cleaned data to a new file with .clean.json extension."""
    # Generate the output file name
    base_name, ext = os.path.splitext(original_file_path)
    output_file = f"{base_name}.clean.json"
    
    try:
        with open(output_file, 'w') as file:
            json.dump(data, file, indent=4)
        print(f"Cleaned data saved to '{output_file}'")
    except IOError as e:
        print(f"Error saving cleaned file: {e}")

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Detect and remove duplicated questions from a JSON file.")
    parser.add_argument("file_path", help="Path to the JSON file containing question-answer pairs")
    
    # Parse the arguments
    args = parser.parse_args()
    
    # Load the JSON data using the provided file path
    data = load_json_file(args.file_path)
    
    # Process the data if loaded successfully
    if data:
        # Detect and remove duplicates, get cleaned data and duplicate flag
        cleaned_data, duplicates_found = detect_and_remove_duplicates(data)
        
        # Save the cleaned data only if duplicates were found
        if duplicates_found and cleaned_data:
            save_cleaned_file(cleaned_data, args.file_path)

if __name__ == "__main__":
    main()