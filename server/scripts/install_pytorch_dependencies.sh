#!/bin/bash
set -e

# Create logs directory
mkdir -p logs

echo "Installing minimal dependencies directly..."
pip install --upgrade pip

# Install exactly what we need without requirements file
echo "Installing base torch packages..."
pip install numpy==1.26.4 torch==2.2.2

echo "Installing transformers and related packages..."
pip install transformers==4.37.2 sentencepiece==0.2.0 "protobuf>=5.26.1,<6.0" safetensors==0.4.1

# Verify versions and MPS availability
echo "Verifying packages and device availability..."
python -c "import numpy; print(f'NumPy version: {numpy.__version__}')"
python -c "import torch; print(f'PyTorch version: {torch.__version__}')"
python -c "import transformers; print(f'Transformers version: {transformers.__version__}')"

# Check for MPS device
python -c "import torch; print(f'MPS available: {torch.backends.mps.is_available() if hasattr(torch.backends, \"mps\") else False}')"