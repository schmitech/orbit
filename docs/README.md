# ORBIT Documentation

Welcome to the ORBIT (Open Retrieval-Based Inference Toolkit) documentation. This directory contains comprehensive guides for deploying, configuring, and extending ORBIT.

## Quick Start

- [Main README](../README.md) - Project overview and quick start guide
- [Server Setup](server.md) - Detailed server configuration and deployment
- [Configuration Guide](configuration.md) - Complete configuration reference

## Core Architecture

### Fault Tolerance System
- **[Fault Tolerance Architecture](fault-tolerance-architecture.md)** - Complete overview of the fault tolerance system, circuit breakers, and parallel execution
- **[Circuit Breaker Patterns](circuit-breaker-patterns.md)** - Detailed implementation patterns, state management, and best practices
- **[Fault Tolerance Troubleshooting](fault-tolerance-troubleshooting.md)** - Common issues, debugging, and performance tuning
- [Migration to Fault Tolerance](migration_to_fault_tolerance.md) - Migration guide from legacy system

### Adapters and Retrievers
- [Adapters Overview](adapters.md) - Adapter system architecture and configuration
- [Adapter Configuration](adapter-configuration.md) - Detailed adapter setup
- [SQL Retriever Architecture](sql-retriever-architecture.md) - SQL-based retrieval system
- [Vector Retriever Architecture](vector-retriever-architecture.md) - Vector database integration
- [File Adapter Architecture](file-adapter-architecture.md) - File-based adapters
- [SQL Adapter Implementation](sql-adapter-implementation.md) - Implementation guide

## Authentication and Security

- [Authentication](authentication.md) - User authentication and RBAC setup
- [API Keys](api-keys.md) - API key management
- [LLM Guard Service](llm-guard-service.md) - Content moderation and safety

## Data Sources and Storage

- [MongoDB Installation (Linux)](mongodb-installation-linux.md) - MongoDB setup guide
- [Chroma Setup](chroma-setup.md) - Vector database configuration
- [Conversation History](conversation_history.md) - Chat history management

## Advanced Features

- [MCP Protocol](mcp_protocol.md) - Model Context Protocol integration
- [Chat Service System Prompts](chat_service_system_prompts.md) - System prompt configuration
- [Llama.cpp Server Guide](llama-cpp-server-guide.md) - Local model server setup

## Development and Roadmap

- [Roadmap](roadmap/README.md) - Future development plans and architecture designs
- [Architecture Diagrams](images/) - Visual representations of system components

## Documentation Structure

```
docs/
├── README.md                              # This file
├── fault-tolerance-architecture.md       # 🆕 Fault tolerance overview
├── circuit-breaker-patterns.md          # 🆕 Circuit breaker details
├── fault-tolerance-troubleshooting.md   # 🆕 Troubleshooting guide
├── migration_to_fault_tolerance.md      # Migration guide
├── configuration.md                     # Configuration reference
├── authentication.md                    # Auth setup
├── adapters.md                         # Adapter system
├── server.md                           # Server setup
└── roadmap/                            # Future development plans
    ├── README.md
    ├── adapters/                       # Adapter strategy docs
    ├── security/                       # Security implementation
    └── *.md                           # Various design documents
```

## Key Features Documented

### 🆕 Enhanced Fault Tolerance
- Circuit breaker protection for adapter failures
- True parallel execution without blocking
- Configurable timeout and retry mechanisms
- Health monitoring and automatic recovery
- Performance optimization strategies

### Flexible Adapter System
- Multiple data source support (SQL, Vector, File)
- Dynamic adapter loading and management
- Custom adapter implementation guides
- Configuration-driven setup

### Enterprise Security
- Role-based access control (RBAC)
- API key management
- Content moderation integration
- Secure session management

### Scalable Architecture
- MongoDB for data persistence
- Vector database integration (Chroma, Qdrant)
- Local and cloud model support
- Containerized deployment options