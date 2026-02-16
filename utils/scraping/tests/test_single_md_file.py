#!/usr/bin/env python3
"""
Test script to see what Q&A pairs are generated for a single file
"""

import asyncio
import sys
from pathlib import Path

# Import functions from the main script
from ollama_firecrawl_question_extractor import (
    parse_frontmatter_and_clean, 
    extract_questions_from_text
)

async def test_single_file(file_path):
    """Test Q&A generation for a single file"""
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse and clean
    frontmatter, cleaned_body = parse_frontmatter_and_clean(content)
    
    print(f"📄 File: {file_path}")
    print(f"📏 Content length: {len(cleaned_body)} characters, {len(cleaned_body.split())} words")
    print(f"📋 Title: {frontmatter.get('title', 'N/A')}")
    print("\n" + "="*60)
    print("CLEANED CONTENT:")
    print("="*60)
    print(cleaned_body[:1000] + "..." if len(cleaned_body) > 1000 else cleaned_body)
    print("="*60)
    
    # Test with different MAX_QA values
    for max_qa in [5, 10, 20]:
        print(f"\n🎯 Testing with MAX_QA = {max_qa}")
        print("-" * 40)
        
        try:
            # Extract questions (simulate the MAX_QA limit)
            questions_data = await extract_questions_from_text(str(file_path), cleaned_body, frontmatter)
            questions_limited = questions_data[:max_qa]
            
            print(f"📊 Generated {len(questions_limited)} questions:")
            
            for i, (_, _, question, _) in enumerate(questions_limited, 1):
                print(f"{i:2d}. {question}")
                
                # Check if any question relates to organization description
                if any(keyword in question.lower() for keyword in ['description', 'democracy', 'cooperative', 'co-op', 'community', 'mission', 'purpose']):
                    print("    ✅ This question relates to organization description!")
            
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test-single-file.py <path-to-md-file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if not Path(file_path).exists():
        print(f"Error: File {file_path} not found")
        sys.exit(1)
    
    asyncio.run(test_single_file(file_path))