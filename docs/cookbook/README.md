# ORBIT Cookbook

Step-by-step recipes and how-tos for configuring ORBIT, connecting data sources, and building real-world AI applications. Each recipe is self-contained and can be followed in order or used as a reference.

---

## Recipes

| Recipe | Description |
|--------|-------------|
| [Build a Full-Duplex Voice Assistant With ORBIT and PersonaPlex](build-full-duplex-voice-assistant-with-orbit-personaplex.md) | Most voice AI works like a walkie talkie — you talk, it thinks, it responds, you wait. |
| [Build a Natural Language Database Copilot With ORBIT](build-natural-language-database-copilot-with-orbit.md) | Turn plain English questions into live SQL queries across SQLite, PostgreSQL, and DuckDB — without writing a single line of glue code. |
| [Configure Ollama Presets for ORBIT](configure-ollama-presets-orbit.md) | ORBIT uses named Ollama presets so you can switch between CPU and GPU setups, different models, and remote Ollama hosts without editing inference code. |
| [Configure ORBIT Adapters and RAG](configure-orbit-adapters-and-rag.md) | ORBIT routes chat and tool requests through adapters: each adapter is a named configuration that ties an API key to a retriever, inference provider, and optional guardrails. |
| [Connect ServiceNow to Natural Language Queries Using ORBIT HTTP Intent Adapters](connect-servicenow-with-natural-language-using-orbit.md) | ServiceNow has a powerful REST API, but your support team still has to click through five menus to find an incident. |
| [Add a Conversational Layer to REST and GraphQL APIs With ORBIT](conversational-rest-graphql-api-orbit.md) | Expose any REST or GraphQL API through natural language so users can ask "What posts did user 3 write?" or "List the next five SpaceX launches" without knowing endpoints or... |
| [Deploy a Private AI Gateway for Regulated Data With ORBIT and Local Models](deploy-private-ai-gateway-for-regulated-data-with-orbit.md) | Healthcare records, financial transactions, classified government documents — some data cannot touch the public internet under any circumstances. |
| [Deploying Full-Duplex Voice Assistants for Hands-Free Field Service with ORBIT](deploying-full-duplex-voice-assistants-field-service.md) | Field technicians often operate in high stakes environments where manual searching through physical or digital technical documentation is both slow and hazardous. |
| [How to Deploy ORBIT with Ollama](how-to-deploy-with-ollama.md) | ORBIT is a self hosted gateway that unifies AI providers, databases, and APIs behind one OpenAI compatible API. |
| [Building an AI Database Copilot for Natural Language Business Intelligence with ORBIT](implementing-database-copilot-natural-language-bi.md) | Transforming raw database tables into actionable business insights usually requires specialized SQL knowledge or complex BI tools. |
| [Query the Web in Natural Language With ORBIT and Firecrawl](natural-language-web-queries-orbit-firecrawl.md) | Turn "What is quantum computing?" or "Summarize the Python Wikipedia page" into answers without building a scraper or hand writing prompts. |
| [ORBIT Adapter Capability Architecture Deep Dive](orbit-adapter-capability-architecture-deep-dive.md) | ORBIT's capability based adapter architecture removes brittle adapter specific branching from the retrieval pipeline and replaces it with declarative behavior. |
| [ORBIT API Keys and Authentication](orbit-api-keys-and-authentication.md) | ORBIT uses API keys to route requests to adapters and optional user authentication (login, RBAC) for admin and CLI operations. |
| [ORBIT Fault Tolerance and Circuit Breakers](orbit-fault-tolerance-circuit-breakers.md) | ORBIT can run adapters with fault tolerance: parallel execution, timeouts, and circuit breakers that stop calling failing adapters until they recover. |
| [ORBIT File Upload and RAG](orbit-file-upload-rag.md) | ORBIT's file adapter lets users upload documents (PDF, DOCX, TXT, images, audio, etc.), which are chunked and indexed into a vector store or DuckDB. |
| [Build a Full-Duplex Voice Assistant With ORBIT and PersonaPlex](orbit-personaplex-full-duplex-voice-assistant.md) | If you want natural voice conversations, turn based pipelines (STT LLM TTS) add latency and make interruptions awkward. |
| [ORBIT Rate Limiting and Quotas](orbit-rate-limiting-and-quotas.md) | ORBIT can enforce rate limits (per IP and per API key) and optional quotas (daily/monthly per key) with progressive throttling. |
| [Build a Resilient AI Gateway in ORBIT With Failover, Circuit Breakers, and Rate Limits](orbit-resilient-ai-gateway-failover-rate-limiting.md) | Most AI outages are not full outages, they are partial failures: one provider slows down, one adapter times out, and traffic spikes trigger cascading latency. |
| [ORBIT Server Production Deployment](orbit-server-production-deployment.md) | Running ORBIT in production means making the server resilient, manageable, and optionally secured with TLS. |
| [ORBIT Vector Store and Embeddings Setup](orbit-vector-store-embeddings-setup.md) | ORBIT uses embeddings to index and search text in vector stores (Chroma, Qdrant, Pinecone, Milvus, Weaviate). |
| [Run the ORBIT Chat CLI (orbitchat)](run-orbit-chat-cli.md) | The orbitchat CLI is a standalone browser based chat app that talks to the ORBIT API. |

---

Back to [ORBIT documentation](../).
