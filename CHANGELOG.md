# Changelog

## [2.4.0] - 2026-01-23

### Core System Updates
- Intent Agent Retriever: Added IntentAgentRetriever with function calling capabilities for complex task execution
- FastAPI Optimizations: Implemented ORJSONResponse for improved API performance and serialization speed
- GPU Auto-Detection: Added automatic GPU detection and included SmolLM2 model support
- Audit & Logging: Separated audit and logging Elasticsearch indices for better data organization

### Bug Fixes & Technical Improvements
- Ollama Streaming: Fixed streaming timeout issues and added SmolLM2 GPU preset
- Vector Store Fallback: Fixed vector store fallback logic when ChromaDB is disabled
- Gemini Provider: Fixed streaming errors in Gemini integration
- Torch XPU: Fixed compatibility issues with torch.xpu backend
- Intent Agent: Fixed parameter extraction bugs and added tool validation logic
- Test Suite: Fixed CLI integration and Redis integration tests

### Documentation & Configuration
- README Revamp: Redesigned README for better readability and scannable onboarding
- Docker Profiles: Added minimal configuration profile for Docker deployments
- Documentation Updates: Updated contact links, support information, and sandbox references
- Docker Scripts: Updated and improved Docker deployment scripts

## [2.3.0] - 2026-01-14

### Core System Updates
- Composite Intent Retriever: New CompositeIntentRetriever for multi-source query routing with parallel template search, shared embedding client, and best-match routing based on similarity scores
- Multi-Stage Template Selection: Extended composite retriever with LLM reranking and string similarity stages for improved template matching accuracy
- Template Hot-Reload: Added CLI command and API endpoint to reload intent templates without server restart (Issue #126)
- OpenAI-Compatible Endpoint: Exposed /v1/chat/completions endpoint enabling official OpenAI SDK clients to work against ORBIT (Issue #57)
- TensorRT-LLM Provider: Added NVIDIA TensorRT-LLM as new inference provider with dual-mode support (direct and API)
- OpenRouter SDK: Added native OpenRouter SDK support for inference and embeddings, replacing OpenAI-compatible client
- Autocomplete Suggestions: Implemented query autocomplete system extracting suggestions from intent template nl_examples with fuzzy matching
- Rate Limiting: Added Redis-backed rate limiting middleware with IP spoofing protection, atomic Lua scripts, and configurable trusted proxies
- Throttling Quotas: Added per-API-key quotas with progressive delays complementing existing rate limiting
- Audit Trail Storage: Added multi-backend audit trail storage (SQLite, MongoDB, Elasticsearch) with optional gzip compression (Issue #130)
- Clock Service Improvements: Added timezone validation, caching, per-adapter time_format override, and health check methods
- Redis Cache Clearing: Added comprehensive cache clearing on startup to prevent orphaned data
- Circuit Breaker Fix: Added thread safety and max size caps to prevent memory leaks

### Chat-app & UI Improvements
- Agent Selection Cards: Replaced dropdown-based agent selector with full-screen card list for better discoverability
- Sidebar Controls: Moved adapter/config controls into sidebar keeping chat header focused on conversations
- Stop Streaming: Implemented server-side stream cancellation with stop button in chat UI
- Autocomplete UI: Added 300ms debounced autocomplete dropdown with keyboard navigation in message input
- Thread Discoverability: Replaced minimal start-thread button with descriptive callout card and rotating example prompts
- Application Name Config: Added configurable application name via VITE_APPLICATION_NAME for browser tab title
- Agent Routing: Added shareable agent URLs with slug-based deep links
- Welcome Heading: Added runtime welcome heading with mode-aware placement
- GitHub Stats Badge: Added GitHub CTA in chat header
- Improved Limits UX: Better handling for threads, messages, and uploads with in-context warnings
- Mobile UX: Keep focus after autocomplete selection, centered message input caret with placeholder

### Bug Fixes & Technical Improvements
- Streaming Fixes: Fixed real-time streaming by skipping LLM step by name, added 50ms batching buffer, preserved spaces in content
- Scrolling Fixes: Fixed scrolling during streaming and in thread conversations
- Threading Fixes: Added supports_threading capability, fixed confidence checks for valid retrieval results, fixed button showing for "no results"
- ChromaDB Cache: Fixed stale collection cache causing search failures with cache validation
- Duplicate Initialization: Fixed duplicate service initialization in thread/database services
- Redis Lua Scripts: Fixed register_script() usage for redis-py 7.x compatibility
- Qdrant Fixes: Fixed clear_collection FilterSelector validation error, added Qdrant Cloud URL-based connection support
- OpenRouter Fixes: Strip model artifacts from responses, add SQL file support
- Ollama Cloud: Fixed response handling and increased context window to 32K
- Embedding Validation: Fixed false-positive warnings for Ollama-based retrievers
- Vector Dimension Mismatch: Optimized handling with pre-compiled regex patterns
- Module Import Fix: Fixed ModuleNotFoundError when running bin/orbit.py directly
- Python Client: Fixed streaming with httpx and direct stdout for real-time output

### API & Client Updates
- orbitchat v2.10.2: Published new NPM package versions (v2.4.0 through v2.10.2) with UI improvements and bug fixes
- Node API v2.1.6: Updated with autocomplete support and various fixes
- Python Client v1.1.6: New version with markdown rendering in responses and aligned slash completions
- Chat Widget v0.6.1: New versions with conversation deletion, markdown alignment, and theme improvements

### Security Improvements
- API Path Security: Replaced /api/proxy/ paths with /api/ to hide proxy architecture
- API Key Masking: Mask API keys in audit logs and chat history storage
- Moderation Messages: Fixed client error handling to display moderation messages properly
- LLM Guard Removal: Removed deprecated LLM Guard service, consolidated to Moderator-only content moderation

### Documentation & Configuration
- Test Organization: Reorganized 60+ test files into logical category folders (Issue #64)
- Docker Improvements: Added orbitchat web app to basic Docker image, enabled API middleware mode
- Setup Script: Added flexible multi-profile syntax, --torch-backend option, and uv support
- Qdrant Scripts: Added cloud support and update mode for collection scripts
- DuckDB Utils: Added CSV-to-DuckDB utilities and template testing scripts
- TTS Sanitization: Added content sanitization to skip tables, charts, and code blocks before TTS generation

## [2.2.0] - 2025-12-12

### Core System Updates
- vLLM Dual-Mode Support: Added direct mode to vLLM inference service allowing in-process model loading with GPU, similar to llama_cpp and bitnet providers
- Audio Config Split: Split sound.yaml into separate tts.yaml and stt.yaml with independent provider configs, updated adapters to use stt_provider/tts_provider
- Ollama Improvements: Added configurable adapter_preload_timeout (default 120s), improved warm-up with keep_alive and skip-if-loaded optimization, added ollama_remote for self-hosted servers
- Language Detection: Skip Redis calls when stickiness is disabled, fixed confidence calculation and metadata exposure bugs
- Jinja2 Templates: Converted intent templates to Jinja2 format with corresponding unit tests (Issue #69)
- Qdrant Cloud: Added URL-based connection support with auto-index creation for payload fields
- File Processing: Added MarkItDown as alternative processor, added full data mode for CSV/JSON with configurable thresholds for exact lookups
- Adapter Config Fix: Fixed adapter config not updating after reload in chat service (Issue #92)
- Maintenance Mode: Added runtime flag and UI for out-of-service messaging

### Chat-app & UI Improvements
- Mobile UI Enhancements: Added iOS/Android PWA meta tags, improved touch interactions, redesigned MessageInput with stacked layout, added larger touch targets (44px)
- Dark Mode Fixes: Fixed desktop chat dark background inconsistencies, aligned chat layout with sidebar
- Adapter Notes: Sync markdown styling with theme, fix notes not loading on startup in middleware proxy mode
- Middleware Proxy: Auto-select first adapter on startup, replace adapters.yaml with environment variable configuration
- Thread Improvements: Fixed markdown rendering in conversation threads

### Bug Fixes & Technical Improvements
- Middleware Proxy Security: Removed API keys and URLs from /api/adapters response, fixed undefined variable errors
- Startup Fixes: Resolved startup errors, reduced duplicate logging, dynamically load providers from inference.yaml
- CLI Fixes: Fixed arguments not overriding build-time env vars in orbitchat, fixed MaxListenersExceededWarning
- Template Rendering: Fixed undefined variables in Jinja2 filters, fixed HTTP Retriever and GraphQL templates after migration
- MongoDB: Fixed insertion error for documents containing ObjectApiResponse, deduplicate query results
- File Cleanup: Fixed orphan files remaining after clearing conversations in middleware mode
- Script Fixes: Fixed bash compatibility issues on Mac

### API & Client Updates
- orbitchat v2.3.9: Published new NPM package versions (v2.2.5 through v2.3.9) with UI improvements and bug fixes
- API Middleware: Fixed integration for threads, files, and new conversations

### Documentation & Configuration
- AWS Deployment: Added ALB deployment guide with WAF configuration, Dockerfile and docker-compose for containerized deployment
- Dependencies: Updated Ollama to 0.6.1, moved Ollama to default profile, updated tarball script with pre-configured db
- Examples: Added Alberta Shelter Occupancy Adapter, replaced Contact with HR template examples
- Installation: Reordered options with latest release as recommended method

## [2.1.1] - 2025-11-27

### Core System Updates
- GraphQL Intent Adapter: Added new GraphQL intent adapter with examples
- File Metadata Consolidation: Consolidated file metadata storage into main backend database, removed separate files.db, updated FileMetadataStore to use DatabaseService interface
- Chat History Cleanup: Implemented automatic cleanup for chat history messages exceeding token budget (deletes old messages when session exceeds 120% of token budget)
- Elasticsearch Log Templates: Enhanced log templates with 16 new query templates (endpoint analysis, user activity, request tracing, order/job events, service health), expanded domain vocabulary, and correlated request traces
- Default Model Updates: Changed default model to granite4:1b for ollama and llama_cpp providers
- Dependencies: Updated various packages to latest versions

### Chat-app & UI Improvements
- Thread Replies: Fixed thread replies display and focus management (show user questions, prevent main input from stealing focus, refocus thread input after sending)
- UI Styling: Polished UI styling with expanded sidebar card spacing, aligned actions with titles, centered conversation header row
- Thread Panel Theme: Unified thread panel theme to match main chat palette with scoped styling
- Configure API Button: Fixed enter key not working issue, renamed button label to 'Update'

### Bug Fixes & Technical Improvements
- ThreadDatasetService: Implemented singleton pattern to prevent duplicate initialization and reduce resource usage
- File Processing: Added fallback processors for PPTX/XLSX/VTT formats to eliminate docling dependency, fixed ChromaDB intermittent "Collection does not exist" race condition
- Cohere Services: Fixed Cohere v2 API support with AsyncClientV2 initialization, added vision service support, maintained backward compatibility with v1 API
- Voice Streaming: Fixed realtime voice streaming stability by wrapping raw PCM chunks in WAV containers before Whisper STT
- Logging Refactoring: Standardized logging across codebase by replacing self.logger.* calls with module-level logger.* calls
- Whisper Logger: Fixed logger definition moved from module docstring to module level
- CLI Restart: Fixed restart command when server uses non-default port (removed hardcoded port 3000)
- Elasticsearch Templates: Fixed JSON parsing error in search_slow_requests template by removing unsupported {% set %} statements
- Qdrant Integration: Completed Qdrant integration with v1.16 API compatibility, fixed file deletion cleanup
- File Attachments: Fixed retry action to send file attachments along with questions, fixed attachment IDs not being sent
- Unit Tests: Fixed various unit test errors

### API & Client Updates
- orbitchat v2.1.7: Published new NPM package versions with UI improvements and bug fixes

### Other Changes
- Firecrawl Templates: Added helper scripts to generate firecrawl intent templates
- GGUF Models: Updated gguf models config with granite4-1b
- Logging Verbosity: Reduced info verbosity by setting config yaml loading to debug level
- Documentation: Updated conversation_history.md with new architecture, updated SECURITY.md

## [2.1.0] - 2025-11-22

### Core System Updates
- Conversation Threading: Implemented conversation threading support enabling follow-up questions on retrieved datasets without re-querying the database
- Audio Services: Added global audio service gating with sound.enabled flag, new TTS providers (CoquiTTS, Gemini Audio Service, vLLM TTS)
- Authentication: Authentication now enabled by default, removed auth.enabled setting
- Adapter Refactoring: Split adapters.yaml into separate files, refactored DynamicAdapterManager (57% code reduction, 121 unit tests)
- Configuration: Configured install/default-config as default, only enable simple-chat adapters by default

### Chat-app & UI Improvements
- Threaded Replies UI: Implemented Slack-style nested thread panels with inline composers
- Mobile Layout: Added slide-in sidebar drawer and responsive mobile controls
- Audio/Upload UI: Added enableAudioOutput flag with UI gating for mic/voice buttons and file upload controls
- Sidebar & Input: Improved sidebar metadata, centered input field, moved voice toggle inline, updated MarkdownRenderer to v0.4.2

### Bug Fixes & Technical Improvements
- Thread Dataset Deletion: Fixed cascade deletion bug when Redis storage enabled
- MongoDB Fixes: Resolved ObjectId JSON serialization errors and datetime deprecation warnings, fixed template rendering for arrays/dicts
- Audio Providers: Fixed issues with Eleven Labs, Whisper adapter, and TTS voice handling
- Security: Fixed critical CORS misconfiguration and implemented security headers middleware
- SQL & Database: Fixed SQL template parametrization for DuckDB/Postgres, added missing token_count field to SQLite schema
- HTTP Intent: Fixed URL parameter substitution causing 404 errors
- Logging: Replaced verbose config checks with Python standard logging levels

### API & Client Updates
- Node API 2.1.0: Published new NPM package version
- orbitchat v2.1.2: Published with UI improvements and bug fixes
- MarkdownRenderer: Updated to v0.4.2

### Audio & Voice Features
- Sound Adapter: Added new TTS/STT capabilities with real-time audio streaming
- Voice Recognition: Improved voice recognition with auto-send after silence, fixed voice input hijacking text input
- Audio Optimization: Optimized audio processing for NVIDIA GPU/CUDA hardware

### Conversation & Threading
- Thread Implementation: Added Redis storage for thread datasets with cascade cleanup
- History Optimization: Implemented intelligent fetch limits reducing database queries by 98%

### CLI & Tools
- CLI Redesign: Full refactoring of ORBIT admin CLI, renamed flags to --enable-upload / --enable-feedback

### Other Changes
- File Upload: Conversation uploads scoped per chat, titles capped at 100 characters, added paste screenshots support
- Dashboard: Improved dashboard with basic authentication enabled
- Documentation: Updated conversation history docs, added sample API keys script

## [2.0.2] - 2025-11-11

### Chat-app & Adapter API Updates
- Adapter File Support Flag: Added flag to indicate whether an adapter supports file uploads, enabling/disabling upload functionality in chat-app accordingly
- Adapter Info UI: Added new adapter info fields in chat-app UI showing support status and file capabilities
- orbitchat 1.0.2: Published new version to npm with latest UI and adapter info features
- Ollama Vision Service: Added new vision service for ollama vision models

## [2.0.1] - 2025-11-10

### Core System Updates
- Sentence Transformers Embedding: Added new embedding service using the sentence transformer package with Hugging Face
- Chunking Strategy Settings: Added new chunking strategy settings for files in config.yaml
- Config Updates: Updated adapters.yaml to reflect new chunking settings for file-based adapters, changed default Anthropic model in inference.yaml
- Remove Intent Caching Plan: Removed intent caching plan from codebase

### Bug Fixes & Technical Improvements
- Fix Anthropic Provider: Fixed Anthropic provider issue where top_p parameter is no longer accepted by API
- Adapter Reloading Fixes: Applied multiple fixes to adapter hot reloading logic, fixed adapter disable issues when reloading
- Load Adapter Config Settings: Fixed adapter config loading to use real adapter config settings instead of config files
- Verbose Logging Improvements: Added more log output for tracing issues when verbose is enabled, applied verbose check on logging in file_routes.py
- Recursive Chunker: Changed log line to debug level in recursive_chunker.py

### Chat-app & UI Improvements
- Chat-app Updates: Load adapter information for default-key, toggle GitHub visibility on/off based on env variable
- Enable Chat-app Limits: Added limits for max files, conversations, and other settings
- Message UI Improvements: Removed rectangle from message bubble for cleaner appearance
- Adapter Info Refresh: Refresh adapter info section on top when adapter is reloaded on the backend
- UI Refinements: Removed "Refresh" text from top, using refresh icon only for better UX
- Chat-app Maintenance: Added tar exclusion in gitignore, renamed API testing instructions

### API & Client Updates
- New orbitchat NPM Package: Published new orbitchat NPM package (v1.0.0) for easy installation of ORBIT UI chat interface

### Retrieval System
- DuckDB Retriever Updates: Further improvements to DuckDB retriever and templates

### Documentation & Examples
- Documentation Updates: Updated and better organized documentation structure
- README Improvements: Improved intro sections, replaced DB chat video example with one showcasing inline charts
- Roadmap Updates: Updated roadmap and cleaned up documentation
- NPM Installation Instructions: Added new orbitchat npm install instructions to README
- Docker Configuration: Added config files to gitignore for Docker deployment

## [2.0.0] - 2025-11-05

### Core System Updates
- SQLite Backend: Added support for SQLite backend in addition to MongoDB for easier setup and simplicity
- Refactor Backend Services: Refactored core backend services to be more db-agnostic, fixed unit tests, added backend selection in config summary logger
- Added DuckDB: New DuckDB store & datasource, updated roadmap documentation
- Vision Services: New vision AI services in addition to embeddings, inference and rerankers, fix logging configurator, remove warning suppression
- Remove inference_only mode: Removed the inference_only configuration option and all related code paths; system now exclusively uses adapters from adapters.yaml for routing
- Update Inference.yaml: Update ollama_cloud settings for RAG purposes, enabled other providers previously marked as disabled
- Config Updates: Update adapters and inference yaml config files to match latest features, optimized Ollama settings for large context
- Update stores.yaml: Disable pinecone and qdrant by default
- Adapter Capabilities System: Replaced hardcoded adapter type checks with declarative capability system using AdapterCapabilities with retrieval_behavior and formatting_style enums, integrated with adapter reload system, includes 25 unit tests and extensive documentation
- Update Adapters Configuration: Updated adapters.yaml to reflect capabilities settings and default adapter names, added more DuckDB analytics templates

### New Adapters & Features
- New Files Adapter: Introduced new file adapter to perform AI reasoning tasks on files
- New Multimodal Adapter: Added new multimodal adapter to chat with files in addition to regular inference
- New DuckDB Adapter: Added new DuckDB retriever adapter for querying CSV/Parquet sources using SQL
- New Adapter Info API: Added new endpoint to pull details about the agent associated with api key, including adapter name and AI model being used
- File Adapter Integration: Implement file adapter integration with api.ts and chat-client for multimodal support, further updates to file adapter pipeline, more unit tests
- File Retriever Updates: Further completion of new file retriever adapter, fix unit tests, update roadmap, added file conversation plan
- Retrievers Adapter Updates: Further improvements of the new file retriever adapter, improve base retriever vector chunking handler for SQL and other intent-based retrievers
- Firecrawler Chunking: Implemented vector chunking for HTTP firecrawler adapter when returning large content from web site

### API & Client Updates
- Node API 1.0.0: Update chat-app to use NPM Node API v 1.0.0, published new version to NPM
- Python chat client: Fix formatting issues for numeric values, dates and emails, published v1.1.3, added adapter planning prompts for future use
- Py Chat CLI 1.1.2: New Release of Python chat CLI to 1.1.2
- Rename API Key: Added new api endpoint to rename api keys
- Add API key validation: Add validateApiKey() method to ApiClient and integrate validation in chat-app when configuring API settings, replace console.error with console.warn for user-friendly messages
- Add caching to prevent repeated initialization: Caches FileVectorRetriever instances to avoid redundant ChromaDB connections and embedding initialization on every request, includes comprehensive test coverage (19 new tests)

### Chat-app & UI Improvements
- Chat-app Updates: Multiple improvements to chat-app files upload functionality, associate conversations with their own api keys / session ids, further improvements
- Chat Widget Theming Fixes: Renamed background to questionsBackground to match the parameter in chat widget
- Clear All Conversations: Added clear all conversations button
- Multimodal Adapter CleanUp: Clean up debug lines after multimodal adapter, only log when verbose / debug is enabled, added file vacuum script
- MessageList Scrolling Fixes: Fixed scrolling down issues in MessageList component
- MessageInput Improvements: Fixed scrolling down, improved input box, fixed unbounded text in input field plus other UX minor improvements

### Bug Fixes & Technical Improvements
- Fix streaming issues: Fix streaming issues, update logging verbosity from intent modules, update chat_client and test_mcp clients
- Fix SQL and HTTP Intent Issues: Fix issues preventing SQL and HTTP based intent retrievers from being returned by the inference pipeline
- OpenAI Streaming Issues: Address issues from OpenAI inference provider, added more unit tests, updated openai version
- Fix text_vector_retriever_truncation: Fix unit test
- Fix Unit Tests: Fix remaining of tests causing errors
- Update intent_http_base.py: Added dump query results when verbose is true
- Update llm_inference.py: Added chart instructions when asking to generate charts in the prompt, adjusted chart instructions prompt, removed unused build_chat_instruction_compact
- Multimodal Adapter Loading Fix: Fixed issues with Multimodal Adapter not being loaded properly after introducing adapter reloading functionality

### File & Retrieval System
- Files Adapter Updates: Further refinement of new file adapter towards new release, more test coverage for file adapter, updated vector stores to better handle file chunking, enable sentence transformer library in minimal installation profile
- File Adapter Updates: Further improve new file adapter, added more unit tests
- Update with MarkdownRenderer 0.2.0: Import MarkdownRenderer 0.2.0
- Update package.json: Update MarkdownRenderer to v0.3.3, updated packages, removed deprecation warnings, updated to latest version of MarkdownRenderer (no more nesting warnings)

### Testing & Quality Assurance
- Create Unit Test: New unit test for file adapter
- Create File Unit Test: Add additional file adapter unit test
- Ollama Embedding Test: Added new test for ollama embedding

### Documentation & Examples
- Create secure LLM RAG Diagram: New diagram describing on-prem LLM architecture
- Update legal document example: Updated document
- Remove adapter comparison: Removed unused document
- Data Correlation Examples: Added sample files to test data correlation when analyzing multiple files
- More Files Examples: Additional files examples to test multimodal capabilities
- Roadmap Updates: Update roadmap plans, add reranking new design, add roadmap item (SQLite)
- Update logs_templates.yaml: Refine DSL queries
- Documentation Cleanup: Reorganized documentation structure
- Documentation and Scripts Updates: Updated scripts and docs to reflect latest release v2.1.0

## [1.6.0] - 2025-10-25

### Core System Updates
- Roadmap Updates
- New MongoDB Intent Adapter
- New Firecrawl Adapter
- HTTP and ES Intent Updates

## [1.5.9] - 2025-10-24

### Core System Updates
- Added HTTP REST adapter.
- Added http and elasticsearch intent adapter types; addressed warning suppression issues.
- Fixed issues with Cohere inference provider.
- Errors handled gracefully when an inference provider is disabled, ensuring adapters continue to load normally.
- Added enable setting in inference.yaml for selective provider loading; granite4:micro set as GGUF default.
- Integrated new zAI inference service
- More Vector Stores: Added support for faiss, marqo, milvus, pgvector, and weaviate vector stores.

### Other Changes
- Update classified demo template: Added another demonstration template.
- Suppress Warnings: Suppressed server log runtime warnings; minor provider fix.
- Update Setup Profiles: Moved dependencies from 'commercial' to 'minimal' profile and renamed 'commercial' to 'cloud'.
- Setup Script, Embedding Plans: Improved setup script to prompt for python version; added embedding plan (sentence transformers); updated minimal profile.

## [1.5.8] - 2025-10-17

### Core System Updates
- Update Contact Templates: Regenerate SQL intent templates for contact example.
- Update template_reranker.py: Fix minor issue causing some templates to throw errors.
- Add Bitnet AI Provider: Integrate Bitnet provider; fixed SQL template strategy and reranker issues.
- SQL Templates Fixes: Improve SQL intent templates generation logic.
- Ollama Cloud Fixes: Resolve issues with Ollama cloud and SQL template generation scripts.
- Create Intent Result Caching Strategy: Implement caching for follow-up questions in intent retrievers.
- Issue #48: Enable datasource overriding in adapters.yaml for SQL adapters.
- SQLite db parameter: Replace db_path with database in datasource.yaml for better configuration clarity.
- Update adapters.yaml: Reinstate postgres intent template example.
- Update inference.yaml: Remove anyscale; set Ollama default model to granite4:micro.
- Update datasources.yaml: Complete supplemental datasource settings.

## [1.5.7] - 2025-10-15

### Core System Updates
- Fixed Issue #58: Transfer safety into its own yaml file, remove from main config.yaml.
- Fixed #53 - Dashboard: Issue resolved for DASHBOARD; linked issue and improved stability.
- Update dashboard_routes.py: Added datasource pooling panel to the dashboard for enhanced observability.
- Datasource Connection Pooling: Enabled connection pooling for datasources.
- New Datasource Registry: Introduced new datasource registry system for improved adapter compatibility and loading behavior.

### Other Changes
- Refined dashboard features for improved user experience.
- General refactoring and bug fixes for performance and stability.

## [1.5.6] - 2025-10-14

### Core System Updates
- AI Provider Services Consolidation: Massive refactoring of AI providers, removing unused providers and consolidating services
- Embedding Services Migration: Migrated embedding providers to new AI services architecture
- Moderators Migration: Brought moderators into new AI service architecture
- Adapters Refactoring: Improved adapter architecture for better maintenance and adaptability

### Bug Fixes & Technical Improvements
- Embedding Service Issues: Fixed double initialization of embedding services by dynamic adapter
- Inference Registry Fixes: Fixed double initialization of inference registry items
- Template Fixes: Fixed 'detect_anomalous_access_patterns' template and added detect_compartment_hopping

## [1.5.5] - 2025-10-10

### Core System Updates
- Adapters Refactoring: Improved adapter architecture for better maintenance and adaptability

## [1.5.4] - 2025-10-10

### Core System Updates
- Pinecone QA Adapter: Added new Pinecone QA Retriever Adapter for enhanced vector database support
- Vector Store Overriding: Enabled vector store overriding in intent adapters to choose between Chroma, Pinecone, Qdrant, Milvus, etc.
- SQL Intent Template Generator: Enhanced SQL intent template generator with improved functionality and documentation

### Python Client
- Python CLI v1.1.1: Published new python package version to PyPI
- Chat Client Fixes: Fixed markdown formatting issues in chat client

### UI & Demo Applications
- Theme Tab Updates: Added missing message background color picker to theming interface
- Dashboard Improvements: Enhanced dashboard UX with better line hovering and value display
- Chat App Enhancements: Added toggle for thumbs up/down buttons based on environment variable and increased logo size

### Documentation & Configuration
- README Updates: Multiple documentation improvements including video updates, contact examples, and scenario details
- Classified Example Updates: Updated templates and SQL Intent documentation
- Scraping Tools: Added scraping tools back for knowledge base extraction
- Configuration Cleanup: Removed sample adapters from default adapter.yaml configuration

## [1.5.3] - 2025-10-03

### Core System Updates
- Pinecone QA Adapter: Added new Pinecone QA Retriever Adapter for enhanced vector database support
- Configuration Updates: Load MongoDB database name from environment variables instead of hardcoded values

### Chat Widget & UI Improvements
- Chat Widget v0.5.3: Published new NPM version with markdown renderer integration
- Markdown Rendering: Fixed markdown styles and updated markdown-renderer package to v0.1.6
- UX Enhancements: Multiple improvements to chat-app user experience including:
  - Improved transition between message and input field
  - Removed vertical border for cleaner interface
  - Enhanced overall look and feel
  - Final round of UX enhancements for better user interaction

### SQL Intent & Retrieval System
- SQLite Intent Examples: Added new SQL intent templates for domain classified information
- Classified Data Example: Updated classified data example schema for better organization

### Deployment & Infrastructure
- Podman Support: Added new Podman project for alternative containerization deployment
- Roadmap Updates: Added future adapter-related features and improvements to development roadmap

## [1.5.2] - 2025-09-26

### Core System Updates
- Clear History Route: Added new endpoint to clear conversation history
- Dependencies Update: Updated orbit CLI chat package version

### Python Client
- Python Client v1.1.0: Integration with new clear conversation endpoint from ORBIT server

### Node API & Testing
- Node API Updates: Enable delete chat history functionality in Node API
- Node API Unit Tests: Added more comprehensive test coverage for the node API
- Node API Tests: Fixed issues with node API unit tests
- Package Updates: Updated package.json and published node-api NPM version 0.5.3
- Chat App Fixes: Fixed issues with chat-app integration

## [1.5.1] - 2025-09-25

### Core System Updates
- Ollama Refactoring: Simplified Ollama implementation and fixed issues with model overriding from adapters
- Inference Providers Update: Better handling of prompt and message chaining in LLM providers
- Elasticsearch Logging Fix: Fixed Elasticsearch logging issues and problems with chat_history and adapters incorrectly storing conversation

## [1.5.0] - 2025-09-24

### Core System Updates
- New Passthrough LLM Adapter: Added new adapter for pure conversation (passthrough) with models without context retrieval, similar to inference_only mode
- System Prompt Caching: Added system prompt caching using Redis service for improved performance
- Ollama Provider Enhancements: Added more settings to both ollama and ollama_cloud providers and updated ollama package
- Language Detection Improvements: Minor tweaks to language detection for French text and added Ollama Linux installation guide
- LLM System Instructions: Adjusted LLM system instructions to provide more accurate information

### SQL Intent & Retrieval System
- Adapter Embeddings Override: Enabled ability to override global embedding for each adapter
- SQL Intent Templates: Fixed issues with SQL templates and marked problematic templates for later review
- Intent Adapter Simplification: Further simplified SQL intent adapter by removing prompt generation and delegating to LLM pipeline

### Chatbot Widget & UI Improvements
- Theming App Enhancements: Added API key toggle hide button and improved preview thumbnails
- Widget React Example: Updated chat widget version
- Markdown Table Fixes: Fixed markdown column table misalignment issues

### Testing & Quality Assurance
- Unit Test Fixes: Fixed issues with test_redis_service.py and test_pipeline_server_integration.py
- Additional Test Coverage: Added test coverage for new passthrough LLM adapter

## [1.4.3] - 2025-09-04

### Core System Updates
- Improved Chroma and Qdrant vector retrievers with enhanced results confidence scoring logic
- Enhanced language detection steps for better accuracy

### Chatbot Theming Platform
- Fixed bugs preventing updates of API keys
- Added ability to toggle endpoint field on/off and updated deploy script
- Limited number of characters for API key and endpoint fields

### Documentation & Configuration
- Updated scripts for Chroma and Qdrant vector databases
- Removed outdated MCP details as they are no longer used

## [1.4.2] - 2025-09-01

### SQL Intent & Retrieval System
- Adapter issues: Fix issues with adapter config loading

## [1.4.1] - 2025-09-01

### SQL Intent & Retrieval System
- Intent Adapter Redesign: Introduced better design for SQL intent adapter with new configurable vector stores service
- SQL Adapter Fixes: Fixed config loading issues with SQL adapters and updated package version for commercial profile

### Python Chat Client
- Minor improvements: Updated chat-client (assistant text color and removal of warning about api-keys). Published new version 1.0.1.

### Testing & Quality Assurance
- Unit Test Fixes: Fixed intent retriever unit tests and removed unneeded tests

### Documentation & Configuration
- Updated ORBIT logo across the project

## [1.4.0] - 2025-08-31

### Core System Updates
- FastAPI MCP: Replaced existing MCP implementation with FastAPI MCP library for cleaner and more maintainable code
- Monitoring Dashboard: Added new monitoring dashboard for real-time resource monitoring

### Chatbot Widget
- Chat Widget v0.4.18: New NPM version with improved UX and bug fixes
- Chat Widget Fixes: Fixed issue when switching windows on desktop and replaced thinking animation with moving 3 dots

### Python Client
- Python Client v1.0.0: Introduced interactive session commands with better user experience
 
## [1.3.7] - 2025-08-29

### Monitoring
- Added prometheus dashboard for real-time resource monitoring

## [1.3.6] - 2025-08-26

### Retrievers
- Remove ununsed file adapter, clean up code.

### Examples
- Improve postgres cusotmer orders data generator (SQL intent adapter).
- Fix markdown issues in chat-app.

## [1.3.5] - 2025-08-20

### Core System Updates
- Clock Service: Introduced clock service for context-aware date/time based on specified timezone
- Ollama Provider: Fixed issues with Ollama cold starts and reduced code redundancy for Ollama services
- Ollama Embeddings: Fixed issues with Ollama embeddings dimensions settings and Qdrant intent adapter

### Chatbot Widget
- Chat Widget v0.4.15: Significant updates to theming app and general UX improvements
- Chat Widget v0.4.14: New NPM version with icon list updates and theming app improvements
- Widget Updates: Further improvements to chatbot widget behavior and theming app
- Theming App Fixes: Enhanced theming application with improved color presets and thumbnails

### Vector Retrieval & RAG
- Qdrant Retriever: Fixed repetitive initialization calls by moving connection check to singleton instance
- Pinecone Integration: Added Pinecone scripts similar to Chroma and Qdrant for better vector database support

### Documentation & Configuration
- README Updates: Multiple updates including stargazer snippet, SQL intent adapter examples, and video content
- Theme Presets: Updated color themes presets for better customization options
- Configuration Updates: Added clock_service to config.yaml and updated inference.yaml with llama_cpp parameters

### Testing & Quality Assurance
- Test Updates: Fixed errors in test_mcp_client.py and improved test coverage
- MCP Client: Updated test_mcp_client.py for better reliability

### Development & Dependencies
- Gemma Model: Added Gemma3 270m as default for basic installation
- Examples: Updated NPM widget version in react-example and improved Qdrant collection creation scripts

## [1.3.4] - 2025-08-15

### Core System Updates
- LLM-Guard Service: Resolve issues with llm guard service causing the server to stop responding, included more settings to improve resiliency

### UI & Demo Applications
- Theming App Improvements: Improve the default themes for the widget theming app

### Testing & Quality Assurance
- Performance Testing: Added perf tests using locust library

### Development & Dependencies
- Updated dev dependencies in toml file

## [1.3.3] - 2025-08-14

### Testing & Quality Assurance
- Update Test Cleanup Scripts - Improve test clean up scripts to further remove any leftover after running the unit tests

### Core System Updates
- Language Detection Fixes - Resolve issues related to incorrect language detection

### UI & Demo Applications
- Theming App Update - Add new env variable to toggle display unavailable message during maintenance

## [1.3.2] - 2025-08-12

### Widget Theming App
- Fixed API key update propagation issues
- Enhanced responsive design across different devices
- Improved numeric field validation
- Fixed API settings update issues

### Inference Pipeline & Adapters
- Added integration with additional inference services
- Implemented adapter-level inference provider overriding
- Fixed inference provider overriding issues by adapters

## [1.3.1] - 2025-08-10

### Core System Updates
- Updated Elasticsearch to 9.1.0
- Fixed Elasticsearch Logger incompatibility with new inference pipeline
- Fixed hardcoded port 3000 issues in unit tests and CLI login command
- Updated build-tarball.sh script to fix Mac-specific tar generation issues
- Updated README.md with logo improvements and size adjustments

## [1.3.0] - 2025-08-09

### Chatbot Widget
- Chatbot Widget v0.4.13 with bug fixes and UX enhancements
- Fixed issues in theming application and improved form input handling
- Enhanced markdown rendering with improved currency values display
- Fixed scrolling issues during response rendering and improved LaTeX rendering
- Increased typing effect speed for better user experience
- Updated widget version in react-example and theme app
- Widget Theming App: Enhanced question form handling with proper truncation

### SQL Intent & Retrieval System
- Significant refactoring of SQL Intent Adapter for improved abstraction and reusability
- Enhanced SQL retriever classes with better inheritance patterns
- Added comprehensive SQL templates for insights and analytics
- Improved intent SQL generation utilities and documentation
- Reorganized SQL intent YAML templates for better maintainability
- Enhanced unit tests for SQL intent functionality

### Documentation & Configuration
- Updated adapter configuration with enabled/disabled toggle settings
- Enhanced documentation for SQL intent features and examples
- Updated roadmap with current development plans
- Improved README.md with better organization and maintainer links
- Added Qdrant deployment instructions

### Core System Updates
- Updated Ollama provider to new version with chat endpoint interface
- Enhanced test utilities for better markdown response formatting
- Improved adapter settings management with configuration controls
- Fixed duplicate logging issues in inference steps

## [1.2.2] - 2025-07-30

### Inference Pipeline & Architecture
- Implemented new inference pipeline architecture
- Added language detection step to the inference pipeline
- Added lazy loading for inference providers to improve performance
- Enhanced provider factory with improved unit tests and import path fixes

### Docker & Deployment
- Improved docker-cleanup.sh script
- Updated tarball script
- Removed unused config.yaml settings

### Testing & Quality Assurance
- Added aditional vLLM unit tests
- Fixed minor import path issues in provider_factory.py
- Enhanced test coverage for inference providers

### UI & Demo Applications
- Updated widget react example with minor improvements
- Improved video content and demonstration materials

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

All notable changes to the ORBIT project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.1.0.html).