# Example 2: Chat with Files

**Level 1 · Foundations**

This is the Multimodal adapter type from [Adapter Types](adapter-types.md) — conversational chat that conditionally retrieves from files only when one is attached. Let users upload PDFs, images, or audio and ask questions about them. The `simple-chat-with-files` adapter is pre-configured in `config/adapters/multimodal.yaml`:

```yaml
- name: "simple-chat-with-files"
  enabled: true
  type: "passthrough"
  adapter: "multimodal"
  implementation: "implementations.passthrough.multimodal.MultimodalImplementation"

  # Provider overrides (these are the current defaults for this adapter)
  inference_provider: "openai"
  model: "gpt-5.4-mini"
  embedding_provider: "cohere"
  embedding_model: "embed-v4.0"
  vision_provider: "cohere"            # For image files
  stt_provider: "openrouter"           # For audio transcription
  tts_provider: "gemini"               # For audio responses

  capabilities:
    retrieval_behavior: "conditional"  # Retrieves only when files are attached
    supports_file_ids: true
    supports_session_tracking: true
    supports_charts: true               # Useful for CSV/XLSX questions
    auto_skill_routing: true            # Per-adapter opt-in for automatic routing
    auto_routable_skills: [Image, Video, PDF, Word, CSV, Excel, PowerPoint, web-search, Markdown]
    available_skills: [Image, Video, Audio, PDF, Word, CSV, Excel, PowerPoint, web-search, Markdown, Fetch, HR, business-analytics, customer-orders]
    mcp_tools: true                     # Optional tool calling when MCP is configured

  config:
    chunking_strategy: "recursive"
    chunk_size: 1000
    chunk_overlap: 100
    vector_store: "chroma"
    collection_prefix: "files_"
    confidence_threshold: 0.3
    max_file_size: 52428800             # 50MB
    max_results: 10
    return_results: 10
```

`simple-chat-with-files` is enabled by default. It uses conditional retrieval: a
normal message goes directly to the LLM, while a message associated with uploaded
files retrieves relevant chunks first. The adapter validates file ownership using
the API key and tracks the session for conversation-level file context. CSV and
similar structured data can use the DuckDB path; documents, images, and audio use
the vector-search path.

The same config also enables explicit skills (such as `Image`, `PDF`, and `Excel`)
and automatic skill routing when the global skill-routing switch is enabled. The
separate `simple-chat-with-files-audio` adapter includes audio transcription
settings and supports larger files, but is disabled by default; enable it in
[`config/adapters/multimodal.yaml`](../../config/adapters/multimodal.yaml) if you
want a dedicated audio-focused adapter.

### Adjust file settings

The full install-time baseline is [`install/default-config/config.yaml`](../../install/default-config/config.yaml).
During installation it is copied into the active `config/` directory; for an
existing installation, edit [`config/config.yaml`](../../config/config.yaml), not
the template, and restart ORBIT after changing settings.

Global file settings belong under `files:` and apply to all file adapters unless
an adapter overrides them in `config/adapters/multimodal.yaml`:

```yaml
files:
  storage_backend: "filesystem"       # filesystem, s3, minio, azure, or gcs
  storage_root: "./uploads"
  default_chunking_strategy: "recursive"
  default_chunk_size: 2048
  default_chunk_overlap: 200
  processing:
    docling_enabled: false             # use local format-specific processors
    markitdown_enabled: true
    ai_document_enabled: false
    processor_priority: "markitdown"
```

Use the adapter’s `config:` block for file-specific overrides such as
`max_file_size`, `chunk_size`, `chunk_overlap`, `confidence_threshold`,
`max_results`, and `return_results`. The global `files.storage_backend` is the
authoritative storage choice; the adapter-level `storage_backend` documents the
same setting but does not select a different backend for that adapter.

Keep `docling_enabled: false` for a lightweight, offline-friendly setup; ORBIT
then falls back to processors such as pypdf, python-docx, openpyxl, pandas, and
BeautifulSoup. Enable Docling when you need its stronger layout understanding,
OCR, table extraction, or document processing behavior. Images and audio still
use the configured vision and speech providers. See the [File Adapter System
Guide](../adapters/file-adapter-guide.md) for storage backends, processor
selection, encryption, and troubleshooting.

### Optional: automatic skill routing

The adapter can infer a skill from an ordinary sentence, so a client does not
need to send a `skill` field or use OrbitChat's `/` picker. For example, phrases
such as `create a PDF of this conversation`, `turn this into an Excel file`, or
`search the web for the latest release` can be routed to the matching skill.

This feature is deliberately opt-in and needs two switches:

```yaml
# config/config.yaml (global gate; off by default)
skill_routing:
  auto_detect: true
  embedding_threshold: 0.35
  max_candidates: 3
  history_turns: 4
  router_provider: "openai"
  router_model: "gpt-5.4-mini"

# config/adapters/multimodal.yaml (consumer adapter)
capabilities:
  auto_skill_routing: true
  auto_routable_skills:
    - "PDF"
    - "Image"
    - "Excel"
    - "PowerPoint"
    - "web-search"
```

The global `skill_routing.auto_detect` switch and the adapter’s
`capabilities.auto_skill_routing` must both be `true`. The adapter’s
`auto_routable_skills` list limits what may be selected automatically; when it
is omitted, ORBIT falls back to `available_skills`. The target skill adapter
must also be enabled and imported in `config/adapters.yaml`—for example, the
PDF generator must expose the skill name `PDF` and have routing examples such as
`make a pdf` or `turn this into a pdf`.

Automatic routing adds an embedding check on opted-in turns and invokes a small
confirmation-model call only when a candidate matches. It is fail-safe: a
no-match or routing error continues as normal chat. An explicit `/` picker
selection or `skill` field takes precedence, and skill routing runs before
opportunistic MCP tool calling. See [Skills: Automatic Intent Detection](../adapters/skills.md#automatic-intent-detection)
for the complete behavior and tuning options.

To validate it without OrbitChat, use a normal chat request with no `skill`
field:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_YOUR_KEY' \
  -H 'X-Session-ID: skill-routing-example' \
  -d '{"messages":[{"role":"user","content":"Create a PDF summarizing this conversation"}],"stream":false}'
```

When the PDF skill is enabled and the router selects it, the response includes
the generated document fields, such as `document` and `document_format: "pdf"`.

### Create an API key

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** with the prompt:

`You are a helpful assistant that answers questions about uploaded documents. Be accurate and cite specific content from the files.`

Then go to **API Keys** → **+ Create**:

1. Choose `simple-chat-with-files` as the adapter.
2. Name the key `Document Assistant`.
3. Select the persona you just created.
4. Save the key and copy the `orbit_…` value shown once.

<!-- MEDIA: screenshot | chat-with-files/upload-and-ask | Chat window with a PDF attached and a question answered from its contents -->
> 🖼️ **Screenshot placeholder:** a file attached in chat with a grounded answer.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### Try it with the API

The web client uploads files through the same API. You can test the complete flow
with `curl` by uploading a file first, then passing the returned `file_id` to
`/v1/chat`:

```bash
curl -X POST http://localhost:3000/api/files/upload \
  -H 'X-API-Key: orbit_YOUR_KEY' \
  -F 'file=@document.pdf'
```

Copy the `file_id` from the response, then ask a question about that file:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_YOUR_KEY' \
  -H 'X-Session-ID: files-example' \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize this document and cite its key sections."}
    ],
    "file_ids": ["FILE_ID_FROM_UPLOAD"],
    "stream": false
  }'
```

The upload response should reach `completed` before querying. For lower-level
file retrieval without an LLM response, see the [file query endpoint](../adapters/file-adapter-guide.md#query-file).

### Try it with OrbitChat

1. Open the web chat (React app or embedded widget).
2. Attach a PDF, DOCX, image, or audio file.
3. Ask:
   - "Summarize this document"
   - "What are the key points in section 3?"
   - "What does the chart on page 2 show?" (images)
   - "Transcribe and summarize this audio file" (audio)

Retrieval only fires when there's a file attached — regular messages go straight to the LLM, keeping costs and latency down.

### Supported file types

| Category | Formats |
|:---|:---|
| Documents | PDF, DOCX, DOC, PPTX, TXT, MD, HTML, VTT |
| Spreadsheets | XLSX, XLS, CSV, Parquet |
| Data | JSON, XML |
| Images | PNG, JPEG, TIFF, GIF, WebP |
| Audio | WAV, MP3, OGG, FLAC, WebM, M4A |

---

[Tutorial home](../tutorial.md) | [Previous: Example 1: SQL Database (SQLite)](sql-database-sqlite.md) | [Next: Example 3: Vector Store Q&A](vector-store-qa.md)

---
