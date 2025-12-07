#!/bin/bash

# Set the VITE_ADAPTERS environment variable (required for --enable-api-middleware)
export VITE_ADAPTERS='[
  { "name": "Simple Chat", "apiKey": "default-key", "apiUrl": "http://localhost:3000" },
  { "name": "Files Chat", "apiKey": "multimodal", "apiUrl": "http://localhost:3000" }
]'

# Run the chat app
orbitchat --api-url http://localhost:3000 --enable-api-middleware --enable-upload \
    --host 0.0.0.0 \
    --max-conversations 5 \
    --max-messages-per-conversation 50 \
    --max-total-messages 200 \
    --max-files-per-conversation 3 \
    --max-file-size-mb 10 \
    --max-total-files 20 \
    --max-message-length 500