# Changelog

## [1.1.1] - 2025-05-30

### Server Architecture & Refactoring
- Further reduce size of inference server
- Move logging-related code from inference server into logging_configuration.py
- Extract middleware initialization code into middleware_configurator.py
- Extract service factory function into service_factory module
- Add routes_configurator.py module
- Extract datasource initialization into datasource_factory.py
- Consolidate code between inference server and main modules
- Move HTTP session tracking function to HTTP utils

### Testing & Quality Assurance
- Fix issues with unit tests
- Improve test coverage
- Add TOML project under tests
- Fix issues with test_prompt_guardrails.py
- Remove warnings from unit tests
- Fix run_tests.py for proper test execution
- Remove test_retriever_types.py for rework

### SQL Retrievers
- Update SQL adapter architecture for better inheritance
- Add basic Postgres and MySQL implementations
- Further updates to SQL retriever design pattern

### Chatbot Widget
- Break chatbot widget into smaller components
- Remove simple GUI example
- Remove misplaced CharWidget.tsx file under widget directory

### Documentation
- Update README file
- Add SQL retriever technical details under docs
- Add more diagrams
- Improve instructions on README.md
- Add excalidraw diagram sources
- Improve script and add better usage documentation
- Update sql-retriever-architecture.md

### Reranking
- Re-organize rerankers, leaving ollama only while implementing the rest
- Add unit tests
- Update config file

### Other Changes
- Move HF GGUF download script to ./utils/scripts
- Udpate release tarball creation script
- Fixed minor config_manager.py warning

## [1.1.0] - 2025-05-26

### Config

- Updated default settings in config example. Now uses llama_cpp by default instead of Ollama.
- Disabled redis cache
- Update default model name for llama_cpp inference

### Core Services
- Introduced conversation history only for inference service (RAG mode not yet supported).
- Migrated admin endpoints from inference_server.py into its own route module as part to promote maintainability.
- Fixed Redis cache service, added redis and mongdb services unit tests.
- Fixed issues with config files. Disable loading RAG adapters if inference_only is true.
- Fixed language and ollama unit tests. Fixed redis config issues.

### Documentation & Configuration
- Updated documentation, improved code for the adapters, removed redundancy.
- Fixed issues with Elasticsearch logger.
- Added more config settings and env variables.
- Modified build-tarball to accept version as argument.

### Chat Widget Improvements
- Chatbot Widget v0.3.6. Made changes to chatbot widget to better handle session management so it works well with chat history on the backend. Updated client examples.
- Chat Widget v0.3.7. Fixed issues with input box focus ring. Now it matches global theme. Changed theme for activities example.

## [1.0.1] - 2025-05-23

### Documentation
- Minor updates to doc files to align with recent changes
- Update architecture diagram

### Core Services

- Fixed issues related to missing error when context is not available in the inference clients

### Chat Widget Improvements
- Improved chatbot widget
- Update Chat Widget Version to v0.3.5
- Updated build script for widget project

### Utilities
- New utils/scripts folder with new git utility to extract commit history and populate CHANGELOG. 

## [1.0.0] - 2025-05-19

### Core Features
- Initial release of ORBIT with full server and CLI functionality
- ORBIT CLI tool for server management
- API key management for service control

### LLM Integration
- Support for multiple LLM providers:
  - Ollama (preferred)
  - llama.cpp
  - vllm
  - Mistral
  - OpenAI
  - Anthropic
  - Gemini

### Data & Storage
- RAG capabilities with SQLite & Chroma integration
- Sample database setup scripts for quick start

### Deployment
- Docker deployment support

## Guidelines

All notable changes to the ORBIT project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).