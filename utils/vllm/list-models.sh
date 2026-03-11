#!/bin/bash

# List available models in vLLM server
curl http://localhost:5000/v1/models | jq
