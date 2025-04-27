"""
Google Question Extractor

This script extracts questions and answers from markdown documentation files using Google's Gemini AI model.

Overview:
---------
The script processes markdown files from a specified directory, extracting relevant questions
that can be answered from the content, and then generates answers to those questions.
It creates a JSON file containing structured question-answer pairs, which can be used for:
- Creating FAQs 
- Building Q&A datasets
- Training chatbots or Q&A systems
- Knowledge base construction

Features:
---------
1. Bulk processing of markdown files with concurrent execution
2. Caching of questions and answers to reduce API calls
3. Command-line arguments for flexibility
4. Progress reporting
5. Intelligent prompt design to ensure high-quality questions and answers

Requirements:
------------
- Python 3.7+
- Google Gemini API key (set in .env file)
- Required packages: google-generativeai, python-dotenv

Environment Variables:
---------------------
- GOOGLE_API_KEY: Your Google Gemini API key
- GOOGLE_GENAI_MODEL: Model to use (default: gemini-2.0-flash)
- MAX_QA_PAIRS: Maximum number of question-answer pairs per file (default: 300)
- MAX_CONCURRENT_REQUESTS: Maximum concurrent API requests (default: 5)

Usage:
------
Note: Run docling-crawler.py to get the markdown files first.

python google_question_extractor.py --input ./docs --output ./questions.json

Command-line Arguments:
---------------------
--input, -i    : Input directory containing markdown files (default: ./data/docs)
--output, -o   : Output JSON file path (default: ./data/questions.json)
--quiet, -q    : Run quietly with minimal output
--no-cache     : Skip cache and regenerate all questions and answers

Output Format:
-------------
The output JSON file contains an array of objects with these fields:
- source: Path to the source file
- question: Generated question
- answer: Generated answer

Cache Files:
-----------
For each processed file, the script creates two cache files:
- {file_path}.json: Cached questions for the file
- {file_path}.result.json: Cached question-answer pairs

How it Works:
------------
1. Loads markdown files from the input directory
2. For each file:
   a. Extracts 5-10 high-quality questions (or loads from cache)
   b. Generates answers for each question (or loads from cache)
3. Combines all results into a single JSON file
"""

import json
import argparse
import os
import asyncio
import re
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Check for Google API key
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_GENAI_MODEL = os.getenv('GOOGLE_GENAI_MODEL', 'gemini-2.0-flash')

if not GOOGLE_API_KEY:
    raise ValueError("No Google API key found. Please set GOOGLE_API_KEY in your .env file.")

# Import Google Generative AI
try:
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    print(f"Google Gemini API configured with model: {GOOGLE_GENAI_MODEL}")
except ImportError:
    raise ImportError("Google Generative AI library not found. Please install it with: pip install google-generativeai")

# Constants
MAX_QA_PAIRS = int(os.getenv('MAX_QA_PAIRS', '300'))
MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT_REQUESTS', '5'))
throttler = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Helper functions
def load_markdown_files_from_directory(directory):
    """Load all markdown files from a directory."""
    files = []
    directory_path = Path(directory)
    
    if not directory_path.exists():
        print(f"Warning: Directory '{directory}' does not exist.")
        return files
    
    for file_path in directory_path.glob('**/*.md'):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                files.append((str(file_path), content))
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
    
    return files

def flatten_nested_lists(nested_lists):
    """Flatten a list of lists."""
    flattened_list = []
    for sublist in nested_lists:
        flattened_list.extend(sublist)
    return flattened_list

async def run_model(prompt):
    """Run the Google Gemini model with the given prompt."""
    try:
        async with throttler:
            model = genai.GenerativeModel(GOOGLE_GENAI_MODEL)
            response = await asyncio.to_thread(
                model.generate_content, 
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 1024,
                }
            )
            
            if hasattr(response, 'text'):
                return response.text.strip()
            else:
                return str(response).strip()
    except Exception as e:
        print(f"Error generating content: {e}")
        return "ERROR"

def extract_questions_from_output(output):
    """Extract numbered questions from text output."""
    question_pattern = re.compile(r"^\s*\d+\.\s*(.+)$", re.MULTILINE)
    questions = question_pattern.findall(output)
    
    # Remove incomplete questions
    if questions and not re.search(r"[.!?)]$", questions[-1].strip()):
        print(f"WARNING: Removing incomplete question: '{questions[-1]}'")
        questions.pop()
    
    return questions

async def extract_questions_from_text(file_path, text):
    """Extract questions from text using the AI model."""
    # Improved prompt for question extraction
    extraction_prompt = f"""
    Read the following text carefully and extract THE MAXIMUM NUMBER OF QUESTIONS possible that can be answered using only this content.
    
    IMPORTANT GUIDELINES:
    1. Be COMPREHENSIVE - create questions that cover EVERY piece of information in the text, no matter how small
    2. Include questions about all facts, concepts, definitions, examples, steps, and details
    3. Break down complex information into multiple specific questions
    4. Ensure all sections, paragraphs, and sentences of the text are represented in your questions
    5. Only create questions that have clear, complete answers in the text
    6. Format your response as a numbered list like this:
       1. Question one?
       2. Question two?
    
    Your goal is to create so many questions that if someone only read the questions and answers,
    they would have complete knowledge of all information contained in the original text.
    DO NOT OMIT ANY INFORMATION - be exhaustive in your coverage.
    
    Here's the text:
    
    {text}
    """
    
    output = await run_model(extraction_prompt)
    questions = extract_questions_from_output(output)
    
    # Return questions with source information
    return [(file_path, text, question.strip()) for question in questions]

async def generate_answer(question, source):
    """Generate an answer for a question using the given source text."""
    answering_prompt = f"""
    Answer the following question based solely on the provided source text.
    
    IMPORTANT GUIDELINES:
    1. Answer directly and efficiently without unnecessary phrases like "The source text states that" or "According to the text"
    2. Provide COMPLETE, DETAILED answers with ALL relevant information from the text
    3. Include all facts, figures, examples, and context that relate to the question
    4. Use a natural, conversational tone
    5. If the exact answer isn't explicitly in the text, say "The information is not provided in the text" - don't guess
    6. Format your answer clearly using plain language
    7. Ensure your answer is comprehensive - if multiple parts of the text address the question, include all relevant information
    
    Question: {question}
    
    Source text:
    {source}
    """
    
    answer = await run_model(answering_prompt)
    return answer

async def process_file(file_path, text, progress_counter, verbose=True, no_cache=False):
    """Process a file to extract questions and generate answers."""
    questions_file_name = f"{file_path}.json"
    
    # Try to load cached questions if caching is enabled
    if not no_cache and Path(questions_file_name).is_file():
        with open(questions_file_name, 'r') as input_file:
            questions = json.loads(input_file.read())
    else:
        # Extract new questions
        questions = await extract_questions_from_text(file_path, text)
        
        # Limit the number of questions
        questions = questions[:MAX_QA_PAIRS]
        
        # Cache the questions
        with open(questions_file_name, 'w') as output_file:
            json.dump(questions, output_file, indent=2)
    
    results_filename = f"{file_path}.result.json"
    result = []
    
    # Try to load cached results if caching is enabled
    if not no_cache and Path(results_filename).is_file():
        with open(results_filename, 'r') as input_file:
            result = json.loads(input_file.read())
    else:
        # Generate answers for each question
        tasks = []
        for sub_file_path, sub_text, question in questions:
            task = generate_answer(question, sub_text)
            tasks.append(task)
        
        answers = await asyncio.gather(*tasks)
        
        # Combine questions and answers
        for (sub_file_path, sub_text, question), answer in zip(questions, answers):
            result.append({
                'question': question,
                'answer': answer
            })
        
        # Cache the results
        with open(results_filename, 'w') as output_file:
            json.dump(result, output_file, indent=2)
    
    # Update progress
    progress_counter['nb_files_done'] += 1
    if verbose:
        print(f"{progress_counter['nb_files_done']}/{progress_counter['nb_files']}: File '{file_path}' done!")
    
    return result

async def process_files(files, verbose=True, no_cache=False):
    """Process multiple files concurrently."""
    nb_files = len(files)
    progress_counter = {'nb_files': nb_files, 'nb_files_done': 0}
    
    if verbose:
        print(f"Starting question extraction on {nb_files} files.")
    
    tasks = []
    for file_path, text in files:
        task = process_file(file_path, text, progress_counter, verbose, no_cache)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    return flatten_nested_lists(results)

def extract_questions_from_directory(input_folder, verbose=True, no_cache=False):
    """Main function to extract questions from a directory of files."""
    if verbose:
        print(f"Loading files from '{input_folder}'.")
    
    files = load_markdown_files_from_directory(input_folder)
    
    if not files:
        print(f"No markdown files found in '{input_folder}'.")
        return []
    
    # Run the async process
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(process_files(files, verbose, no_cache))
    finally:
        loop.close()
    
    if verbose:
        print(f"Done, {len(results)} question/answer pairs have been generated!")
    
    return results

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='Extract questions from documents')
    parser.add_argument('--input', '-i', type=str, default='./data/docs',
                        help='Input directory containing documents (default: ./data/docs)')
    parser.add_argument('--output', '-o', type=str, default='./data/questions.json',
                        help='Output JSON file path (default: ./data/questions.json)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Run quietly with minimal output')
    parser.add_argument('--no-cache', action='store_true',
                        help='Skip cache and regenerate all questions and answers')
    return parser.parse_args()

# Main function
def main():
    args = parse_args()
    
    input_directory = Path(args.input)
    output_filepath = Path(args.output)
    verbose = not args.quiet
    no_cache = args.no_cache
    
    if verbose and no_cache:
        print("Cache disabled. Regenerating all questions and answers.")
    
    # Create output directory if it doesn't exist
    output_filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Pass no_cache to extract_questions_from_directory
    extracted_questions = extract_questions_from_directory(input_directory, verbose, no_cache)
    
    # Save the results
    with open(output_filepath, 'w') as output_file:
        json.dump(extracted_questions, output_file, indent=4)
        if verbose:
            print(f"Results have been saved to {output_filepath}.")

if __name__ == "__main__":
    main() 