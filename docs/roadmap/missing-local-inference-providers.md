# Missing Local Inference Providers

This document tracks local inference tools that are not yet implemented in ORBIT but could be valuable additions.

## Currently Supported Local Inference Tools

- ✅ **Ollama** - Local/Cloud inference server
- ✅ **llama.cpp** - Direct mode and API mode
- ✅ **vLLM** - High-performance local inference
- ✅ **Shimmy** - Lightweight Rust-based OpenAI-compatible server
- ✅ **BitNet** - Direct mode and API mode
- ✅ **Hugging Face** - Local model inference (transformers)

---

## Missing Local Inference Providers

### High Priority

#### 1. LocalAI
**Status:** Not implemented  
**Type:** OpenAI-compatible local inference server  
**Priority:** High  
**Difficulty:** Easy (OpenAI-compatible)

**Description:**
- OpenAI-compatible local inference server
- Supports multiple backends (llama.cpp, gpt4all, etc.)
- Self-hosted, on-premise deployment
- Automatic GPU backend detection
- Supports LLMs, TTS, and other models locally

**Implementation Notes:**
- Can reuse `OpenAICompatibleBaseService` (similar to Shimmy)
- Default port: `http://localhost:8080` (configurable)
- No API key required (or optional)
- Should be straightforward since it's OpenAI-compatible

**Resources:**
- GitHub: https://github.com/mudler/LocalAI
- Documentation: https://localai.io/

**Configuration Example:**
```yaml
localai:
  enabled: false
  base_url: "http://localhost:8080"  # LocalAI server URL
  model: "gpt-3.5-turbo"  # Model name configured in LocalAI
  api_key: null  # Optional - LocalAI doesn't require authentication by default
  # ... standard OpenAI-compatible parameters
```

---

#### 2. LM Studio
**Status:** Not implemented  
**Type:** Desktop app with OpenAI-compatible local server  
**Priority:** High  
**Difficulty:** Easy (OpenAI-compatible)

**Description:**
- Desktop application for running LLMs locally
- Provides OpenAI-compatible local server
- User-friendly interface
- Very popular among developers and researchers
- Supports various model formats (GGUF, etc.)

**Implementation Notes:**
- Can reuse `OpenAICompatibleBaseService` (similar to Shimmy)
- Default port: `http://localhost:1234` (configurable in LM Studio)
- No API key required
- Users need to start LM Studio server manually

**Resources:**
- Website: https://lmstudio.ai/
- GitHub: https://github.com/lmstudio-ai/lmstudio

**Configuration Example:**
```yaml
lm_studio:
  enabled: false
  base_url: "http://localhost:1234"  # LM Studio server URL (default port)
  model: null  # Model is selected in LM Studio UI
  api_key: null  # Optional - LM Studio doesn't require authentication
  # ... standard OpenAI-compatible parameters
```

---

### Medium Priority

#### 3. FastChat
**Status:** Not implemented  
**Type:** Open-source framework with OpenAI-compatible API  
**Priority:** Medium  
**Difficulty:** Easy (OpenAI-compatible)

**Description:**
- Open-source framework by LMSYS (behind Chatbot Arena)
- Provides OpenAI-compatible API
- Good for serving and comparing models
- Supports various model architectures
- Used by Chatbot Arena for LLM comparisons

**Implementation Notes:**
- Can reuse `OpenAICompatibleBaseService`
- Default port: `http://localhost:8000` (configurable)
- Requires FastChat server to be running
- Supports controller, worker, and gradio web server modes

**Resources:**
- GitHub: https://github.com/lm-sys/FastChat
- Documentation: https://github.com/lm-sys/FastChat#api

**Configuration Example:**
```yaml
fastchat:
  enabled: false
  base_url: "http://localhost:8000"  # FastChat server URL
  model: null  # Model is configured when starting FastChat server
  api_key: null  # Optional
  # ... standard OpenAI-compatible parameters
```

---

#### 4. GPT4All
**Status:** Not implemented  
**Type:** Local LLM runner  
**Priority:** Medium  
**Difficulty:** Medium (may need custom integration)

**Description:**
- Popular local LLM runner
- Supports various model formats
- Cross-platform (Windows, macOS, Linux)
- May be compatible via LocalAI or need custom integration

**Implementation Notes:**
- Check if GPT4All provides OpenAI-compatible API
- If not, may need custom integration
- Could potentially be supported via LocalAI backend

**Resources:**
- Website: https://gpt4all.io/
- GitHub: https://github.com/nomic-ai/gpt4all

**Configuration Example:**
```yaml
gpt4all:
  enabled: false
  # TBD - depends on API compatibility
```

---

### Low Priority

#### 5. KoboldAI
**Status:** Not implemented  
**Type:** Lightweight platform for local LLMs  
**Priority:** Low  
**Difficulty:** Medium (not fully OpenAI-compatible)

**Description:**
- Lightweight platform for running LLMs locally
- Focused on interactive fiction and creative writing
- Supports various backends
- May not be fully OpenAI-compatible

**Implementation Notes:**
- Check API compatibility
- May need custom integration if not OpenAI-compatible
- Less critical for general-purpose use cases

**Resources:**
- GitHub: https://github.com/KoboldAI/KoboldAI-Client
- Website: https://koboldai.org/

**Configuration Example:**
```yaml
koboldai:
  enabled: false
  # TBD - depends on API compatibility
```

---

#### 6. AMD Gaia
**Status:** Not implemented  
**Type:** AMD's open-source LLM project  
**Priority:** Low  
**Difficulty:** Medium (Windows-focused, ONNX-based)

**Description:**
- AMD's open-source project for running LLMs locally
- Windows-focused (uses ONNX TurnkeyML)
- Supports AMD Ryzen AI processors
- Newer, less established than other options

**Implementation Notes:**
- Windows-specific (may limit adoption)
- Uses ONNX runtime
- Check if it provides API interface
- Lower priority due to platform limitations

**Resources:**
- GitHub: https://github.com/amd/gaia (if available)
- AMD announcement: Check AMD's official channels

**Configuration Example:**
```yaml
amd_gaia:
  enabled: false
  # TBD - depends on API availability and platform support
```

---

## Implementation Strategy

### Phase 1: High Priority (Easy Wins)
1. **LocalAI** - Reuse `OpenAICompatibleBaseService`, similar to Shimmy
2. **LM Studio** - Reuse `OpenAICompatibleBaseService`, similar to Shimmy

### Phase 2: Medium Priority
3. **FastChat** - Reuse `OpenAICompatibleBaseService` if API is compatible
4. **GPT4All** - Evaluate API compatibility, may need custom integration

### Phase 3: Low Priority
5. **KoboldAI** - Evaluate API compatibility
6. **AMD Gaia** - Evaluate platform support and API availability

## Implementation Template

For OpenAI-compatible providers (LocalAI, LM Studio, FastChat), follow the Shimmy implementation pattern:

1. **Create Base Service** (if needed)
   - File: `server/ai_services/providers/{provider}_base.py`
   - Extend `OpenAICompatibleBaseService` or `ProviderAIService`

2. **Create Inference Service**
   - File: `server/ai_services/implementations/{provider}_inference_service.py`
   - Extend `InferenceService` and base service
   - Implement `generate()` and `generate_stream()` methods

3. **Update Exports**
   - `server/ai_services/providers/__init__.py`
   - `server/ai_services/implementations/__init__.py`

4. **Register Service**
   - `server/ai_services/registry.py`
   - Add to `register_inference_services()`

5. **Add Configuration**
   - `config/inference.yaml`
   - `install/default-config/inference.yaml`

6. **Update Documentation**
   - Add to README.md provider table
   - Create setup guide if needed

## Notes

- All OpenAI-compatible providers can leverage existing `OpenAICompatibleBaseService`
- Default ports should be configurable
- Consider adding retry logic for local servers that may need warmup time
- Test with various model configurations
- Document any provider-specific limitations or requirements

---

**Last Updated:** 2025-11-29  
**Status:** Tracking document for future implementation

