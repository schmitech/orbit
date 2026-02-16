#!/usr/bin/env python3
"""
Word to Markdown Converter

A command-line tool for converting Microsoft Word documents (.docx) to Markdown format
using the docling library. This tool provides flexible input/output options and
comprehensive error handling.

Features:
- Convert single Word documents to Markdown
- Support for custom input and output file paths
- Automatic output file naming based on input file
- Comprehensive error handling and validation
- Progress indicators and user feedback
- Filter out table of contents and page numbers
- Verbose output with detailed conversion statistics

Requirements:
- docling library (install with: pip install docling)
- Python 3.6+

Usage Examples:
    # Convert a specific file with custom output name
    python word-to-markdown.py input.docx output.md
    
    # Convert a file with automatic output naming
    python word-to-markdown.py document.docx
    
    # Convert with verbose output
    python word-to-markdown.py -v input.docx output.md
    
    # Exclude table of contents from output
    python word-to-markdown.py --exclude-toc document.docx
    
    # Exclude page numbers from output
    python word-to-markdown.py --exclude-page-numbers document.docx
    
    # Exclude both ToC and page numbers
    python word-to-markdown.py --exclude-toc --exclude-page-numbers document.docx
    
    # Combine filtering with verbose output
    python word-to-markdown.py --exclude-toc --exclude-page-numbers -v document.docx clean.md
    
    # Show help
    python word-to-markdown.py -h

Author: QA Pipeline Project
Version: 2.0
"""

import os
import sys
import argparse
import re
from pathlib import Path
from docling.document_converter import DocumentConverter


def validate_input_file(file_path):
    """
    Validate that the input file exists and has a supported extension.
    
    Args:
        file_path (str): Path to the input file
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not os.path.exists(file_path):
        print(f"❌ Error: Input file not found at '{file_path}'")
        return False
    
    # Check file extension
    supported_extensions = ['.docx', '.doc']
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext not in supported_extensions:
        print(f"❌ Error: Unsupported file format '{file_ext}'")
        print(f"Supported formats: {', '.join(supported_extensions)}")
        return False
    
    return True


def generate_output_filename(input_path, custom_output=None):
    """
    Generate output filename based on input file or custom name.
    
    Args:
        input_path (str): Path to the input file
        custom_output (str, optional): Custom output filename
        
    Returns:
        str: Generated output filename
    """
    if custom_output:
        return custom_output
    
    # Generate output filename based on input file
    input_path = Path(input_path)
    return f"{input_path.stem}.md"


def is_toc_entry(text):
    """
    Check if the given text appears to be a table of contents entry.
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if text appears to be a ToC entry, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    text = text.strip()
    
    # Check for ToC patterns (dots followed by page numbers)
    if re.search(r'\.{2,}\s*\d+$', text):
        return True

    # Check for ToC patterns (text, tab, number)
    if re.search(r'^[A-Z\s]+\t\d+$', text):
        return True
    
    # Check for common ToC indicators
    toc_indicators = [
        'table of contents',
        'contents',
        'index',
        'chapter',
        'section',
        'part'
    ]
    
    text_lower = text.lower()
    for indicator in toc_indicators:
        if indicator in text_lower and len(text) < 100:  # Short lines with ToC indicators
            return True
    
    # Check for numbered lists that might be ToC (1. Title ... 5)
    if re.match(r'^\d+\.\s+.*\. {2,}\s*\d+$', text):
        return True
        
    # Check for lines that are mostly dots (common in ToC)
    if re.match(r'^\.{3,}$', text):
        return True
    
    return False


def is_page_number(text):
    """
    Check if the given text appears to be a page number.
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if text appears to be a page number, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    text = text.strip()
    
    # Check for standalone numbers (page numbers)
    if re.match(r'^\d+$', text):
        return True
    
    return False


def filter_content(markdown_content, exclude_toc=False, exclude_page_numbers=False, enhance_for_qa=True):
    """
    Filter out table of contents and/or page numbers from markdown content.
    Optionally enhance content for better Q&A extraction.
    
    Args:
        markdown_content (str): Original markdown content
        exclude_toc (bool): Whether to exclude ToC entries
        exclude_page_numbers (bool): Whether to exclude page numbers
        enhance_for_qa (bool): Whether to enhance content for Q&A extraction
        
    Returns:
        str: Filtered and enhanced markdown content
    """
    lines = markdown_content.split('\n')
    filtered_lines = []
    
    # Track headers and footers to remove
    header_footer_patterns = [
        r'^Page \d+ of \d+$',
        r'^\d+\s*\|\s*Page$',
        r'^©.*20\d{2}',  # Copyright lines
        r'^All rights reserved',
        r'^Confidential',
    ]
    
    in_toc = False
    
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        
        # Detect table of contents sections
        if 'table of contents' in stripped_line.lower() or 'contents' == stripped_line.lower():
            in_toc = True
            if exclude_toc:
                continue
        
        # End of ToC detection (usually when we hit a main heading)
        if in_toc and re.match(r'^#+\s+[A-Z]', line) and not is_toc_entry(stripped_line):
            in_toc = False
        
        # Skip ToC content
        if in_toc and exclude_toc:
            continue
        
        # Skip empty lines but preserve them in the output
        if not stripped_line:
            filtered_lines.append(line)
            continue
        
        # Exclude headers/footers
        if enhance_for_qa:
            skip_line = False
            for pattern in header_footer_patterns:
                if re.match(pattern, stripped_line, re.IGNORECASE):
                    skip_line = True
                    break
            if skip_line:
                continue
        
        # Exclude ToC entries if requested
        if exclude_toc and is_toc_entry(stripped_line):
            continue
        
        # Exclude standalone page numbers if requested
        if exclude_page_numbers and is_page_number(stripped_line):
            continue
        
        # Exclude trailing page numbers if requested
        if exclude_page_numbers and re.search(r'\s+\d+\s*$', line) and len(stripped_line) < 10:
            line = re.sub(r'\s+\d+\s*$', '', line)
            if line.strip():
                filtered_lines.append(line)
            continue
            
        filtered_lines.append(line)
    
    # Post-process for Q&A enhancement
    if enhance_for_qa:
        content = '\n'.join(filtered_lines)
        content = enhance_content_for_qa(content)
        return content
    
    return '\n'.join(filtered_lines)


def enhance_content_for_qa(content):
    """
    Enhance markdown content for better Q&A extraction.
    
    Args:
        content (str): Markdown content to enhance
        
    Returns:
        str: Enhanced markdown content
    """
    # Clean up excessive whitespace
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    # Fix broken sentences across lines (common in PDFs)
    content = re.sub(r'([a-z,])\n([a-z])', r'\1 \2', content)
    
    # Ensure proper heading hierarchy
    lines = content.split('\n')
    enhanced_lines = []
    prev_heading_level = 0
    
    for line in lines:
        # Fix heading hierarchy
        if line.startswith('#'):
            heading_match = re.match(r'^(#+)\s+(.+)$', line)
            if heading_match:
                hashes, heading_text = heading_match.groups()
                current_level = len(hashes)
                
                # Ensure heading hierarchy doesn't jump levels
                if current_level > prev_heading_level + 1 and prev_heading_level > 0:
                    # Adjust the heading level
                    new_level = prev_heading_level + 1
                    line = '#' * new_level + ' ' + heading_text
                    current_level = new_level
                
                prev_heading_level = current_level
        
        enhanced_lines.append(line)
    
    content = '\n'.join(enhanced_lines)
    
    # Add section markers for better context
    content = add_section_markers(content)
    
    # Clean up bullet points and lists
    content = clean_lists(content)
    
    return content

def add_section_markers(content):
    """
    Add section markers to help LLM understand document structure.
    
    Args:
        content (str): Markdown content
        
    Returns:
        str: Content with section markers
    """
    lines = content.split('\n')
    enhanced_lines = []
    current_section = None
    
    for line in lines:
        if line.startswith('# '):
            current_section = line[2:].strip()
            enhanced_lines.append(line)
            enhanced_lines.append(f'<!-- SECTION: {current_section} -->')
        elif line.startswith('## '):
            subsection = line[3:].strip()
            enhanced_lines.append(line)
            if current_section:
                enhanced_lines.append(f'<!-- SUBSECTION of {current_section}: {subsection} -->')
        else:
            enhanced_lines.append(line)
    
    return '\n'.join(enhanced_lines)

def clean_lists(content):
    """
    Clean up bullet points and numbered lists for consistency.
    
    Args:
        content (str): Markdown content
        
    Returns:
        str: Content with cleaned lists
    """
    # Standardize bullet points
    content = re.sub(r'^[•·▪▫◦‣⁃]\s+', '- ', content, flags=re.MULTILINE)
    
    # Fix numbered lists
    lines = content.split('\n')
    cleaned_lines = []
    in_numbered_list = False
    list_counter = 0
    
    for line in lines:
        # Detect numbered list items
        numbered_match = re.match(r'^\s*\d+[.)\s]+(.+)$', line)
        if numbered_match:
            if not in_numbered_list:
                in_numbered_list = True
                list_counter = 1
            else:
                list_counter += 1
            cleaned_lines.append(f'{list_counter}. {numbered_match.group(1)}')
        else:
            if in_numbered_list and line.strip():
                # End of numbered list
                in_numbered_list = False
                list_counter = 0
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def convert_word_to_markdown(input_file, output_file, verbose=False, exclude_toc=False, exclude_page_numbers=False, enhance_for_qa=True):
    """
    Convert a Word document to Markdown format.
    
    Args:
        input_file (str): Path to the input Word document
        output_file (str): Path to the output Markdown file
        verbose (bool): Enable verbose output
        exclude_toc (bool): Exclude table of contents from output
        exclude_page_numbers (bool): Exclude page numbers from output
        enhance_for_qa (bool): Enhance output for Q&A extraction
        
    Returns:
        bool: True if conversion successful, False otherwise
    """
    if verbose:
        print(f"📁 Input file: {input_file}")
        print(f"📄 Output file: {output_file}")
        print(f"📊 File size: {os.path.getsize(input_file)} bytes")
    
    print(f"🔄 Converting '{input_file}' to '{output_file}'...")
    
    try:
        # Create a DocumentConverter instance
        converter = DocumentConverter()
        
        # Perform the conversion using docling's DocumentConverter
        result = converter.convert(input_file)
        
        # Get the markdown content from the result
        markdown_content = result.document.export_to_markdown()
        
        # Apply filtering and enhancement
        if exclude_toc or exclude_page_numbers or enhance_for_qa:
            if verbose:
                original_size = len(markdown_content)
                print("🔍 Processing content...")
                print(f"   - Exclude ToC: {exclude_toc}")
                print(f"   - Exclude page numbers: {exclude_page_numbers}")
                print(f"   - Enhance for Q&A: {enhance_for_qa}")
            
            markdown_content = filter_content(
                markdown_content, 
                exclude_toc=exclude_toc, 
                exclude_page_numbers=exclude_page_numbers,
                enhance_for_qa=enhance_for_qa
            )
            
            if verbose:
                filtered_size = len(markdown_content)
                print(f"📊 Content processed: {original_size} → {filtered_size} characters")
        
        # Write the markdown content to the output file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # Verify the output file was created
        if os.path.exists(output_file):
            output_size = os.path.getsize(output_file)
            print("✅ Conversion successful!")
            print(f"📄 Output file: '{output_file}'")
            if verbose:
                print(f"📊 Output size: {output_size} bytes")
            return True
        else:
            print("❌ Error: Output file was not created")
            return False
            
    except FileNotFoundError as e:
        print(f"❌ File not found error: {e}")
        return False
    except PermissionError as e:
        print(f"❌ Permission error: {e}")
        print("Please check file permissions and ensure you have write access to the output directory.")
        return False
    except Exception as e:
        print(f"❌ An error occurred during conversion: {e}")
        if verbose:
            import traceback
            print("Full error details:")
            traceback.print_exc()
        return False


def main():
    """
    Main function to handle command-line arguments and orchestrate the conversion.
    """
    parser = argparse.ArgumentParser(
        description="Convert Microsoft Word documents to Markdown format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s document.docx                    # Convert with auto-generated output name
  %(prog)s input.docx output.md            # Convert with custom output name
  %(prog)s -v document.docx                # Verbose output
  %(prog)s --exclude-toc document.docx     # Exclude table of contents
  %(prog)s --exclude-page-numbers doc.docx # Exclude page numbers
  %(prog)s --exclude-toc --exclude-page-numbers doc.docx # Exclude both
  %(prog)s --help                          # Show this help message
        """
    )
    
    parser.add_argument(
        'input_file',
        help='Path to the input Word document (.docx or .doc)'
    )
    
    parser.add_argument(
        'output_file',
        nargs='?',
        help='Path to the output Markdown file (optional, auto-generated if not provided)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output with additional information'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Word to Markdown Converter v2.0'
    )
    
    parser.add_argument(
        '--exclude-toc',
        action='store_true',
        help='Exclude table of contents from the output'
    )
    
    parser.add_argument(
        '--exclude-page-numbers',
        action='store_true',
        help='Exclude page numbers from the output'
    )
    
    parser.add_argument(
        '--no-enhance-qa',
        action='store_true',
        help='Disable Q&A enhancement features (enabled by default)'
    )
    
    # Parse command line arguments
    args = parser.parse_args()
    
    # Validate input file
    if not validate_input_file(args.input_file):
        sys.exit(1)
    
    # Generate output filename
    output_file = generate_output_filename(args.input_file, args.output_file)
    
    # Check if output file already exists
    if os.path.exists(output_file):
        response = input(f"⚠️  Output file '{output_file}' already exists. Overwrite? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("❌ Conversion cancelled.")
            sys.exit(0)
    
    # Perform the conversion
    success = convert_word_to_markdown(
        args.input_file, 
        output_file, 
        args.verbose, 
        args.exclude_toc, 
        args.exclude_page_numbers,
        enhance_for_qa=not args.no_enhance_qa
    )
    
    if success:
        print("🎉 Conversion completed successfully!")
        sys.exit(0)
    else:
        print("💥 Conversion failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()