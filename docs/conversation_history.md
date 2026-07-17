# Conversation History System

Orbit includes a conversation history system that automatically adapts to your chosen AI model's capabilities. This system maintains context across conversations while optimally utilizing available memory.

## Table of Contents

- [What is a Token?](#what-is-a-token)
- [Overview](#overview)
- [How It Works](#how-it-works)
- [Rolling Window Memory](#rolling-window-memory)
  - [Automatic Cleanup Mechanism](#-automatic-cleanup-mechanism)
- [Dynamic Token Budget](#dynamic-token-budget)
- [Provider-Specific Behavior](#provider-specific-behavior)
- [Per-Adapter and Per-Request Overrides](#per-adapter-and-per-request-overrides)
- [Configuration](#configuration)
- [Examples](#examples)
- [Technical Details](#technical-details)
  - [Thread Safety](#thread-safety)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
- [Conversation Limit Warnings](#conversation-limit-warnings)

## Overview

The conversation history system provides:

- **Automatic Context Management**: Maintains conversation context without manual tuning
- **Token-Based Memory**: Dynamically calculates optimal token budget based on your AI model
- **Provider Awareness**: Adapts to different inference providers (llama.cpp, Ollama, OpenAI, etc.)
- **Efficient Resource Utilization**: Uses available context window efficiently via rolling window queries
- **Rolling Window Queries**: Automatically selects recent messages that fit within token budget
- **🗑️ Automatic Cleanup**: Deletes old messages when session exceeds token budget threshold
- **⚠️ Proactive Warnings**: Alerts users when conversation approaches token budget limits
- **🔒 Thread-Safe**: Per-session locking ensures safe concurrent access

### Key Benefits

1. **No Manual Configuration**: The system automatically determines the best settings
2. **Model-Optimized**: Adapts to each model's context window size
3. **Memory Efficient**: Prevents context overflow while maximizing conversation length
4. **Storage Efficient**: Automatically cleans up old messages to save database space
5. **Provider Agnostic**: Works seamlessly across all supported inference providers
6. **🔔 User-Friendly Warnings**: Get notified before messages are deleted

## How It Works

### The Challenge

Different AI models have vastly different context window sizes:

- **Small models** (like TinyLLama): ~1,024 tokens
- **Medium models** (like Llama 3 8B): ~8,192 tokens  
- **Large models** (like GPT-4): ~32,768+ tokens
- **Massive models** (like Claude 3): ~200,000 tokens

A fixed conversation limit doesn't make sense across this range.

### What is a Token?

A **token** is the basic unit of text that AI models process. Tokens are not the same as words or characters:

- **Words**: "Hello world" = 2 words
- **Tokens**: "Hello world" ≈ 2-3 tokens (varies by tokenizer)
- **Characters**: "Hello world" = 11 characters

Tokens are created by breaking text into smaller pieces that the model understands. For example:
- Short words like "the" or "cat" are usually 1 token each
- Longer words might be split into multiple tokens
- Punctuation and spaces also count as tokens

**Why tokens matter**: AI models have limits on how many tokens they can process at once (their "context window"). The conversation history system uses token counts to ensure conversations stay within these limits, automatically selecting the most recent messages that fit within the available token budget.

### The Solution

The system **dynamically calculates** the optimal token budget for conversation history based on:

1. **Active inference provider** configuration
2. **Model's context window size**
3. **Reserved space** for system prompts and current queries

### The Calculation Process

```
Token Budget = Context Window - Reserved Tokens
Reserved Tokens = Model's Max Output Tokens + 700
```

Where:
- **Model's Max Output Tokens**: the provider's configured `max_tokens` (or `num_predict` for Ollama) — how many tokens the model is allowed to generate in its response. Defaults to **1,024** if not explicitly configured for that provider.
- **700**: fixed overhead for the system prompt (~500 tokens) + current query buffer (~200 tokens)
- **Safety Bounds**: Minimum 100 tokens, maximum 800,000 tokens

Because the reserved amount includes the model's own output budget, a provider configured for long responses (e.g. `max_tokens: 16000`) reserves noticeably more than one left at the default 1,024 — the same context window yields a smaller history budget for the former.

The system then uses a **rolling window query** to select messages that fit within this token budget, starting from the most recent messages and working backwards until the budget is reached.

## Rolling Window Memory

### 🔄 How Memory Actually Works

**IMPORTANT**: The system uses a **token-based rolling window** approach with **automatic cleanup**. Messages that fit within the token budget are included in context, and old messages that exceed the budget are automatically deleted from the database.

### ❌ **What It Does NOT Do** (Common Misconception):
```
Conversation: [1,2,3,4,5,6,7,8,9,10] → DELETE ALL → Start fresh from 0
```

### ✅ **What It Actually Does** (Rolling Window with Cleanup):
```
Messages in DB: [1,2,3,4,5,6,7,8,9,10,11,12]
Token budget: 1000 tokens
Context query: [7,8,9,10,11,12]  ← Messages that fit in token budget
Cleanup (at 120%): [1,2,3,4,5,6] ← Old messages deleted from database
After cleanup: [7,8,9,10,11,12]  ← Only recent messages remain
```

**The AI remembers information based on recency and token usage, not arbitrary cutoffs:**

#### **Information Gets Remembered When:**
- ✅ **Recently discussed**: "What's my name?" → AI recalls because it's in recent token window
- ✅ **Frequently reinforced**: Topics you keep bringing up stay accessible
- ✅ **Context-relevant**: Information that connects to recent conversations
- ✅ **Within token budget**: Messages that fit within the available token budget

#### **Information Gets Deleted When:**
- ❌ **Old and unreferenced**: Early topics not mentioned recently are deleted when budget is exceeded
- ❌ **No recent reinforcement**: Details from beginning that haven't come up again
- ❌ **Outside token window**: Messages exceeding 120% of token budget are permanently removed

### 📊 **Real Example Scenarios**

#### **Scenario 1: Name Memory** (Why it persists)
```
Message 1:  "Hi, I'm Sarah"                    → [Outside token budget]
Message 15: "What's my name?"                  → [In token window]
Message 16: "Your name is Sarah"               → [In token window]
Message 25: "What's my name again?"            → [In token window]  
Message 26: "Your name is Sarah"               → [In token window]

Result: AI remembers "Sarah" because recent exchanges are within token budget
```

#### **Scenario 2: Early Details** (Why they're deleted)
```
Message 2:  "I work at Microsoft"              → [Deleted when budget exceeded]
Message 3:  "I have a dog named Buddy"         → [Deleted when budget exceeded]
[... 20 messages about other topics ...]
Message 25: "Where do I work?"                 → [Recent, but early messages gone]
Message 26: "I don't see that information     → [Messages were deleted from
             in our recent conversation"           the database]

Result: AI can't access early details because they were permanently deleted
```

#### **Scenario 3: Natural Conversation Flow**
```
Messages 1-5:   Discuss weekend plans          → [Deleted at cleanup]
Messages 6-10:  Talk about work projects       → [Deleted at cleanup]
Messages 11-15: Conversation about cooking     → [May be deleted at cleanup]
Messages 16-20: Return to work discussion      → [In token window, retained]
Messages 21-25: More work-related topics       → [In token window, retained]

Result: AI remembers recent work discussion, weekend plans permanently deleted
```

### 🔍 **Testing Memory Behavior**

To verify the rolling window works correctly, try:

#### **Test Deleted Information:**
- Ask about topics from your **first few messages** that you haven't mentioned recently
- Example: "What was the first thing I told you about myself?"
- **Expected**: AI won't remember because those messages were deleted from the database

#### **Test Remembered Information:**
- Ask about topics you've discussed **recently or repeatedly**
- Example: "What's my name?" (if asked multiple times recently)
- **Expected**: AI remembers because those messages are within the token budget and retained

### 🚀 **Why This Design is Optimal**

1. **🧠 Natural Conversation Flow**: Like human memory, recent topics stay accessible
2. **⚡ Optimal Performance**: Always uses maximum available context efficiently
3. **🔄 Continuous Context**: No jarring "memory wipes" that break conversation flow
4. **🎯 Relevance-Based**: Important information naturally stays through reinforcement
5. **📈 Scalable**: Works identically across tiny to massive models
6. **💾 Storage Efficient**: Old messages are automatically cleaned up to save database space
7. **🔒 Thread-Safe**: Per-session locking prevents race conditions during cleanup

### 🔧 **How Rolling Window Query Works**

**Query happens BEFORE each new conversation turn:**

```
1. User asks question
2. System calculates: "What messages fit in token budget?"
3. Query fetches messages from newest to oldest
4. Accumulates tokens until budget reached
5. Returns messages in chronological order (oldest to newest)
6. Generate response using context within token budget
7. Store new user question + AI response
8. Cleanup triggered if session exceeds 120% of token budget
```

**This ensures:**
- ✅ **Fresh context**: AI always sees most relevant recent messages within token budget
- ✅ **No overflow**: Context never exceeds model limits
- ✅ **Smooth experience**: No mid-conversation memory loss
- ✅ **Automatic cleanup**: Old messages deleted when budget is significantly exceeded

### 🗑️ **Automatic Cleanup Mechanism**

**Cleanup triggers when session exceeds 120% of token budget:**

```
Token budget: 6,468 tokens (Ollama, num_ctx=8192, default max_tokens)
Cleanup threshold: 7,761 tokens (120% of budget)

Session at 7,000 tokens → No cleanup (under 120%)
Session at 8,500 tokens → Cleanup triggered
    ↓
Delete oldest messages until session fits within budget
    ↓
Session now at ~6,400 tokens
```

**Cleanup behavior:**
- **Threshold**: 120% of token budget (prevents cleanup on every message)
- **Warning**: Users warned at 90% before cleanup occurs
- **Thread-safe**: Per-session locking prevents race conditions
- **Non-blocking**: Cleanup happens asynchronously after storing messages
- **Permanent**: Deleted messages cannot be recovered
- **Model-aware**: the threshold used is the budget for whichever adapter/model handled *that turn* (see [Per-Adapter and Per-Request Overrides](#per-adapter-and-per-request-overrides)) — switching to a model with a smaller context window can trigger deletion of messages that were stored under a larger budget, not just omit them from that turn's prompt

## Dynamic Token Budget

### Automatic Calculation

The system examines your active inference provider configuration and extracts the context window size to calculate a token budget:

| Provider | Primary Parameter | Universal Parameter | Typical Range |
|----------|------------------|-------------------|---------------|
| llama.cpp, BitNet | `n_ctx` | `context_window` | 1,024 - 8,192 |
| Ollama (local, cloud, remote) | `num_ctx` | `context_window` | 2,048 - 32,768 |
| vLLM, TensorRT-LLM | `max_model_len` | `context_window` | 4,096 - 32,768 |
| OpenAI | `context_window` | `max_context_length` | 8,192 - 128,000+ |
| Anthropic | `context_window` | `max_context_length` | 100,000 - 200,000+ |
| Gemini | `context_window` | `max_context_length` | 32,768 - 1,000,000+ |
| Groq | `context_window` | `max_context_length` | 8,192 - 32,768 |
| DeepSeek | `context_window` | `max_context_length` | 16,384 - 32,768 |
| HuggingFace | `max_length` | `context_window` | 512 - 4,096 |
| Others | `context_window` | `max_context_length` | Varies |

All figures below assume the provider's `max_tokens`/`num_predict` (output token reservation) is left at its default of 1,024 — see [The Calculation Process](#how-it-works) for how a larger configured output budget reduces these numbers.

### Example Calculations

**Small Model (llama.cpp with n_ctx: 1,024)**:
```
Token Budget: 1,024 - (1,024 + 700) = 0 → clamped to safety minimum
Safety Minimum: 100 tokens (applied)
Result: 100 tokens available for conversation history
```
A context window this small is mostly consumed by the reserved system prompt and
output budget — there's effectively no room left for history. In practice, models
this small should configure a much smaller `max_tokens`/`num_predict` to leave any
usable budget.

**Medium Model (Ollama with num_ctx: 8,192)**:
```
Token Budget: 8,192 - (1,024 + 700) = 6,468 tokens
Result: 6,468 tokens available for conversation history
```

**Large Model (OpenAI with ~32K context)**:
```
Token Budget: 32,768 - (1,024 + 700) = 31,044 tokens
Result: 31,044 tokens available for conversation history
```

The system then uses a rolling window query to select messages that fit within this token budget, starting from the most recent messages.

## Provider-Specific Behavior

### Local Models (llama.cpp, Ollama)

**Configuration Detection**: Reads context window directly from config
```yaml
inference:
  llama_cpp:
    n_ctx: 4096  # ← System reads this value
  ollama:
    num_ctx: 8192  # ← System reads this value
```

**Typical Results** (default `max_tokens`/`num_predict` of 1,024):
- 1K context → 100 tokens available (safety minimum enforced)
- 4K context → 2,372 tokens available
- 8K context → 6,468 tokens available

### Cloud APIs (OpenAI, Anthropic, etc.)

**Configuration-First Detection**: Now reads from actual provider configuration when available
```yaml
inference:
  openai:
    model: "gpt-4o"
    context_window: 64000  # ← System reads this value first
    
  anthropic:
    model: "claude-3-sonnet"
    context_window: 100000  # ← Custom override for this model
    
  gemini:
    model: "gemini-1.5-pro"
    context_window: 48000   # ← Override provider default
```

**Fallbacks**: Uses conservative built-in defaults when `context_window` isn't configured for that provider (default `max_tokens`/`num_predict` of 1,024 assumed)
- OpenAI: 128,000 tokens → 126,276 token budget
- Anthropic: 200,000 tokens → 198,276 token budget
- Groq: 131,072 tokens → 129,348 token budget

### Universal Configuration

**All Providers Support Context Window Configuration**:
```yaml
inference:
  # Local providers (existing behavior)
  ollama:
    num_ctx: 16384      # Ollama-specific parameter
  llama_cpp:
    n_ctx: 8192         # llama.cpp-specific parameter
    
  # Cloud providers (enhanced - now configurable!)  
  openai:
    context_window: 64000    # Universal parameter
  anthropic:
    context_window: 100000   # Universal parameter
  gemini:
    context_window: 48000    # Universal parameter
  groq:
    context_window: 8192     # Universal parameter
  deepseek:
    context_window: 16384    # Universal parameter
  together:
    context_window: 8192     # Universal parameter
  xai:
    context_window: 32768    # Universal parameter
  azure:
    context_window: 32768    # Universal parameter
  vertex:
    context_window: 48000    # Universal parameter
  aws:
    context_window: 8192     # Universal parameter
  mistral:
    context_window: 16384    # Universal parameter
  openrouter:
    context_window: 200000   # Universal parameter
    
  # HuggingFace uses its own parameter
  huggingface:
    max_length: 4096         # HuggingFace-specific parameter
```

### Detection Priority

The system uses a **three-tier detection strategy**:

1. **Primary Parameter**: Provider-specific parameter (e.g., `num_ctx` for Ollama, `n_ctx` for llama.cpp)
2. **Universal Parameter**: `context_window` for all cloud providers  
3. **Fallback Defaults**: Conservative estimates when no configuration is found

**Example Detection Flow**:
```yaml
# OpenAI provider detection priority:
openai:
  context_window: 64000        # ← 1st priority: Universal parameter
  max_context_length: 60000    # ← 2nd priority: Alternative parameter
  # No config found?           # ← 3rd priority: Default (128,000 tokens)
```

### Fallback Behavior

**For unknown providers or missing configuration**:
- **Default context window**: 4,096 tokens
- **Resulting token budget**: 2,372 tokens
- **Graceful degradation**: System continues working with reasonable defaults
- **Verbose logging**: Shows which defaults are being used

**Benefits of Enhanced Detection**:
- ✅ **Consistent behavior** across all providers
- ✅ **User control** over context windows for any provider
- ✅ **Defaults** when configuration is missing
- ✅ **No breaking changes** to existing configurations

## Per-Adapter and Per-Request Overrides

Everything above describes the **global default** budget, computed from
`general.inference_provider` and its `config/inference.yaml` settings. On top of
that, individual adapters — and individual runtime model choices — can override
`inference_provider`, `context_window`, `max_tokens`, and `temperature` for
themselves. The history token budget automatically follows whichever provider
actually answers a given turn.

### Precedence

```
runtime (allowed_models entry selected via the "model" request field)
  > adapter config (config/adapters/*.yaml)
    > config/inference.yaml default
```

### Adapter-level overrides

```yaml
# config/adapters/passthrough.yaml
adapters:
  - name: "simple-chat"
    type: "passthrough"
    inference_provider: "openai"   # Override the global default provider
    model: "gpt-5.4-mini"
    context_window: 200000         # Optional — also reshapes the history budget
    max_tokens: 4096                # Optional
    temperature: 0.3                # Optional (LLM call only; doesn't affect history)
```

If an adapter sets `context_window`/`max_tokens`, those values — merged with the
adapter's `inference_provider` (or the global default provider if the adapter
doesn't set one) — replace the global default budget for every request that uses
that adapter.

### Per-request overrides via `allowed_models`

An adapter can also let clients pick from a fixed list of models at request time
(via the `model` field in the chat request), and each entry may carry its own
overrides:

```yaml
allowed_models:
  - name: "claude"
    provider: "anthropic"
    model: "claude-sonnet-4-5-20250929"
    context_window: 1000000   # e.g. Claude's extended-context variant
  - name: "mistral"
    provider: "mistral"
    model: "mistral-small-2603"
    # No overrides on this entry — its own inference.yaml context_window (e.g. 32K) applies
```

When a client requests `"model": "mistral"` on an adapter otherwise configured
for a 128K-context provider, **that specific turn's** history budget is
calculated against `mistral`'s own `context_window`/`max_tokens` from
`config/inference.yaml` (32,768 by default here), not the adapter's 128K
default — even though the `mistral` entry itself sets no overrides. The selected
*provider* alone is enough to change which provider's defaults apply.

### What this means in practice

- **Switching models mid-conversation is safe** — on the next request, only as
  much prior history is included in the prompt as fits the newly-selected
  model's budget. Nothing crashes or silently truncates mid-response.
- **The original messages aren't deleted just because they weren't sent** —
  they remain in the database. They're only *permanently* deleted if the
  post-turn cleanup threshold (120% of that turn's budget) is exceeded. Since
  cleanup uses whichever budget applied to *that* turn, switching to a
  smaller-context model can trigger deletion of messages that were stored
  under a larger budget from an earlier turn in the same session.
- **A smaller usable budget than the raw context window suggests**: the reserved
  amount includes the *selected* model's own output-token setting (see
  [The Calculation Process](#how-it-works)), so two models with the same
  context window but different `max_tokens` configurations get different
  history budgets.

### Provider-native parameter names

Local/self-hosted providers (Ollama family, llama.cpp, BitNet, vLLM,
TensorRT-LLM, HuggingFace) don't read a generic `context_window` key from their
config section — they use their own native option name (see the
[provider table](#automatic-calculation) above: `num_ctx`, `n_ctx`,
`max_model_len`, `max_length`). An adapter or `allowed_models` override to
`context_window`/`max_tokens` is written to **both** the generic key and that
provider's native key, so it takes effect regardless of which one the provider
actually reads — including for the actual LLM call, not just the history budget.

## Configuration

### Minimal Configuration Required

The conversation history system requires **no manual configuration** for message limits. It only needs basic settings:

```yaml
chat_history:
  enabled: true                    # Enable/disable the system
  collection_name: "chat_history"  # MongoDB collection name
  default_limit: 20               # Default messages per API call
  store_metadata: true            # Store additional metadata
  retention_days: 90              # How long to keep messages
  max_tracked_sessions: 10000     # Max sessions in memory
  session:
    required: true                # Require session IDs
    header_name: "X-Session-ID"   # HTTP header name
  user:
    header_name: "X-User-ID"      # Optional user tracking
    required: false
```

### What's NOT Needed

❌ **No longer required**:
```yaml
# This parameter is automatically calculated
max_conversation_messages: 1000  # ← REMOVED
```

### Inference Provider Configuration

The system reads context window from your inference provider config:

```yaml
general:
  inference_provider: "llama_cpp"  # ← System uses this

inference:
  llama_cpp:
    n_ctx: 4096                   # ← System reads this
    # ... other settings
```

## Examples

### Example 1: Small Local Model

**Configuration**:
```yaml
general:
  inference_provider: "llama_cpp"
inference:
  llama_cpp:
    n_ctx: 1024
```

**Result**:
- Context window: 1,024 tokens
- Token budget: 100 tokens (safety minimum enforced — the reserved system prompt + default 1,024-token output budget already exceeds the context window)
- Conversation length: Varies based on message sizes

### Example 2: Medium Local Model

**Configuration**:
```yaml
general:
  inference_provider: "ollama"
inference:
  ollama:
    num_ctx: 8192
```

**Result**:
- Context window: 8,192 tokens
- Token budget: 6,468 tokens
- Conversation length: Varies based on message sizes

### Example 3: Cloud API

**Configuration**:
```yaml
general:
  inference_provider: "openai"
inference:
  openai:
    model: "gpt-4o"
```

**Result**:
- Context window: 128,000 tokens (default)
- Token budget: 126,276 tokens
- Conversation length: Varies based on message sizes

### Example 4: Switching the Global Default Provider

Changing `general.inference_provider` changes the budget used for adapters that
don't set their own `inference_provider` — but **requires a service restart**,
since the global default budget (`max_token_budget`) is computed once when
`ChatHistoryService` initializes:

```yaml
# Before: Using small local model
general:
  inference_provider: "llama_cpp"  # 100 token budget (n_ctx: 1024)

# After restart: Switching to cloud API
general:
  inference_provider: "anthropic"  # 198,276 token budget (default 200K context)
```

For switching models **without a restart**, see
[Per-Adapter and Per-Request Overrides](#per-adapter-and-per-request-overrides) —
setting `inference_provider`/`context_window`/`max_tokens` on an adapter, or
letting clients pick a model via `allowed_models`, changes the budget on the very
next request that uses it.

### Example 5: Custom Context Windows

**Configuration with Enhanced Detection**:
```yaml
general:
  inference_provider: "openai"  # Can be any provider
  
inference:
  # Local providers use native parameters
  ollama:
    num_ctx: 16384            # 16K context → ~163 messages
    
  # Cloud providers now support context_window
  openai:
    model: "gpt-4o"
    context_window: 64000     # 64K context → ~636 messages
    
  anthropic:
    model: "claude-3-sonnet"
    context_window: 150000    # 150K context → 1000 messages (capped)
    
  gemini:
    model: "gemini-1.5-pro"
    context_window: 48000     # 48K context → ~476 messages
```

**Results** (default `max_tokens`/`num_predict` of 1,024):
- **OpenAI**: 64,000 tokens → 62,276 token budget
- **Anthropic**: 150,000 tokens → 148,276 token budget
- **Ollama**: 16,384 tokens → 14,660 token budget
- **Automatic scaling** based on your exact configuration

## Technical Details

### Token Counting

The system uses a two-phase token counting approach:

**Phase 1: Fast Estimation (Immediate Storage)**:
- Uses character-based estimation: ~3 characters per token (conservative)
- Applied immediately when messages are stored
- Ensures non-blocking message storage

**Phase 2: Accurate Tokenization (Background)**:
- Uses actual tokenizer (configurable via `tokenizer` setting)
- Calculated asynchronously in background worker
- Updates database with accurate token counts
- Adjusts session token cache when complete

**Reserved Space Breakdown**:
```
System prompt:                           ~500 tokens
Current query buffer:                    ~200 tokens
Fixed overhead subtotal:                  700 tokens
Model's response budget (max_tokens /
num_predict; defaults to 1,024):        1,024 tokens (example — varies by config)
Total reserved (example):               1,724 tokens
```

### Rolling Window Query with Cleanup

The system uses a token-based rolling window query approach with automatic cleanup:

1. **Query Strategy**: Fetches messages from newest to oldest
2. **Token Accumulation**: Adds messages until token budget is reached
3. **Natural Limiting**: Query automatically stops when budget would be exceeded
4. **Chronological Order**: Results are reversed to oldest-to-newest for LLM context
5. **Automatic Cleanup**: Messages exceeding 120% of budget are permanently deleted

**Example**: If token budget is 6,468 tokens:
- Query fetches messages starting from most recent
- Accumulates: Message 1 (150 tokens), Message 2 (200 tokens), ...
- Stops when adding next message would exceed 6,468 tokens
- Returns selected messages in chronological order
- If session reaches 7,761 tokens (120%), oldest messages are deleted

### Thread Safety

The cleanup mechanism uses per-session locking to ensure thread safety:

1. **Per-Session Locks**: Each session has its own asyncio.Lock
2. **Double-Check Pattern**: Quick pre-check before acquiring lock, re-check after
3. **Skip if Locked**: If another coroutine is already cleaning, the request skips cleanup
4. **Atomic Updates**: Cache updates happen within the lock to prevent race conditions

**Concurrency Behavior**:
```
Request A: Triggers cleanup → Acquires lock → Deletes messages → Releases lock
Request B: Triggers cleanup → Lock already held → Skips cleanup → Continues
```

This prevents duplicate cleanup operations and ensures data consistency.

### Safety Bounds

**Minimum Token Budget**: 100 tokens
- Ensures basic conversation functionality
- Applied even for very small context windows

**Maximum Token Budget**: 800,000 tokens  
- Prevents excessive memory usage
- Applied even for very large context windows (e.g., Claude 3)

### Efficiency Metrics

The system maximizes context window utilization:

```
Efficiency = (Reserved + Conversation_Tokens) / Context_Window
```

The rolling window query naturally fills the available token budget, maximizing conversation length while preventing context overflow.

## Monitoring and Troubleshooting

### Startup Logging

When the service starts, you'll see:

```
Chat History Service initialized with max_token_budget=6468 tokens
```

This is the **global default** budget only, computed from `general.inference_provider`.
Adapters or requests using a different provider (via an adapter-level override or
`allowed_models`) get their own budget computed and logged the first time they're
used — see [Per-Adapter and Per-Request Overrides](#per-adapter-and-per-request-overrides).

### Verbose Logging

Enable verbose mode for detailed calculation logs:

```yaml
general:
  verbose: true
```

**Verbose Output**:
```
Token budget calculation: provider=ollama, context_window=8192,
reserved=1724, available=6468, max_budget=6468
```

### Service Metrics

`ChatHistoryService` exposes `get_metrics()` and `health_check()` methods with
this shape:

```json
{
  "active_sessions": 15,
  "tracked_sessions": 42,
  "messages_today": 234,
  "oldest_tracked_session": "2026-01-01T00:00:00+00:00",
  "max_token_budget": 6468,
  "max_tracked_sessions": 10000,
  "retention_days": 90
}
```

There is currently no dedicated admin HTTP route exposing these directly. For
inspecting an individual session's stored history, use:

```bash
GET /admin/chat-history/{session_id}
```

`max_token_budget` reflects only the **global default provider's** budget. It
does not surface the per-adapter or per-runtime-model budgets described in
[Per-Adapter and Per-Request Overrides](#per-adapter-and-per-request-overrides) —
those are only visible via debug logging on the request that used them.

### Common Issues

**Issue**: Token budget seems too low
```
Solution: Check your inference provider's context window setting
- llama.cpp / BitNet: Increase n_ctx
- Ollama (local/cloud/remote): Increase num_ctx
- vLLM / TensorRT-LLM: Increase max_model_len
- Cloud providers: Set context_window parameter
- Check the provider's configured max_tokens/num_predict — a large output
  reservation eats directly into the history budget (see The Calculation Process)
- If this is adapter- or model-specific, check for a context_window/max_tokens
  override on the adapter or the allowed_models entry that was selected
  (see Per-Adapter and Per-Request Overrides)
- Check model documentation for optimal values
```

**Issue**: Messages not being stored
```
Solution: Verify chat_history configuration
- Ensure enabled: true
- Check MongoDB connection
- Verify session_id headers are provided
```

**Issue**: Context window calculation fails
```
Fallback: System uses 4000 tokens as safe default
Check logs for: "Error calculating max token budget"
Verify inference provider configuration is valid
```

### Performance Considerations

**Memory Usage**: Proportional to `max_tracked_sessions` setting
**Database Growth**: Managed by `retention_days` cleanup
**Computation**:
- The **global default** budget is calculated once at service startup.
- Any **adapter- or runtime-model-specific** budget (see
  [Per-Adapter and Per-Request Overrides](#per-adapter-and-per-request-overrides))
  is calculated lazily the first time it's needed, then cached in memory for the
  life of the process — it is a cheap, non-blocking calculation, not a per-request cost.
- ⚠️ These cached per-adapter/per-runtime-model budgets are **not** invalidated by
  a live adapter config reload. If you change an adapter's `context_window`/
  `max_tokens`/`inference_provider` via the admin API without restarting the
  server, chat history for that adapter keeps using the previously cached budget
  until the process restarts.

### Migration from Fixed Limits

If you previously used a fixed `max_conversation_messages`:

1. **Remove** the parameter from your config
2. **Restart** the service
3. **Verify** new token budget in startup logs
4. **Enjoy** automatic optimization!

The system will seamlessly transition to dynamic token budget calculation without data loss. All existing messages remain in the database and will be included in rolling window queries based on their token counts.

## Conversation Limit Warnings

### 🔔 Proactive Memory Alerts

The system automatically warns users when their conversation approaches the token budget limit, alerting them before old messages are permanently deleted. Users receive clear notifications when it's time to consider starting a new conversation.

### Warning and Cleanup Thresholds

The system uses **two thresholds** based on token usage:

| Threshold | Calculation | Purpose |
|-----------|-------------|---------|
| **Warning** | 90% of token budget | Early notice before deletion occurs |
| **Cleanup** | 120% of token budget | Triggers automatic deletion of oldest messages |

### Example Warning Messages

**⚠️ Memory Warning** (at 90% token threshold):
```
⚠️ **WARNING**: This conversation is using 5900/6468 tokens. Older messages
will be automatically deleted to stay within limits. Consider starting a new
conversation if you want to preserve the full context.
```

The warning message can be customized via the `messages.conversation_limit_warning` configuration option, which supports `{current_tokens}` and `{max_tokens}` placeholders.

### Warning Behavior by Model Size

**Small Models** (e.g., TinyLlama with 1K context → 100 token budget, safety minimum enforced):
- Warning at 90 tokens (90% of 100)
- Cleanup at 120 tokens (120% of 100)
- Tight limits require immediate action

**Medium Models** (e.g., Ollama with 8K context → 6,468 token budget):
- Warning at 5,821 tokens (90% of 6,468)
- Cleanup at 7,761 tokens (120% of 6,468)
- "Older messages will be automatically deleted"

**Large Models** (e.g., a 32K-context model → 31,044 token budget):
- Warning at 27,939 tokens (90% of 31,044)
- Cleanup at 37,252 tokens (120% of 31,044)
- "Consider starting a new conversation if you want to preserve the full context"
