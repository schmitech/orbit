#!/bin/bash

################################################################################
# Clean Q&A Extraction Script (No Cache Mode)
# Version: 2.0.0
# Author: QA Pipeline Project
# Date: 2024
################################################################################
#
# DESCRIPTION:
#   Runs the Ollama question extractor in clean mode (without cache) to generate
#   fresh Q&A pairs from markdown files. This script is optimized for production
#   runs where you want consistent, reproducible results without cached data.
#
# KEY FEATURES:
#   - Clean extraction mode (no cache) for reproducible results
#   - Automatic Word document conversion if detected
#   - Enhanced markdown preprocessing for better Q&A quality
#   - Virtual environment auto-detection and activation
#   - Comprehensive dependency checking
#   - Progress monitoring with time estimates
#   - Automatic backup of existing output files
#   - No source field in output (clean Q&A pairs only)
#
# PREREQUISITES:
#   - Python 3.7+ with optional virtual environment
#   - Ollama server running (configured in config.yaml)
#   - Required packages: aiohttp, pyyaml, requests
#   - Markdown files in INPUT_DIR or Word document to convert
#
# INPUT:
#   - Markdown files in ./guardians-md-files/ directory
#   - OR: guardians.docx file for automatic conversion
#
# OUTPUT:
#   - JSON file with Q&A pairs at ./generated-qa-files/guardians-qa-sample.json
#   - Each entry contains: {question: string, answer: string}
#   - No source fields included (clean output)
#
# CONFIGURATION (edit variables below):
#   INPUT_DIR       - Directory containing markdown files
#   OUTPUT_FILE     - Path to output JSON file  
#   WORD_FILE       - Optional Word document to convert
#   CONCURRENT      - Number of concurrent Ollama requests (default: 3)
#   BATCH_SIZE      - Files to process per batch (default: 10)
#   DELAY           - Delay between requests in seconds (default: 2)
#   TIMEOUT         - Request timeout in seconds (default: 300)
#   MAX_QA          - Maximum Q&A pairs per file (default: 10)
#
# USAGE:
#   ./run-extraction-clean.sh
#
# MONITORING:
#   While running, you can monitor progress in another terminal:
#   watch -n 2 'wc -l ./generated-qa-files/guardians-qa-sample.json'
#
################################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Python virtual environment handling
VENV_DIR="venv"

# Check if virtual environment exists and activate it
if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}Found virtual environment at $VENV_DIR${NC}"
    
    # Check if already in a virtual environment
    if [ -z "$VIRTUAL_ENV" ]; then
        echo -e "${YELLOW}Activating virtual environment...${NC}"
        source "$VENV_DIR/bin/activate"
        echo -e "${GREEN}✓ Virtual environment activated${NC}"
    else
        echo -e "${GREEN}✓ Virtual environment already active: $VIRTUAL_ENV${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No virtual environment found at $VENV_DIR${NC}"
    echo -e "${YELLOW}Running with system Python installation${NC}"
fi

# Display Python information
echo -e "${BLUE}Python Info:${NC}"
echo -e "  Python path: $(which python)"
echo -e "  Python version: $(python --version 2>&1)"
echo ""

# Configuration
INPUT_DIR="./guardians-md-files"
OUTPUT_FILE="./generated-qa-files/guardians-qa-sample.json"
WORD_FILE="./guardians.docx"  # Input Word file if exists
CONCURRENT=3  # Reduced from 10 to prevent timeouts
BATCH_SIZE=10  # Reduced from 20 for better stability
DELAY=2
TIMEOUT=300  # Increased from 120 to 300 seconds
MAX_QA=10

# Print configuration
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Q&A Extraction - CLEAN MODE (No Cache)${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Input Directory:${NC} $INPUT_DIR"
if [ -f "$WORD_FILE" ]; then
    echo -e "${GREEN}Word Document:${NC} $WORD_FILE (will be converted)"
fi
echo -e "${GREEN}Output File:${NC} $OUTPUT_FILE"
echo -e "${GREEN}Concurrent Requests:${NC} $CONCURRENT"
echo -e "${GREEN}Batch Size:${NC} $BATCH_SIZE"
echo -e "${GREEN}Max Q&A per file:${NC} $MAX_QA"
echo -e "${GREEN}Timeout:${NC} ${TIMEOUT}s"
echo -e "${RED}Cache:${NC} DISABLED (clean regeneration, no source fields)"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check for required Python packages
echo -e "${BLUE}Checking Python dependencies...${NC}"
python -c "import aiohttp" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: aiohttp package not found${NC}"
    echo -e "${YELLOW}Please install with: pip install aiohttp${NC}"
    exit 1
fi

python -c "import yaml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: pyyaml package not found${NC}"
    echo -e "${YELLOW}Please install with: pip install pyyaml${NC}"
    exit 1
fi

python -c "import requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: requests package not found${NC}"
    echo -e "${YELLOW}Please install with: pip install requests${NC}"
    exit 1
fi
echo -e "${GREEN}✓ All Python dependencies found${NC}"
echo ""

# Check if we need to convert Word to Markdown first
if [ -f "$WORD_FILE" ]; then
    echo -e "${BLUE}Found Word document: $WORD_FILE${NC}"
    echo -e "${YELLOW}Converting Word to enhanced Markdown format...${NC}"
    
    # Create output directory if it doesn't exist
    mkdir -p "$INPUT_DIR"
    
    # Convert with Q&A enhancement
    OUTPUT_MD="$INPUT_DIR/$(basename "$WORD_FILE" .docx).md"
    python word-to-markdown.py --exclude-toc --exclude-page-numbers -v "$WORD_FILE" "$OUTPUT_MD"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Word document converted successfully${NC}"
    else
        echo -e "${RED}Error: Word document conversion failed${NC}"
        exit 1
    fi
fi

# Check if input directory exists
if [ ! -d "$INPUT_DIR" ]; then
    echo -e "${RED}Error: Input directory '$INPUT_DIR' does not exist!${NC}"
    echo -e "${YELLOW}Please ensure you have markdown files ready.${NC}"
    exit 1
fi

# Count markdown files
MD_COUNT=$(find "$INPUT_DIR" -name "*.md" -type f | wc -l | tr -d ' ')
if [ "$MD_COUNT" -eq 0 ]; then
    echo -e "${RED}Error: No markdown files found in '$INPUT_DIR'${NC}"
    exit 1
fi

echo -e "${GREEN}Found $MD_COUNT markdown files to process${NC}"
echo ""

# Create backup of existing output if it exists
if [ -f "$OUTPUT_FILE" ]; then
    BACKUP_FILE="${OUTPUT_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}Backing up existing output to: $BACKUP_FILE${NC}"
    cp "$OUTPUT_FILE" "$BACKUP_FILE"
    echo ""
fi

# Show warning about clean mode
echo -e "${YELLOW}⚠️  CLEAN MODE ENABLED${NC}"
echo -e "${YELLOW}This will regenerate ALL Q&A pairs without using cache${NC}"
echo -e "${YELLOW}Result will have NO source fields - only question/answer pairs${NC}"
echo -e "${YELLOW}Processing time will be longer but results will be clean${NC}"
echo ""

# Estimate processing time (longer without cache)
ESTIMATED_TIME=$((MD_COUNT * 8 / CONCURRENT)) # 8 seconds per file without cache
ESTIMATED_MINUTES=$((ESTIMATED_TIME / 60))
echo -e "${BLUE}Estimated processing time: ~$ESTIMATED_MINUTES minutes${NC}"
echo -e "${YELLOW}Press Ctrl+C to cancel, starting in 5 seconds...${NC}"
sleep 5
echo ""

# Start time tracking
START_TIME=$(date +%s)

# Run the extraction with --no-cache
echo -e "${GREEN}Starting CLEAN extraction (no cache)...${NC}"
echo -e "${YELLOW}💡 Tip: Monitor progress in another terminal with:${NC}"
echo -e "${YELLOW}   watch -n 2 'wc -l $OUTPUT_FILE && tail -5 $OUTPUT_FILE'${NC}"
echo -e "${BLUE}========================================${NC}"

python ollama_question_extractor.py \
  --input "$INPUT_DIR" \
  --output "$OUTPUT_FILE" \
  --concurrent $CONCURRENT \
  --batch-size $BATCH_SIZE \
  --delay $DELAY \
  --no-warmup \
  --no-cache \
  --timeout $TIMEOUT \
  --max-qa $MAX_QA

# Check exit status
EXIT_STATUS=$?

# End time tracking
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MINUTES=$((DURATION / 60))
DURATION_SECONDS=$((DURATION % 60))

echo ""
echo -e "${BLUE}========================================${NC}"

if [ $EXIT_STATUS -eq 0 ]; then
    # Count Q&A pairs in output
    if [ -f "$OUTPUT_FILE" ]; then
        QA_COUNT=$(jq length "$OUTPUT_FILE" 2>/dev/null || echo "0")
        FILE_SIZE=$(ls -lh "$OUTPUT_FILE" | awk '{print $5}')
        
        echo -e "${GREEN}✅ CLEAN extraction completed successfully!${NC}"
        echo -e "${GREEN}Total Q&A pairs generated: $QA_COUNT${NC}"
        echo -e "${GREEN}Output file size: $FILE_SIZE${NC}"
        echo -e "${GREEN}Processing time: ${DURATION_MINUTES}m ${DURATION_SECONDS}s${NC}"
        
        # Calculate average Q&A per file
        if [ "$MD_COUNT" -gt 0 ]; then
            AVG_QA=$((QA_COUNT / MD_COUNT))
            echo -e "${GREEN}Average Q&A pairs per file: ~$AVG_QA${NC}"
        fi
        
        # Verify no source fields
        HAS_SOURCE=$(jq 'map(has("source")) | any' "$OUTPUT_FILE" 2>/dev/null || echo "false")
        if [ "$HAS_SOURCE" = "false" ]; then
            echo -e "${GREEN}✅ Verified: No source fields in output${NC}"
        else
            echo -e "${YELLOW}⚠️  Warning: Some entries may still have source fields${NC}"
        fi
        
        # Show sample of clean Q&A
        echo ""
        echo -e "${BLUE}Sample of clean Q&A pairs:${NC}"
        echo -e "${BLUE}---------------------------${NC}"
        jq '.[0:2] | .[] | {question: .question[0:80], answer: .answer[0:80]}' "$OUTPUT_FILE" 2>/dev/null || echo "Could not display sample"
    else
        echo -e "${YELLOW}⚠️ Output file not found, but process completed${NC}"
    fi
else
    echo -e "${RED}❌ Clean extraction failed with exit code: $EXIT_STATUS${NC}"
    echo -e "${YELLOW}Check the error messages above for details${NC}"
fi

echo -e "${BLUE}========================================${NC}"

# Final message
if [ $EXIT_STATUS -eq 0 ] && [ -f "$OUTPUT_FILE" ]; then
    echo ""
    echo -e "${GREEN}🧹 Clean extraction complete!${NC}"
    echo -e "${GREEN}Your clean Q&A pairs (no source fields) are ready in: $OUTPUT_FILE${NC}"
fi