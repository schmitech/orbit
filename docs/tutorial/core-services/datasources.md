# Datasources

**Level 2 · Core AI Services**

[`config/datasources.yaml`](../../../config/datasources.yaml) holds connection details for 20+ backends — SQL databases, NoSQL stores, vector databases, and cloud query engines. Like `inference.yaml`, you only ever configure the entries your adapters actually use; everything else in the file can stay as shipped.

Datasources only matter to **retriever adapters** (QA, intent, file, composite). A pure passthrough/conversational adapter (`config/adapters/passthrough.yaml`) has `datasource: "none"` and never touches this file at all.

## Worked example: tracing `qa-sql` end to end

`config/adapters/qa.yaml` defines an adapter that answers questions from a local SQLite database:

```yaml
# config/adapters/qa.yaml
- name: "qa-sql"
  datasource: "sqlite"          # <- points at the "sqlite:" block below
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QASSQLRetriever"
  inference_provider: "llama_cpp"
```

`datasource: "sqlite"` is the link into `config/datasources.yaml`:

```yaml
# config/datasources.yaml
datasources:
  sqlite:
    database: "examples/sqlite/sqlite_db"
```

That's the entire connection — a path to a local file. Compare that to a networked database like Postgres, which needs credentials and pool settings instead of a file path:

```yaml
# config/datasources.yaml
datasources:
  postgres:
    host: ${DATASOURCE_POSTGRES_HOST}
    port: ${DATASOURCE_POSTGRES_PORT}
    database: ${DATASOURCE_POSTGRES_DATABASE}
    username: ${DATASOURCE_POSTGRES_USERNAME}
    password: ${DATASOURCE_POSTGRES_PASSWORD}
    use_connection_pool: true
    pool_size: 10
```

Same pattern every time: an adapter's `datasource:` field is a plain lookup key into a block here, and that block holds whatever connection info that backend type needs. Credentials are always referenced via `${DATASOURCE_..._ENV_VAR}`, never written as literal values in the file.

## Which datasource types need which settings

| Family | Examples | What you configure |
|---|---|---|
| **File-based / embedded** | `sqlite`, `duckdb` | A local file path — no network config, no credentials |
| **Relational (networked)** | `postgres`, `mysql`, `mariadb`, `sqlserver`, `oracle`, `supabase` | Host/port/database/username/password, plus a connection pool (`pool_size`, `connection_timeout`, `statement_timeout`) |
| **NoSQL** | `mongodb`, `cassandra`, `redis` | Connection string or host/credentials; MongoDB also supports an Atlas `connection_string` shortcut |
| **Vector stores** | `chroma`, `qdrant`, `milvus`, `pinecone`, `elasticsearch`, `redis` | Host/URL/API key, plus vector-specific settings like `dim`, `metric_type`, or `collection_name` |
| **Cloud query engines** | `athena` | AWS credentials/region plus an S3 staging location for query results |

## Which adapter families use which datasources

| Adapter family (see [Adapter Types](../adapter-types.md)) | Typical datasource |
|---|---|
| QA (SQL) | `sqlite`, `postgres`, `mysql` |
| QA (vector) | `chroma`, `qdrant` |
| Intent (SQL) | `postgres`, `mysql`, `duckdb` |
| Intent (NoSQL) | `mongodb`, `elasticsearch` |
| File | `none` in `datasources.yaml` — files are managed separately, indexed into a vector store referenced under `config:` (e.g. `vector_store: "chroma"`) |
| Passthrough / conversational | `none` — no datasource at all |

## Connection pooling, at a glance

Every networked SQL datasource shares the same pool settings: `use_connection_pool`, `pool_size`, `min_pool_size`, `connection_timeout`, `statement_timeout`, `validate_on_borrow`. Defaults (10 max connections, 5s connect timeout) work for most single-server deployments — raise `pool_size` if you're running multiple worker processes or expect high concurrent adapter traffic. See [Datasource Pooling](../../datasource-pooling.md) for the reference-counting details behind this.

---

Next: [Embeddings](embeddings.md) — how ORBIT turns text into vectors for the retrieval types above that need it.

[Core AI Services overview](overview.md) | [Tutorial home](../../tutorial.md)
