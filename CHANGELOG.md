# Changelog

## [1.2.1] - 2025-07-23

### Fault Tolerance & Architecture
- Implemented new circuit breaker pattern and fault tolerance mechanisms
- Added new fault tolerance service with comprehensive error handling
- Improved fault tolerance architecture with additional test coverage
- Added adapters health endpoints for better monitoring
- Enhanced abstraction and reusability with additional generic classes
- Refactored and cleaned up redundant code for better maintainability

### API & Authentication
- New API Key Adapter Association feature - associate adapters with API keys
- API keys now point to specific retriever behavior instead of single collection
- Removed collection_name field references throughout the codebase
- Updated adapter configuration to use adapter-specific settings

### Vector Retrievers & RAG
- Refactored Chroma and QDrant QA retrievers with base class extraction
- Improved Intent RAG PoC with enhanced SQL template configuration
- Added Streamlit UI app for Intent RAG demonstration
- Enhanced PostgreSQL semantic RAG system with improved examples
- Updated RAG examples and removed sentence transformers dependencies

### Inference & Moderation
- Fixed issues with vLLM inference client and improved unit tests
- Added comprehensive test coverage for vLLM functionality
- Fixed moderator service issues and improved unit tests
- Updated default moderator configuration to use Ollama
- Removed unused unit tests for cleaner codebase

### UI & Demo Applications
- Enhanced Streamlit PoC with UX improvements
- Added additional script for Chroma example demonstration
- Expanded QA sets for city-qa-pairs.json with more comprehensive data
- Updated orbit architecture diagram to reflect current system design

### Docker & Deployment
- Updated docker scripts for improved deployment process
- Enhanced setup.sh with model location updates and GGUF download script
- Moved scripts to install directory and removed utils folder
- Improved deployment configuration and script organization

### Documentation & Configuration
- Updated configuration files with improved settings
- Enhanced documentation for fault tolerance features
- Updated architecture diagrams to reflect current system design
- Improved configuration management and deployment documentation

## [1.2.0] - 2025-07-07

### Authentication & Security
- Introduced new authentication service with CLI integration
- Improved CLI tools for better user experience with authentication operations
- Added config-based authentication enable/disable controls

### Chatbot Widget & UI Improvements
- Chat Widget v0.4.11 with bug fixes and UX enhancements
- Fixed suspended state issues after initial messages
- Improved input field styling and border handling
- Enhanced Widget Theming App with code highlighting and download functionality
- Updated Node API client to version 0.5.1 with optimizations
- Improved demo chat app UX and removed unused dependencies

### Docker & Deployment
- Enhanced docker deployment scripts and setup procedures
- Added MongoDB initialization logic improvements
- Fixed docker deployment issues with clean and test scripts
- Improved tarball creation script with better sample data

### Code Quality & Architecture
- Removed language detection module due to complexity and ineffectiveness
- Improved CLI code structure with direct command-to-handler mapping
- Enhanced logging summary for better server startup feedback
- Updated MongoDB service and reranker initialization logic

### Documentation & Configuration
- Updated README with improved diagrams and content
- Enhanced widget documentation and usage instructions
- Added theming app demonstration to documentation
- Improved setup and configuration scripts

## [1.1.4] - 2025-06-27

### Docker & Deployment Scripts
- Improve docker and setup scripts
- Fix profile 'torch' and docker deployment issues
- Added missing google-cloud dependency for profile 'commercial' in toml file

### Security & Moderation
- Fixed issue related to moderation called after LLM response instead of checking first before returning final response to client
- Integrate new llm_guard service with existing moderators. Now it's possible to use both services to enforce safety.
- Make safety check bidirectional (user prompt and LLM response)

### Vector Database & Retrieval
- Added Qdrant vector retriever (similar to Chroma)

### Code Quality & Architecture
- Chat Service Module: Significant improvement in code quality, maintainability and testability

### Inference Providers
- Added cohere and IBM Watson AI inference client

### UI/Widget Improvements
- Added new Widget Theming App
- Chat Widget v0.4.9 new version of Widget with further UX enhancements and design updates

## [1.1.3] - 2025-06-12

### Language Support

- Improve language detection module for more accurate language detection.
- Updated language detection unit test for better coverage.
- Improve language detection flow in chat_service.

### vLLM

- Fixed problem with vLLM inference. Updated vllm settings in config.

### UI/Widget Improvements

## [1.1.2] - 2025-06-09

### UI/Widget Improvements
- Significant UI/UX enhancements to the widget (v0.5.0)
- Updated chat examples to use latest release chat widget 0.4.0
- Removed widget project as it's been moved into its own repo
- Updated ORBIT logo
- Updated links in README.md to point to new chatbot widget project
- Updated orbit diagram and orbit chat GUI example

### Architecture & Code Structure
- Refactored SQL and vector retrievers modules to promote inheritance
- Added new settings based on recent additions of vector retrievers
- Added new endpoints for file upload with corresponding retrieval adapter (early stage)
- Use parameter num_ctx from inference provider for conversation history management
- Replace HF with Torch libraries for GPU/CUDA backend support

### Documentation & Content
- Added logo, roadmap section, plus other content improvements
- Fix navigation links
- Added links to MD files under docs
- Updated documentation to reflect recent changes
- Updated readme, added new diagram
- Added more items under roadmap
- Added more items under why orbit
- Added additional llama.cpp usage guide

### Bug Fixes & Technical Improvements
- Fix issues with API streaming logic
- Improved language detection module
- Fixed streaming issues in api.ts
- Further improved language detection and unit tests
- Updated API version to fix streaming issues
- Improved language_detector.py and unit tests
- Load conversation history warning from config.yaml

### Testing
- Added corresponding unit tests for new file upload endpoints
- Added unit tests for conversation history management
- Added unit tests for language detection improvements

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