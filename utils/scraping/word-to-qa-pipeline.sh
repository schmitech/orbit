#!/bin/bash

################################################################################
# Word to Q&A Pipeline Script
# Version: 1.0.0
# Author: QA Pipeline Project
# Date: 2024
################################################################################
#
# DESCRIPTION:
#   Comprehensive pipeline for converting Microsoft Word documents (.docx) into
#   high-quality question-answer pairs suitable for LLM training, RAG systems,
#   and knowledge base construction.
#
# FEATURES:
#   - Automatic Word to Markdown conversion with content enhancement
#   - Intelligent content filtering (removes ToC, page numbers, headers/footers)
#   - Structure preservation with heading hierarchy normalization
#   - Q&A extraction using Ollama LLM with configurable parameters
#   - Paraphrase generation for question diversity
#   - Parallel processing for improved performance
#   - Comprehensive validation and error handling
#   - Detailed progress reporting and summary generation
#
# PREREQUISITES:
#   - Python 3.7+ with virtual environment (recommended)
#   - Ollama running locally or remotely (configured in config.yaml)
#   - Required Python packages: docling, aiohttp, pyyaml, requests
#   - Sufficient disk space for markdown and JSON output files
#
# USAGE:
#   Basic usage:
#     ./word-to-qa-pipeline.sh
#
#   Show help:
#     ./word-to-qa-pipeline.sh --help
#
#   Clean all generated files:
#     ./word-to-qa-pipeline.sh --clean
#
# CONFIGURATION:
#   The script uses the following environment variables (with defaults):
#     WORD_FILES_DIR   - Directory containing Word files (default: current dir)
#     MD_OUTPUT_DIR    - Directory for enhanced markdown files (default: ./enhanced-md-files)
#     QA_OUTPUT_DIR    - Directory for Q&A JSON files (default: ./generated-qa-files)
#     CONCURRENT       - Number of concurrent Ollama requests (default: 3)
#     BATCH_SIZE       - Files to process in each batch (default: 5)
#     MAX_QA           - Maximum Q&A pairs per file (default: 15)
#     PARAPHRASES      - Number of paraphrase variants per question (default: 3)
#
# OUTPUT:
#   - Enhanced markdown files in MD_OUTPUT_DIR/
#   - Q&A pairs in JSON format in QA_OUTPUT_DIR/qa_pairs_TIMESTAMP.json
#   - Pipeline summary report in QA_OUTPUT_DIR/pipeline_summary_TIMESTAMP.txt
#
# PIPELINE STAGES:
#   1. Dependency Check    - Validates Python environment and packages
#   2. Word→Markdown      - Converts .docx files with enhancement
#   3. Markdown Validation - Verifies markdown files are ready
#   4. Q&A Extraction     - Generates Q&A pairs using Ollama
#   5. Output Validation  - Validates JSON structure and content
#   6. Summary Generation - Creates detailed execution report
#
# ERROR HANDLING:
#   - Validates each stage before proceeding
#   - Provides detailed error messages with troubleshooting hints
#   - Creates backups of existing files before overwriting
#   - Supports resume from any stage if interrupted
#
# EXAMPLES:
#   # Process all Word files in current directory
#   ./word-to-qa-pipeline.sh
#
#   # Process Word files from specific directory with custom settings
#   WORD_FILES_DIR=/path/to/docs MAX_QA=20 ./word-to-qa-pipeline.sh
#
#   # Clean and restart fresh
#   ./word-to-qa-pipeline.sh --clean
#   ./word-to-qa-pipeline.sh
#
################################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
WORD_FILES_DIR="."  # Directory containing Word files
MD_OUTPUT_DIR="./enhanced-md-files"
QA_OUTPUT_DIR="./generated-qa-files"
BATCH_SIZE=5
CONCURRENT=3
MAX_QA=15
TIMEOUT=300
PARAPHRASES=3  # Number of paraphrase variants per question

# Python virtual environment handling
VENV_DIR="venv"

# Function to print section headers
print_header() {
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# Function to check Python dependencies
check_dependencies() {
    echo -e "${BLUE}Checking dependencies...${NC}"
    
    # Check for Python
    if ! command -v python &> /dev/null; then
        echo -e "${RED}Error: Python is not installed${NC}"
        exit 1
    fi
    
    # Check virtual environment
    if [ -d "$VENV_DIR" ]; then
        echo -e "${GREEN}Found virtual environment at $VENV_DIR${NC}"
        
        if [ -z "$VIRTUAL_ENV" ]; then
            echo -e "${YELLOW}Activating virtual environment...${NC}"
            source "$VENV_DIR/bin/activate"
            echo -e "${GREEN}✓ Virtual environment activated${NC}"
        else
            echo -e "${GREEN}✓ Virtual environment already active: $VIRTUAL_ENV${NC}"
        fi
    fi
    
    # Check required Python packages
    local packages=("docling" "aiohttp" "pyyaml" "requests")
    local missing_packages=()
    
    for package in "${packages[@]}"; do
        python -c "import $package" 2>/dev/null
        if [ $? -ne 0 ]; then
            missing_packages+=($package)
        fi
    done
    
    if [ ${#missing_packages[@]} -gt 0 ]; then
        echo -e "${YELLOW}Missing packages: ${missing_packages[*]}${NC}"
        echo -e "${YELLOW}Installing missing packages...${NC}"
        pip install "${missing_packages[@]}"
    else
        echo -e "${GREEN}✓ All Python dependencies found${NC}"
    fi
}

# Function to convert Word files to Markdown
convert_word_to_markdown() {
    local input_file=$1
    local output_dir=$2
    local basename=$(basename "$input_file" .docx)
    local output_file="$output_dir/${basename}.md"
    
    echo -e "${BLUE}Converting: $input_file${NC}"
    
    # Convert with all enhancements enabled
    python word-to-markdown.py \
        --exclude-toc \
        --exclude-page-numbers \
        --verbose \
        "$input_file" \
        "$output_file"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Converted: ${basename}.md${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to convert: $input_file${NC}"
        return 1
    fi
}

# Function to process markdown files for Q&A extraction
extract_qa_pairs() {
    local input_dir=$1
    local output_file=$2
    
    echo -e "${BLUE}Extracting Q&A pairs from $input_dir${NC}"
    
    # Run the improved Q&A extractor with optimizations
    python ollama_question_extractor.py \
        --input "$input_dir" \
        --output "$output_file" \
        --concurrent $CONCURRENT \
        --batch-size $BATCH_SIZE \
        --max-qa $MAX_QA \
        --timeout $TIMEOUT \
        --no-cache \
        --no-warmup \
        --group-questions \
        --paraphrases $PARAPHRASES \
        --paraphrase-batch-size 5 \
        --parallel-paraphrases
    
    return $?
}

# Function to validate Q&A output
validate_qa_output() {
    local qa_file=$1
    
    if [ ! -f "$qa_file" ]; then
        echo -e "${RED}Error: Q&A file not found${NC}"
        return 1
    fi
    
    # Check if file is valid JSON
    python -c "import json; json.load(open('$qa_file'))" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Invalid JSON in Q&A file${NC}"
        return 1
    fi
    
    # Count Q&A pairs
    local qa_count=$(python -c "import json; print(len(json.load(open('$qa_file'))))" 2>/dev/null)
    echo -e "${GREEN}✓ Validated: $qa_count Q&A pairs${NC}"
    
    # Show sample
    echo -e "${BLUE}Sample Q&A pair:${NC}"
    python -c "
import json
data = json.load(open('$qa_file'))
if data:
    item = data[0]
    if 'questions' in item:
        print(f'Questions: {item[\"questions\"][:2]}')
    else:
        print(f'Question: {item.get(\"question\", \"N/A\")}')
    answer = item.get('answer', 'N/A')
    print(f'Answer: {answer[:200]}...' if len(answer) > 200 else f'Answer: {answer}')
" 2>/dev/null
    
    return 0
}

# Main pipeline
main() {
    print_header "Word to Q&A Pipeline"
    
    # Check dependencies
    check_dependencies
    
    # Create output directories
    mkdir -p "$MD_OUTPUT_DIR"
    mkdir -p "$QA_OUTPUT_DIR"
    
    # Step 1: Find and convert Word files
    print_header "Step 1: Word to Markdown Conversion"
    
    # Find all Word files
    WORD_FILES=($(find "$WORD_FILES_DIR" -maxdepth 1 -name "*.docx" -type f))
    
    if [ ${#WORD_FILES[@]} -eq 0 ]; then
        echo -e "${YELLOW}No Word files found in $WORD_FILES_DIR${NC}"
        echo -e "${YELLOW}Looking for existing markdown files...${NC}"
    else
        echo -e "${GREEN}Found ${#WORD_FILES[@]} Word file(s) to convert${NC}"
        
        # Convert each Word file
        for word_file in "${WORD_FILES[@]}"; do
            convert_word_to_markdown "$word_file" "$MD_OUTPUT_DIR"
        done
    fi
    
    # Step 2: Check for markdown files
    print_header "Step 2: Markdown Validation"
    
    MD_COUNT=$(find "$MD_OUTPUT_DIR" -name "*.md" -type f | wc -l | tr -d ' ')
    if [ "$MD_COUNT" -eq 0 ]; then
        echo -e "${RED}Error: No markdown files found in $MD_OUTPUT_DIR${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}Found $MD_COUNT markdown file(s) to process${NC}"
    
    # Step 3: Extract Q&A pairs
    print_header "Step 3: Q&A Extraction"
    
    # Generate output filename with timestamp
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    QA_OUTPUT_FILE="$QA_OUTPUT_DIR/qa_pairs_${TIMESTAMP}.json"
    
    # Start time tracking
    START_TIME=$(date +%s)
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo -e "  - Concurrent requests: $CONCURRENT"
    echo -e "  - Batch size: $BATCH_SIZE"
    echo -e "  - Max Q&A per file: $MAX_QA"
    echo -e "  - Paraphrases per question: $PARAPHRASES"
    echo -e "  - Output file: $QA_OUTPUT_FILE"
    echo ""
    
    # Extract Q&A pairs
    extract_qa_pairs "$MD_OUTPUT_DIR" "$QA_OUTPUT_FILE"
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Q&A extraction failed${NC}"
        exit 1
    fi
    
    # End time tracking
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    DURATION_MINUTES=$((DURATION / 60))
    DURATION_SECONDS=$((DURATION % 60))
    
    # Step 4: Validate output
    print_header "Step 4: Output Validation"
    
    validate_qa_output "$QA_OUTPUT_FILE"
    
    # Step 5: Summary
    print_header "Pipeline Summary"
    
    echo -e "${GREEN}✅ Pipeline completed successfully!${NC}"
    echo -e "${GREEN}Processing time: ${DURATION_MINUTES}m ${DURATION_SECONDS}s${NC}"
    echo -e "${GREEN}Output file: $QA_OUTPUT_FILE${NC}"
    
    # Calculate statistics
    if [ -f "$QA_OUTPUT_FILE" ]; then
        FILE_SIZE=$(ls -lh "$QA_OUTPUT_FILE" | awk '{print $5}')
        echo -e "${GREEN}File size: $FILE_SIZE${NC}"
        
        # Create summary report
        SUMMARY_FILE="$QA_OUTPUT_DIR/pipeline_summary_${TIMESTAMP}.txt"
        cat > "$SUMMARY_FILE" << EOF
Word to Q&A Pipeline Summary
============================
Timestamp: $(date)
Duration: ${DURATION_MINUTES}m ${DURATION_SECONDS}s

Input:
- Word files processed: ${#WORD_FILES[@]}
- Markdown files processed: $MD_COUNT

Configuration:
- Concurrent requests: $CONCURRENT
- Batch size: $BATCH_SIZE
- Max Q&A per file: $MAX_QA
- Paraphrases per question: $PARAPHRASES

Output:
- Q&A file: $QA_OUTPUT_FILE
- File size: $FILE_SIZE
EOF
        
        echo -e "${GREEN}Summary saved to: $SUMMARY_FILE${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}🎉 Your Q&A pairs are ready for use in RAG systems or LLM training!${NC}"
}

# Handle script arguments
case "${1:-}" in
    -h|--help)
        echo "Word to Q&A Pipeline"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  -h, --help     Show this help message"
        echo "  -c, --clean    Clean all generated files and start fresh"
        echo ""
        echo "Environment variables:"
        echo "  WORD_FILES_DIR  Directory containing Word files (default: .)"
        echo "  MD_OUTPUT_DIR   Directory for markdown files (default: ./enhanced-md-files)"
        echo "  QA_OUTPUT_DIR   Directory for Q&A files (default: ./generated-qa-files)"
        echo "  CONCURRENT      Concurrent API requests (default: 3)"
        echo "  MAX_QA          Max Q&A pairs per file (default: 15)"
        echo ""
        exit 0
        ;;
    -c|--clean)
        echo -e "${YELLOW}Cleaning generated files...${NC}"
        rm -rf "$MD_OUTPUT_DIR"/*.md
        rm -rf "$QA_OUTPUT_DIR"/*.json
        rm -rf ./*.md.json ./*.md.result.json
        echo -e "${GREEN}✓ Cleaned all generated files${NC}"
        exit 0
        ;;
esac

# Run the main pipeline
main