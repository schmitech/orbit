# LlamaCpp Embedding Service

This embedding service allows you to generate embeddings using local GGUF models via the llama-cpp-python library.

## Requirements

- A GGUF model file that supports embeddings (e.g., LLaMA, Mistral, Vicuna, etc.)
- llama-cpp-python 0.3.8 or higher (included in requirements.txt)

## Configuration

To use this embedding service, set up your configuration file with the following settings:

```yaml
embedding:
  provider: "llama_cpp"

embeddings:
  llama_cpp:
    # Model configuration
    model_path: "/path/to/your/embedding-model.gguf"  # Path to the GGUF model file
    model: "model-name"  # Optional: Model name for logging
    
    # Model parameters
    n_ctx: 4096  # Context window size
    n_threads: 4  # Number of CPU threads to use
    n_gpu_layers: -1  # Number of layers to offload to GPU (-1 for all)
    main_gpu: 0  # Which GPU to use (for multi-GPU systems)
    tensor_split: null  # Optional: GPU memory split for multi-GPU setups
    
    # Processing parameters
    batch_size: 8  # Number of texts to process in parallel
    dimensions: 4096  # Expected embedding dimensions (optional)
    embed_type: "llama_embedding"  # Embedding generation method
```

## Finding Suitable Models

You can use most GGUF language models for embeddings, but some models are specifically trained for embeddings and will provide better results. Here are some options:

1. **E5 Models**: These are specifically trained for embeddings and provide good results.
   - Example: [BAAI/gte-large-en-v1.5-gguf](https://huggingface.co/LLukas22/gte-large-en-v1.5-gguf)

2. **BGE Models**: These models are also designed for embeddings.
   - Example: [bge-small-en-v1.5-gguf](https://huggingface.co/LLukas22/bge-small-en-v1.5-gguf)

3. **Language Models**: General language models like LLaMA, Mistral, etc. can also generate embeddings, but they may not be as effective for retrieval tasks.

## GGUF Quantization Formats

GGUF models come in different quantization formats, indicated by suffixes in their filenames. These affect model size, memory usage, and performance:

1. `Q4_0` (4-bit quantization):
   - Most compressed format
   - Uses 4 bits per weight
   - Good balance of size and performance
   - Suitable for most consumer hardware

2. `Q5_K_M` (5-bit quantization with K-means clustering):
   - 5 bits per weight
   - Uses K-means clustering for better precision
   - "M" stands for "mixed" precision
   - Better quality than Q4_0 but larger file size

3. `Q6_K` (6-bit quantization with K-means):
   - 6 bits per weight
   - Higher precision than Q5_K_M
   - Better quality but larger file size

4. `Q8_0` (8-bit quantization):
   - 8 bits per weight
   - Highest precision among common quantizations
   - Largest file size
   - Best quality but requires more memory

Choose your quantization based on your needs:
- For maximum accuracy: Use Q8_0
- For a good balance: Use Q5_K_M
- For maximum compression: Use Q4_0
- If unsure: Start with Q4_0 and upgrade if needed

## Memory Requirements

Memory usage depends on the model size and quantization format. Here are approximate requirements:

- **Q4_0 models**: ~0.5x model size in RAM/VRAM
  - Example: 7B model ≈ 3.5GB
- **Q5_K_M models**: ~0.6x model size in RAM/VRAM
  - Example: 7B model ≈ 4.2GB
- **Q6_K models**: ~0.7x model size in RAM/VRAM
  - Example: 7B model ≈ 4.9GB
- **Q8_0 models**: ~1x model size in RAM/VRAM
  - Example: 7B model ≈ 7GB

Add 20-30% overhead for processing and temporary buffers. For GPU usage, ensure you have enough VRAM for the model plus overhead.

## Performance Considerations

- GPU acceleration is highly recommended, especially for larger models.
- Set `n_gpu_layers` to -1 to offload all layers to GPU for best performance.
- Adjust `n_threads` based on your CPU's core count.
- The `batch_size` parameter can be adjusted based on your memory constraints.
- For multi-GPU systems, use `tensor_split` to distribute the model across GPUs.

## Embedding Types

The `embed_type` parameter controls how embeddings are generated:

- `llama_embedding`: Uses the model's built-in embedding function (recommended)
- `last_hidden_state`: Uses the last hidden state of the model (experimental)

## Environment Variables

You can also use environment variables in the configuration:

```yaml
embeddings:
  llama_cpp:
    model_path: "${LLAMA_CPP_MODEL_PATH}"
```

Then set the `LLAMA_CPP_MODEL_PATH` environment variable to your model path.

## Troubleshooting

### Model Loading Issues

If you see errors when loading models:

1. Check if the model path is correct.
2. Make sure the model file is a valid GGUF format.
3. Check if you have enough RAM/VRAM to load the model.
4. Verify that llama-cpp-python is installed correctly: `pip install llama-cpp-python==0.3.8`
5. For GPU support, ensure you have the correct CUDA version installed.

### Embedding Quality

If embedding quality is poor:

1. Try using a purpose-built embedding model instead of a general LLM.
2. Ensure your inputs are properly formatted.
3. Consider using shorter context lengths for better performance.
4. Try different quantization formats (Q5_K_M or Q8_0 for better quality).
5. Check if the model supports the selected `embed_type`.

### Performance Issues

If you experience slow performance:

1. Enable GPU acceleration by setting `n_gpu_layers: -1`
2. Increase `n_threads` to match your CPU core count
3. Adjust `batch_size` based on available memory
4. Consider using a more compressed quantization format (Q4_0)
5. For multi-GPU systems, configure `tensor_split` appropriately 