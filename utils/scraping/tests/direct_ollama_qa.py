#!/usr/bin/env python3
"""
Direct Ollama Q&A Extractor for gemma3:12b

This bypasses LangExtract and directly uses the Ollama API to generate Q&A pairs.
Works reliably with gemma3:12b model.
"""

import json
import requests
import argparse
import yaml
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

def load_config():
    """Load configuration from config.yaml"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {'ollama': {'base_url': 'http://localhost:11434', 'model': 'gemma3:12b'}}

def parse_docling_markdown(content: str) -> tuple:
    """Parse Docling markdown content"""
    lines = content.split('\n')
    frontmatter = {}
    body_start = 0

    # Extract title
    for i, line in enumerate(lines):
        if line.strip().startswith('# '):
            frontmatter['title'] = line.replace('# ', '').strip()
            body_start = i + 1
            break

    body = '\n'.join(lines[body_start:]).strip()
    return frontmatter, body

def extract_qa_pairs(text: str, model: str, base_url: str, max_qa: int = 10) -> List[Dict]:
    """Extract Q&A pairs using direct Ollama API call"""

    # Truncate text if too long
    if len(text) > 2000:
        text = text[:2000] + "..."

    prompt = f"""Extract {max_qa} question-answer pairs from this text. Return only valid JSON in this format:

{{
  "qa_pairs": [
    {{"question": "What is...?", "answer": "The answer is..."}},
    {{"question": "Who is...?", "answer": "The person is..."}},
    {{"question": "When was...?", "answer": "It was in..."}}
  ]
}}

Focus on:
- Key facts and dates
- People and organizations
- Mission and purpose
- Services and products
- Contact information
- Important processes

Text to analyze:
{text}

JSON output:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "top_p": 0.8,
            "num_predict": 1000
        }
    }

    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=120
        )

        if response.status_code == 200:
            result = response.json()
            output = result.get('response', '')

            # Parse JSON response
            try:
                data = json.loads(output)
                return data.get('qa_pairs', [])
            except json.JSONDecodeError:
                print(f"Warning: Could not parse JSON response")
                return []
        else:
            print(f"Error: HTTP {response.status_code}")
            return []

    except Exception as e:
        print(f"Error: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Direct Ollama Q&A Extraction')
    parser.add_argument('--mdfile', type=str, required=True, help='Markdown file to process')
    parser.add_argument('--output', '-o', type=str, required=True, help='Output JSON file')
    parser.add_argument('--max-qa', type=int, default=10, help='Maximum Q&A pairs')

    args = parser.parse_args()

    # Load configuration
    config = load_config()
    ollama_config = config.get('ollama', {})
    model = ollama_config.get('model', 'gemma3:12b')
    base_url = ollama_config.get('base_url', 'http://localhost:11434')

    print(f"Direct Ollama Q&A Extractor")
    print(f"Model: {model}")
    print(f"Server: {base_url}")

    # Load and process file
    file_path = Path(args.mdfile)
    if not file_path.exists():
        print(f"Error: File '{args.mdfile}' not found")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_docling_markdown(content)

    if len(body.split()) < 20:
        print("Warning: Document is very short")

    print(f"Processing: {file_path.name} ({len(body)} chars)")

    # Extract Q&A pairs
    qa_pairs = extract_qa_pairs(body, model, base_url, args.max_qa)

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(qa_pairs, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Extracted {len(qa_pairs)} Q&A pairs")
    print(f"✓ Saved to {output_path}")

    # Show sample
    if qa_pairs:
        print("\nSample Q&A pairs:")
        for i, qa in enumerate(qa_pairs[:3], 1):
            print(f"{i}. Q: {qa.get('question', 'N/A')}")
            print(f"   A: {qa.get('answer', 'N/A')[:100]}...")

if __name__ == "__main__":
    main()