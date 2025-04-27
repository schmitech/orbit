import asyncio
import json
import os
import argparse
from docling.document_converter import DocumentConverter

async def process_url(url, output_path, converter):
    """
    Process a single URL and save its content as markdown.
    
    Args:
        url (str): URL to crawl (use url-extractor.py to get the urls)
        output_path (str): Path where to save the markdown file
        converter (DocumentConverter): Docling document converter instance
    """
    try:
        # Convert the document using docling
        result = converter.convert(url)
        
        # Check if document was successfully retrieved
        if result and result.document:
            # Save the markdown content to the output file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result.document.export_to_markdown())
            print(f"Saved {output_path}")
        else:
            print(f"Warning: No content retrieved for {url}")
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")

async def main(urls_file, output_dir):
    """
    Main function that processes web pages and saves their content as markdown files.
    
    Args:
        urls_file (str): Path to the JSON file containing URLs to process.
                         Expected format: [{"url": "https://example.com", "file_name": "example.md"}, ...]
        output_dir (str): Directory where the processed content will be saved.
    """
    print(f"Starting to process URLs from {urls_file}")  # Add initial feedback
    
    # Load URLs from JSON file
    with open(urls_file, 'r') as f:
        urls = json.load(f)
    
    print(f"Loaded {len(urls)} URLs to process")  # Show number of URLs
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize the docling converter
    converter = DocumentConverter()
    print("Initialized document converter")  # Confirm initialization
    
    # Create tasks for each URL
    tasks = []
    for i, item in enumerate(urls):
        print(f"Starting to process URL {i+1}/{len(urls)}: {item['url']}")  # Show progress
        filepath = os.path.join(output_dir, item['file_name'])
        task = asyncio.create_task(process_url(item['url'], filepath, converter))
        tasks.append(task)
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks)
    print("All URLs have been processed")  # Final confirmation

if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description='Document converter script that saves web pages as markdown files using Docling')
    parser.add_argument('urls_file', help='JSON file containing URLs to process')
    parser.add_argument('output_dir', help='Directory to store the processed files')
    args = parser.parse_args()
    
    # Run the main function with the provided arguments
    asyncio.run(main(args.urls_file, args.output_dir))