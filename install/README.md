
Orbit uses a TOML file (`dependencies.toml`) to manage different dependency profiles. This approach provides better maintainability and flexibility.

## How to Use

### 1. List Available Profiles

```bash
./setup.sh --list-profiles
```

This shows all available dependency profiles defined in `dependencies.toml`:
- `minimal`: Core dependencies only (default)
- `huggingface`: Adds Hugging Face model support
- `commercial`: Adds commercial cloud providers (OpenAI, Anthropic, etc.)
- `all`: Includes everything
- `development`: Adds development and testing tools

### 2. Install Specific Profile

```bash
# Install minimal dependencies (default)
./setup.sh

# Install Hugging Face support
./setup.sh --profile huggingface

# Install commercial providers
./setup.sh --profile commercial

# Install everything
./setup.sh --profile all
```

### 3. Combine Multiple Profiles

```bash
# Install both Hugging Face and commercial providers
./setup.sh --profile huggingface --profile commercial
```

### 4. Download GGUF Model

```bash
# Install minimal + download GGUF model
./setup.sh --download-gguf

# Install everything + download GGUF model
./setup.sh --profile all --download-gguf
```

## Creating Custom Profiles

You can add custom profiles to `dependencies.toml`:

```toml
[profiles.my_custom]
description = "My custom profile for specific use case"
extends = "minimal"  # Can be a string or array: ["minimal", "commercial"]
dependencies = [
    "openai==1.76",
    "streamlit==1.40.0",
    # Add any specific packages you need
]
```

Then install it:
```bash
./setup.sh --profile my_custom
```

## Profile Inheritance

Profiles can extend other profiles:

```toml
[profiles.data_science]
description = "Data science tools"
extends = ["minimal", "huggingface"]
dependencies = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "jupyter>=1.0.0",
]
```

## Model Configuration

GGUF models are configured in the TOML file:

```toml
[models.gguf]
gemma_3_1b = {
    url = "https://huggingface.co/...",
    path = "server/gguf/gemma-3-1b-it-Q4_0.gguf",
    description = "Gemma 3 1B quantized model"
}
```