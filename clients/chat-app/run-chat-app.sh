#!/bin/bash

# Set the VITE_ADAPTERS environment variable (required for --enable-api-middleware)
export VITE_ADAPTERS='[
  { "name": "Simple Chat", "apiKey": "YOUR_API_KEY", "apiUrl": "http://localhost:3000" },
  { "name": "Chat With Files", "apiKey": "YOUR_API_KEY", "apiUrl": "http://localhost:3000" }
]'

# Run the chat app
orbitchat --api-url http://localhost:3000 --enable-api-middleware --enable-audio --enable-upload