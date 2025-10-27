# 🚀 Q&A Pipeline Optimization Guide

This guide provides optimization strategies for processing large volumes of markdown files through the Q&A generation pipeline.

## 📋 Table of Contents
- [Quick Start: Recommended Settings](#quick-start-recommended-settings)
- [Command-Line Options for Speed](#command-line-options-for-speed)
- [Performance Benchmarks](#performance-benchmarks)
- [Ollama Server Optimizations](#ollama-server-optimizations)
- [System-Level Optimizations](#system-level-optimizations)
- [Processing Strategies for Large Datasets](#processing-strategies-for-large-datasets)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

## Quick Start: Recommended Settings

### ⚡ Fastest Configuration for Hundreds of Files

```bash
python ollama_firecrawl_question_extractor.py \
  --input ./csed-dir-out \
  --output ./csed-dir-qa.json \
  --concurrent 10 \
  --batch-size 20 \
  --delay 0 \
  --no-warmup \
  --timeout 120 \
  --max-qa 10
```

This configuration can process ~100 files in 8-12 minutes.

## Command-Line Options for Speed

### 1. **Concurrency** (`--concurrent`)
Controls how many files are processed simultaneously.

```bash
--concurrent 10  # Default: 5
```

- **Conservative**: 3-5 (stable, slower)
- **Balanced**: 8-10 (recommended)
- **Aggressive**: 15-20 (fast but may overwhelm Ollama)

### 2. **Batch Size** (`--batch-size`)
Process files in batches for better memory management.

```bash
--batch-size 20  # Default: 0 (all at once)
```

- **Small batches**: 10-15 (better progress tracking)
- **Medium batches**: 20-30 (recommended)
- **Large batches**: 40-50 (faster but less granular progress)

### 3. **Max Q&A Pairs** (`--max-qa`)
Limit questions per file - **biggest impact on speed!**

```bash
--max-qa 10  # Default: 300 (way too many!)
```

- **Minimal**: 5-10 (very fast, good for overviews)
- **Balanced**: 10-20 (recommended)
- **Comprehensive**: 30-50 (slower but thorough)

### 4. **Skip Warm-up** (`--no-warmup`)
Skip model initialization test.

```bash
--no-warmup  # Saves 2-5 seconds at startup
```

### 5. **Timeout** (`--timeout`)
Fail faster on stuck requests.

```bash
--timeout 120  # Default: 300 seconds
```

- **Quick**: 60-90 seconds (for simple content)
- **Balanced**: 120-180 seconds (recommended)
- **Patient**: 300+ seconds (for complex content)

### 6. **API Delay** (`--delay`)
Add delay between requests (only if needed).

```bash
--delay 0  # Default: 0 (no delay)
```

- Use `0` for local Ollama
- Use `0.5-1` for remote servers
- Use `2-5` if experiencing rate limits

## Performance Benchmarks

### Configuration Profiles

#### 🐢 **Conservative (Slow but Safe)**
```bash
python ollama_firecrawl_question_extractor.py \
  --input ./data \
  --output ./qa.json \
  --concurrent 3 \
  --delay 1 \
  --max-qa 50
```
- **100 files**: ~30-45 minutes
- **500 files**: ~2.5-4 hours
- **Use when**: Stability is critical, limited resources

#### ⚖️ **Balanced (Recommended)**
```bash
python ollama_firecrawl_question_extractor.py \
  --input ./data \
  --output ./qa.json \
  --concurrent 8 \
  --batch-size 20 \
  --max-qa 15 \
  --no-warmup
```
- **100 files**: ~10-15 minutes
- **500 files**: ~50-75 minutes
- **Use when**: Good balance of speed and reliability

#### 🚀 **Aggressive (Maximum Speed)**
```bash
python ollama_firecrawl_question_extractor.py \
  --input ./data \
  --output ./qa.json \
  --concurrent 15 \
  --batch-size 30 \
  --max-qa 5 \
  --no-warmup \
  --timeout 60
```
- **100 files**: ~5-8 minutes
- **500 files**: ~25-40 minutes
- **Use when**: Speed is critical, robust hardware

## Ollama Server Optimizations

### 1. Choose Faster Models

Edit `config.yaml`:

```yaml
ollama:
  # Fastest models (in order of speed)
  model: "llama3.2:1b"    # Fastest, decent quality
  # model: "phi3:mini"     # Very fast, good quality
  # model: "mistral:7b"    # Slower, better quality
  # model: "llama3.2:3b"   # Balanced speed/quality
```

### 2. Optimize Model Parameters

```yaml
ollama:
  base_url: "http://localhost:11434"
  model: "llama3.2:1b"
  
  # Reduce these for speed
  num_predict: 512        # Default: 2048 (max tokens)
  num_ctx: 8000          # Default: 32000 (context window)
  
  # Increase for better CPU utilization
  num_threads: 16        # Set to number of CPU cores
  
  # Keep model loaded
  keep_alive: "30m"      # Keep model in memory
  
  # Quality vs Speed tradeoffs
  temperature: 0.1       # Lower = more consistent
  top_k: 20             # Lower = faster
  repeat_penalty: 1.1    # Prevent repetition
```

### 3. Pre-load Model

Before processing, keep model warm:

```bash
# Pre-load model to avoid cold starts
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2:1b",
  "prompt": "Hello",
  "keep_alive": "30m"
}'
```

### 4. GPU Acceleration

Check if Ollama is using GPU:

```bash
# Check GPU usage
ollama ps

# Should show something like:
# NAME          ID          SIZE    PROCESSOR    UNTIL
# llama3.2:1b   abc123      2.0 GB  100% GPU     30m from now
```

## System-Level Optimizations

### 1. Use Local Ollama
- **Local**: 10-50ms latency per request
- **Remote**: 100-500ms+ latency per request
- Network latency adds up quickly with hundreds of files!

### 2. Hardware Recommendations

#### Minimum Requirements
- CPU: 4+ cores
- RAM: 8GB
- Storage: SSD preferred

#### Recommended Setup
- CPU: 8+ cores
- RAM: 16GB+
- GPU: Any CUDA-compatible GPU (even 4GB helps)
- Storage: NVMe SSD

### 3. Resource Monitoring

Monitor during processing:

```bash
# Terminal 1: Run extraction
python ollama_firecrawl_question_extractor.py ...

# Terminal 2: Monitor CPU/Memory
htop

# Terminal 3: Monitor GPU (if available)
nvidia-smi -l 1

# Terminal 4: Monitor Ollama
watch -n 1 'curl -s http://localhost:11434/api/ps'
```

## Processing Strategies for Large Datasets

### 1. Parallel Processing

Split files and run multiple instances:

```bash
# Terminal 1
python ollama_firecrawl_question_extractor.py \
  --input ./chunk1 --output ./qa1.json --concurrent 5 &

# Terminal 2  
python ollama_firecrawl_question_extractor.py \
  --input ./chunk2 --output ./qa2.json --concurrent 5 &

# Combine results later
jq -s 'add' qa1.json qa2.json > combined.json
```

### 2. Progressive Processing

Start with minimal extraction, enhance later:

```bash
# Pass 1: Quick extraction (5 Q&As)
python ollama_firecrawl_question_extractor.py \
  --input ./data --output ./qa-quick.json \
  --max-qa 5 --concurrent 15

# Pass 2: Enhancement for important files only
python ollama_firecrawl_question_extractor.py \
  --input ./important --output ./qa-detailed.json \
  --max-qa 30 --concurrent 5 --no-cache
```

### 3. Use Caching Effectively

The script caches results automatically:

```bash
# First run - generates cache files
python ollama_firecrawl_question_extractor.py --input ./data --output ./qa.json

# Subsequent runs - uses cache (much faster!)
# Only processes new/modified files

# Force regeneration if needed
python ollama_firecrawl_question_extractor.py --input ./data --output ./qa.json --no-cache
```

### 4. Batch Processing Strategy

For 1000+ files:

```bash
#!/bin/bash
# process_batches.sh

DIRS=($(find ./markdown -type d -maxdepth 1))
for dir in "${DIRS[@]}"; do
    echo "Processing $dir..."
    python ollama_firecrawl_question_extractor.py \
        --input "$dir" \
        --output "${dir##*/}-qa.json" \
        --concurrent 10 \
        --max-qa 10 \
        --batch-size 20
done
```

## Monitoring and Troubleshooting

### Real-time Progress Monitoring

```bash
# Watch Q&A count grow
watch -n 5 'echo "Q&A pairs: $(jq length ./qa.json 2>/dev/null || echo 0)"'

# Monitor file size
watch -n 5 'ls -lh ./qa.json'

# Tail the latest additions
watch -n 5 'jq ".[-3:]" ./qa.json'
```

### Using tmux/screen for Long Runs

```bash
# Start tmux session
tmux new -s ollama-extraction

# Run your command
python ollama_firecrawl_question_extractor.py ...

# Detach: Ctrl+B, then D
# Reattach later:
tmux attach -t ollama-extraction
```

### Common Issues and Solutions

#### Issue: Ollama Timeouts
```bash
# Solution: Increase timeout and reduce concurrency
--timeout 300 --concurrent 5
```

#### Issue: Out of Memory
```bash
# Solution: Reduce batch size and concurrency
--batch-size 10 --concurrent 3
```

#### Issue: Slow Processing
```bash
# Solution: Reduce max-qa significantly
--max-qa 5  # Instead of default 300
```

#### Issue: Connection Errors
```bash
# Solution: Add delay and reduce concurrency
--delay 1 --concurrent 3
```

## Performance Expectations

With optimized settings on a decent machine (8 cores, 16GB RAM):

| File Count | Conservative | Balanced | Aggressive |
|------------|-------------|----------|------------|
| 10 files   | 3-5 min     | 1-2 min  | 30-60 sec  |
| 100 files  | 30-45 min   | 10-15 min| 5-8 min    |
| 500 files  | 2.5-4 hrs   | 50-75 min| 25-40 min  |
| 1000 files | 5-8 hrs     | 1.5-2.5 hrs| 1-1.5 hrs |

## Quick Optimization Checklist

- [ ] Reduce `--max-qa` from default 300 to 10-20
- [ ] Increase `--concurrent` to 8-15
- [ ] Use `--batch-size 20-30` for large datasets
- [ ] Add `--no-warmup` flag
- [ ] Use faster model (llama3.2:1b or phi3:mini)
- [ ] Reduce `num_predict` and `num_ctx` in config
- [ ] Use local Ollama instance (not remote)
- [ ] Monitor resource usage with htop
- [ ] Use tmux/screen for long runs
- [ ] Keep output file on SSD for faster writes

## Final Tips

1. **Start Small**: Test with 10 files first to gauge performance
2. **Use Cache**: Don't use `--no-cache` unless necessary
3. **Monitor Progress**: Watch the JSON file grow in real-time
4. **Split Large Jobs**: Process in chunks rather than all at once
5. **Choose Quality vs Speed**: Adjust `--max-qa` based on your needs

Remember: The biggest speed improvement comes from reducing `--max-qa` from 300 to something reasonable like 10-20!