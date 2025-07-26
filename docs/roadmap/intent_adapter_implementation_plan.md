### **Objective**

Create a new `intent` retriever adapter that, like the `postgresql-rag` example, translates a user's natural language query into a precise SQL query, executes it, and returns the results. This involves understanding user intent, extracting parameters, and dynamically building the query.

### **Implementation Plan**

This plan is broken into four phases, from setting up the configuration to implementing the core logic.

---

#### **Phase 1: Configuration & Scaffolding**

This phase sets up the necessary files, directories, and configuration entries for the new adapter.

1.  **Define the Adapter in `config/adapters.yaml`**:
    Add a new entry for the `intent` adapter. This configuration will point to the new Python implementation and provide paths to domain-specific configuration files, drawing inspiration from `customer_order_domain.yaml` and `custom_templates.yaml`.

    ```yaml
    # In config/adapters.yaml
    - name: "intent-sql-postgres"
      type: "retriever"
      datasource: "postgres"
      adapter: "intent"
      implementation: "retrievers.implementations.intent.IntentPostgreSQLRetriever"
      config:
        # Path to the domain definition file
        domain_config_path: "examples/sandbox/postgresql-rag/customer_order_domain.yaml"
        # Path to the SQL template library
        template_library_path: "examples/sandbox/postgresql-rag/custom_templates.yaml"
        # Name for the in-memory vector store collection for templates
        template_collection_name: "intent_query_templates"
        confidence_threshold: 0.75
        # Fault tolerance settings can be copied from another adapter
        fault_tolerance:
          operation_timeout: 20.0
          failure_threshold: 5
          recovery_timeout: 45.0
          # ... etc.
    ```

2.  **Create New Directories**:
    -   `server/retrievers/implementations/intent/`
    -   `server/retrievers/adapters/intent/`

3.  **Create Initial Python Files**:
    -   `server/retrievers/implementations/intent/__init__.py`
    -   `server/retrievers/implementations/intent/intent_postgresql_retriever.py`
    -   `server/retrievers/adapters/intent/__init__.py`
    -   `server/retrievers/adapters/intent/intent_adapter.py`

---

#### **Phase 2: The Intent Adapter**

This component will manage the domain-specific knowledge required for the `intent` retriever to function.

1.  **Implement `IntentAdapter`**:
    -   **File**: `server/retrievers/adapters/intent/intent_adapter.py`
    -   **Class**: `IntentAdapter(DocumentAdapter)`
    -   **Responsibilities**:
        -   In its constructor, load the domain configuration (`.yaml`) and template library (`.yaml`) using the paths from the `config` section in `adapters.yaml`. The logic for this can be adapted from `domain_configuration.py` and `template_library.py`.
        -   Provide methods to access the loaded domain and template definitions.
        -   The `format_document` method will be used to format the final SQL results into a structured document for the user.

---

#### **Phase 3: The Intent Retriever (Core Logic)**

This is the main component that will perform the text-to-SQL processing. It will act as a "meta-retriever," orchestrating several services.

1.  **Implement `IntentPostgreSQLRetriever`**:
    -   **File**: `server/retrievers/implementations/intent/intent_postgresql_retriever.py`
    -   **Class**: `IntentPostgreSQLRetriever(AbstractSQLRetriever)`
    -   **Key Components**: This class will initialize and manage clients for:
        -   **PostgreSQL**: Inherited from `AbstractSQLRetriever` to execute the final query.
        -   **Embeddings**: To convert the user's query into a vector for semantic search. This will be initialized from `embeddings.yaml`.
        -   **Inference (LLM)**: For advanced parameter extraction from the user's query. This will be initialized from `inference.yaml`.
        -   **Vector Store**: An in-memory ChromaDB instance to store and search the SQL templates from the library.

2.  **Implement the `initialize` Method**:
    -   This method will be called once on startup.
    -   It will load the templates via the `IntentAdapter`, embed them using the embedding client, and populate the in-memory ChromaDB instance. This process is similar to `populate_chromadb_from_library` in `base_rag_system.py`.

3.  **Implement the `get_relevant_context` Method**:
    This method will contain the core text-to-SQL orchestration logic, adapted from `RAGSystem.process_query`:
    -   **Step 1: Find Best Template**: Embed the user's query and search the template vector store to find the most relevant SQL template.
    -   **Step 2: Extract Parameters**: Using the matched template's parameter definitions, create a prompt for the inference client (LLM) to extract the required values from the user's query. This is inspired by `DomainAwareParameterExtractor`.
    -   **Step 3: Build and Execute SQL**: Insert the extracted parameters into the `sql_template` from the matched template to form the final SQL query. Execute this query against the PostgreSQL database.
    -   **Step 4: Format and Return Results**: The results from the SQL query are the "context." Use the `IntentAdapter` to format these results into a clean list of documents to be returned. You can also use the inference client here to generate a natural language summary of the results, as seen in `DomainAwareResponseGenerator`.

---

#### **Phase 4: System Integration**

The final step is to register the new components with the application's factories.

1.  **Register the Adapter**:
    -   In `server/retrievers/adapters/registry.py`, register the new `IntentAdapter` so the system can create it.

2.  **Register the Retriever**:
    -   In `server/retrievers/__init__.py`, import the new `IntentPostgreSQLRetriever` to make it available to the `RetrieverFactory`.

This plan provides a clear path to integrate the powerful intent-based retrieval logic from your sandbox into the main application architecture, ensuring it leverages the existing configuration for services like inference and embeddings.
