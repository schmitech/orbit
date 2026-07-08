# Example 2: Chat with Files

Let users upload PDFs, images, or audio and ask questions about them. The `simple-chat-with-files` adapter is pre-configured in `config/adapters/multimodal.yaml`:

```yaml
- name: "simple-chat-with-files"
  enabled: true
  type: "passthrough"
  adapter: "multimodal"
  implementation: "implementations.passthrough.multimodal.MultimodalImplementation"

  # Provider overrides (defaults shown — swap as needed)
  inference_provider: "openai"
  model: "gpt-5.4-mini"
  embedding_provider: "openai"
  embedding_model: "text-embedding-3-small"
  vision_provider: "gemini"           # For image files
  stt_provider: "whisper"             # Local speech-to-text for audio

  capabilities:
    retrieval_behavior: "conditional" # Retrieves only when files are attached
    supports_file_ids: true

  config:
    chunking_strategy: "recursive"
    chunk_size: 1000
    vector_store: "chroma"
    max_results: 10
    return_results: 10
```

### Create an API key

Open `http://localhost:3000/admin` and create a persona under **Prompts / Personas** with the prompt:

`You are a helpful assistant that answers questions about uploaded documents. Be accurate and cite specific content from the files.`

Then go to **API Keys** → **+ Create**:

1. Choose `simple-chat-with-files` as the adapter.
2. Name the key `Document Assistant`.
3. Select the persona you just created.
4. Save the key and copy the `orbit_…` value shown once.

### Try it

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
| Documents | PDF, DOCX, DOC, TXT, MD, HTML |
| Spreadsheets | XLSX, XLS, CSV |
| Data | JSON, XML |
| Images | PNG, JPEG, TIFF, GIF, WebP |
| Audio | WAV, MP3, OGG, FLAC, WebM, M4A |

---

[Tutorial home](../tutorial.md) | [Previous: Example 1: SQL Database (SQLite)](sql-database-sqlite.md) | [Next: Example 3: Vector Store Q&A](vector-store-qa.md)

---
