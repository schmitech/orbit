# ORBIT MCP Flow - Detailed Diagrams

This document contains three focused diagrams for better readability and higher resolution exports.

---

## Diagram 1: High-Level Request Flow

```mermaid
flowchart TD
    Start([MCP Request Received<br/>POST /v1/chat]) --> Auth[API Key Authentication<br/>Middleware Layer]

    Auth --> AuthCheck{Valid API Key?}
    AuthCheck -->|No| AuthError([Return 401 Unauthorized])
    AuthCheck -->|Yes| Validate

    Validate[Request Validation<br/>Pydantic RequestModel] --> ValidCheck{Valid Request?}
    ValidCheck -->|No| ValidationError([Return 400 Bad Request])
    ValidCheck -->|Yes| SessionMgr

    SessionMgr[Session Manager<br/>Get or Create Chat History<br/>SQLite Database] --> Pipeline

    Pipeline[Pipeline Chat Service<br/>6-Step Processing Pipeline<br/>server/services/pipeline_chat_service.py] --> Step1

    Step1[Step 1: Safety Check] --> Step2[Step 2: Language Detection]
    Step2 --> Step3[Step 3: Context Retrieval]
    Step3 --> Step4[Step 4: Reranking]
    Step4 --> Step5[Step 5: LLM Inference]
    Step5 --> Step6[Step 6: Validation]

    Step6 --> SaveHistory[Save to Chat History<br/>Update Session]

    SaveHistory --> LogMetrics[Log Metrics<br/>Latency, Tokens, Cost<br/>server/logs/]

    LogMetrics --> StreamCheck{Streaming<br/>Enabled?}

    StreamCheck -->|Yes| StreamResponse([Stream Response<br/>Server-Sent Events<br/>SSE Protocol])
    StreamCheck -->|No| FullResponse([Return Complete Response<br/>JSON Format])
```

**Timeline**: Total 700-12,500ms
- Authentication: 1-3ms
- Validation: 1-3ms
- Session Management: 5-10ms
- Pipeline Processing: 600-12,000ms
- Logging: 10-50ms

---

## Diagram 2: Six-Step Pipeline Details

```mermaid
flowchart TD
    PipelineStart([Pipeline Input<br/>User Query + Session]) --> Step1

    Step1[Step 1: Safety Check<br/>Pre-Moderation] --> SafetyServices

    SafetyServices[Moderation Services] --> SafetyProviders

    SafetyProviders[OpenAI Moderation<br/>Google Perspective API<br/>Azure Content Safety] --> SafetyCheck{Content<br/>Safe?}

    SafetyCheck -->|No| BlockRequest[Block Request<br/>Return Moderation Error<br/>HTTP 400]
    SafetyCheck -->|Yes| Step2Start

    Step2Start[Step 2: Language Detection<br/>Identify User Language] --> LangDetect[Language Detector<br/>Detect Query Language]

    LangDetect --> LangResult[Language Identified<br/>Used for Localized Responses]

    LangResult --> Step3Start[Step 3: Context Retrieval<br/>RAG Pipeline]

    Step3Start --> RetrievalDetails[See Diagram 3<br/>Context Retrieval Flow]

    RetrievalDetails --> ContextGathered[Context Documents Retrieved<br/>Relevant Information]

    ContextGathered --> Step4Start[Step 4: Reranking<br/>Optional Context Refinement]

    Step4Start --> RerankerCheck{Reranker<br/>Enabled?}

    RerankerCheck -->|No| Step5Start
    RerankerCheck -->|Yes| RerankerService[Cohere Reranker<br/>or<br/>Jina Reranker]

    RerankerService --> RerankResult[Documents Scored & Sorted<br/>Top-K Selected]

    RerankResult --> Step5Start[Step 5: LLM Inference<br/>Generate Response]

    Step5Start --> PromptBuilder[Build Prompt Template<br/>System Message<br/>+ Context Documents<br/>+ Chat History<br/>+ User Query]

    PromptBuilder --> LLMSelection[Select LLM Provider<br/>Based on Config<br/>24+ Providers Available]

    LLMSelection --> LLMCall[Call LLM API<br/>Generate Response<br/>Stream or Non-Stream]

    LLMCall --> LLMResponse[LLM Response Generated]

    LLMResponse --> Step6Start[Step 6: Validation<br/>Post-Moderation]

    Step6Start --> PostModeration[Output Guardrails<br/>Safety Validation<br/>Content Filtering]

    PostModeration --> PostCheck{Response<br/>Safe?}

    PostCheck -->|No| Sanitize[Sanitize Response<br/>Remove Unsafe Content<br/>or Block Entirely]
    PostCheck -->|Yes| FinalResponse

    Sanitize --> FinalResponse[Final Response Ready]

    FinalResponse --> PipelineEnd([Pipeline Output<br/>Response + Metadata])

    BlockRequest --> PipelineEnd
```

**Step Latencies**:
- Step 1 (Safety): 50-200ms
- Step 2 (Language): 10-50ms
- Step 3 (Retrieval): 100-2000ms
- Step 4 (Reranking): 50-300ms
- Step 5 (LLM): 500-10,000ms (largest)
- Step 6 (Validation): 50-200ms

---

## Diagram 3: Context Retrieval Adapters

```mermaid
flowchart TD
    RetrievalStart([Step 3: Context Retrieval<br/>User Query]) --> AdapterConfig[Load Adapter Configuration<br/>config/adapters.yaml]

    AdapterConfig --> SelectAdapter{Select Retriever<br/>Adapter Type}

    SelectAdapter -->|Vector| VectorAdapter[Vector Adapter<br/>Semantic Search]
    SelectAdapter -->|SQL| SQLAdapter[SQL Adapter<br/>Database Queries]
    SelectAdapter -->|Graph| GraphAdapter[Graph Adapter<br/>Relationship Queries]
    SelectAdapter -->|Elastic| ElasticAdapter[Elasticsearch Adapter<br/>Full-Text Search]
    SelectAdapter -->|Hybrid| HybridAdapter[Hybrid Adapter<br/>Multi-Source Retrieval]
    SelectAdapter -->|Web| WebAdapter[Web Search Adapter<br/>Real-Time Info]
    SelectAdapter -->|Workflow| WorkflowAdapter[Workflow Adapter<br/>Custom Pipelines]

    VectorAdapter --> VectorDetails[Vector Store Options:<br/>• Chroma<br/>• Qdrant<br/>• Milvus<br/>• Pinecone<br/>• Weaviate]

    VectorDetails --> VectorEmbed[Embed Query<br/>Using Embedding Model<br/>28+ Options Available]

    VectorEmbed --> VectorSearch[Similarity Search<br/>Cosine/Euclidean Distance<br/>Top-K Results]

    VectorSearch --> VectorResults[Retrieved Documents]

    SQLAdapter --> SQLParser[Parse User Intent<br/>Generate SQL Query<br/>Schema Understanding]

    SQLParser --> SQLExecute[Execute SQL Query<br/>Against Database<br/>Dynamic Query Generation]

    SQLExecute --> SQLResults[Query Results<br/>Converted to Documents]

    GraphAdapter --> GraphOptions[Graph Database Options:<br/>• Neo4j<br/>• NetworkX<br/>• Graph Queries]

    GraphOptions --> GraphQuery[Relationship Traversal<br/>Pattern Matching<br/>Cypher/Graph Queries]

    GraphQuery --> GraphResults[Related Entities<br/>& Relationships]

    ElasticAdapter --> ElasticSearch[Elasticsearch Query<br/>Full-Text Search<br/>BM25 Ranking]

    ElasticSearch --> ElasticResults[Search Results<br/>Ranked by Relevance]

    HybridAdapter --> HybridStrategy[Combine Multiple Retrievers:<br/>• Vector + Keyword<br/>• SQL + Vector<br/>• Custom Combinations]

    HybridStrategy --> HybridFusion[Result Fusion<br/>Reciprocal Rank Fusion<br/>Score Normalization]

    HybridFusion --> HybridResults[Merged Results<br/>Best of Both Worlds]

    WebAdapter --> WebServices[Web Search Services:<br/>• Tavily API<br/>• SerpAPI<br/>• Google Search]

    WebServices --> WebFetch[Fetch Real-Time Info<br/>Web Scraping<br/>API Calls]

    WebFetch --> WebResults[Current Information<br/>Web Content]

    WorkflowAdapter --> WorkflowEngine[LangChain-Style Workflows<br/>Custom Processing<br/>Multi-Step Pipelines]

    WorkflowEngine --> WorkflowSteps[Execute Workflow:<br/>• Custom Logic<br/>• Tool Calls<br/>• Agent Actions]

    WorkflowSteps --> WorkflowResults[Workflow Output<br/>Processed Results]

    VectorResults --> EmbedLoad[Load Embedding Model<br/>config/embeddings.yaml]
    SQLResults --> EmbedLoad
    GraphResults --> EmbedLoad
    ElasticResults --> EmbedLoad
    HybridResults --> EmbedLoad
    WebResults --> EmbedLoad
    WorkflowResults --> EmbedLoad

    EmbedLoad --> EmbedOptions[Embedding Options:<br/>• OpenAI<br/>• Cohere<br/>• HuggingFace<br/>• Google<br/>• Voyage AI<br/>• Jina AI<br/>• Ollama Local<br/>• 20+ More Models]

    EmbedOptions --> ContextReady[Context Documents Ready<br/>Proceed to Step 4: Reranking]

    ContextReady --> RetrievalEnd([Return to Pipeline<br/>Context Retrieved])
```

**Adapter Locations**:
- Vector: `server/adapters/vector_adapter.py`
- SQL: `server/adapters/sql_adapter.py`
- Graph: `server/adapters/graph_adapter.py`
- Elastic: `server/adapters/elastic_adapter.py`
- Hybrid: `server/adapters/hybrid_adapter.py`
- Web: `server/adapters/web_adapter.py`
- Workflow: `server/adapters/workflow_adapter.py`

**Configuration**: `config/adapters.yaml`

---

## Export Instructions

### For High-Quality SVG (Recommended):
1. Visit https://mermaid.live
2. Copy each diagram's mermaid code
3. Click "Actions" → "Export SVG"
4. SVG files scale infinitely without pixelation

### For High-Resolution PNG:
Use mermaid-cli with increased dimensions:
```bash
# Install mermaid-cli first
npm install -g @mermaid-js/mermaid-cli

# Export each diagram
mmdc -i diagram.md -o diagram.png -w 3000 -H 4000 -b white
```

### PNG Export Settings:
- Width: 3000-4000px
- Height: 4000-6000px
- Background: white
- Scale: 2x or 3x for retina displays
