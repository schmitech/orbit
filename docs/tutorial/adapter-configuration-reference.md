# Adapter Configuration Reference

This page is a field-by-field cheatsheet for a single adapter entry. For how to split adapters across multiple files, `import` them into `config.yaml`, and override models per API key, see [Adapter Configuration Management](../adapters/adapter-configuration.md).

> **Tip: generate adapters instead of hand-writing them.** The Adapter SDK scaffolds valid config files for the template-like families — document/media generators, passthrough, `fetch`, `mcp-agent`, and web-search — writes them to `config/adapters/`, and registers them so ORBIT loads them. Run it from anywhere:
>
> ```bash
> bin/adapter-sdk.sh --list                          # see which families it can generate
> bin/adapter-sdk.sh                                  # interactive wizard
> bin/adapter-sdk.sh --spec doc-generator --dry-run   # preview a config without writing
> ```
>
> It picks the interdependent `type`/`datasource`/`adapter`/`implementation` values for you and can optionally use an LLM to draft the skill description and routing phrases. Intent × datasource adapters (the config shown below) are still authored by hand for now. See [server/adapter_sdk/README.md](../../server/adapter_sdk/README.md).

Every adapter accepts these shared fields:

```yaml
- name: "adapter-name"
  enabled: true                  # Toggle the adapter on/off (live-reloadable from admin)
  type: "retriever"              # "retriever" or "passthrough"

  # Provider overrides (optional — falls back to config/*.yaml defaults)
  inference_provider: "ollama"
  model: "llama3:8b"
  embedding_provider: "openai"
  reranker_provider: "cohere"

  capabilities:
    retrieval_behavior: "always" # "none", "always", or "conditional"
    formatting_style: "standard" # "standard" or "clean"
    supports_file_ids: false
    supports_threading: true

  fault_tolerance:
    operation_timeout: 30.0
    failure_threshold: 5
    max_retries: 3
```

Intent adapters add:

```yaml
config:
  domain_config_path: "path/to/domain.yaml"
  template_library_path:
    - "path/to/templates.yaml"
  template_collection_name: "my_templates"
  store_name: "chroma"           # Vector store used for template matching
  confidence_threshold: 0.4
  max_templates: 5
  return_results: 100
  reload_templates_on_start: true
  force_reload_templates: false
```

---

[Tutorial home](../tutorial.md) | [Previous: Connecting Your Own Data](connecting-your-own-data.md) | [Next: Troubleshooting](troubleshooting.md)

---
