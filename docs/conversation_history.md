# Conversation History System

Orbit includes a conversation history system that automatically adapts to your chosen AI model's capabilities. This system maintains context across conversations while optimally utilizing available memory.

## Table of Contents

- [What is a Token?](#what-is-a-token)
- [Overview](#overview)
- [How It Works](#how-it-works)
- [Rolling Window Memory](#rolling-window-memory)
- [Dynamic Token Budget](#dynamic-token-budget)
- [Provider-Specific Behavior](#provider-specific-behavior)
- [Configuration](#configuration)
- [Examples](#examples)
- [Technical Details](#technical-details)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
- [Conversation Limit Warnings](#conversation-limit-warnings)

## Overview

The conversation history system provides:

- **Automatic Context Management**: Maintains conversation context without manual tuning
- **Token-Based Memory**: Dynamically calculates optimal token budget based on your AI model
- **Provider Awareness**: Adapts to different inference providers (llama.cpp, Ollama, OpenAI, etc.)
- **Efficient Resource Utilization**: Uses available context window efficiently via rolling window queries
- **Rolling Window Queries**: Automatically selects recent messages that fit within token budget
- **⚠️ Proactive Warnings**: Alerts users when conversation approaches token budget limits

### Key Benefits

1. **No Manual Configuration**: The system automatically determines the best settings
2. **Model-Optimized**: Adapts to each model's context window size
3. **Memory Efficient**: Prevents context overflow while maximizing conversation length
4. **Provider Agnostic**: Works seamlessly across all supported inference providers
5. **🔔 User-Friendly Warnings**: Never lose context unexpectedly

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
```

Where:
- **Reserved Tokens**: 350 (system prompts + current query + response buffer)
- **Safety Bounds**: Minimum 100 tokens, maximum 800,000 tokens

The system then uses a **rolling window query** to select messages that fit within this token budget, starting from the most recent messages and working backwards until the budget is reached.

## Rolling Window Memory

### 🔄 How Memory Actually Works

**IMPORTANT**: The system uses **token-based rolling window queries**, not message archiving. All messages remain in the database, but only recent messages that fit within the token budget are included in context.

### ❌ **What It Does NOT Do** (Common Misconception):
```
Conversation: [1,2,3,4,5,6,7,8,9,10] → DELETE ALL → Start fresh from 0
```

### ✅ **What It Actually Does** (Rolling Window Query):
```
All messages in DB: [1,2,3,4,5,6,7,8,9,10,11,12]
Token budget: 1000 tokens
Query result: [7,8,9,10,11,12]  ← Only messages that fit in token budget
Next query: [8,9,10,11,12,13]    ← Automatically adjusts as new messages added
```

**The AI remembers information based on recency and token usage, not arbitrary cutoffs:**

#### **Information Gets Remembered When:**
- ✅ **Recently discussed**: "What's my name?" → AI recalls because it's in recent token window
- ✅ **Frequently reinforced**: Topics you keep bringing up stay accessible
- ✅ **Context-relevant**: Information that connects to recent conversations
- ✅ **Within token budget**: Messages that fit within the available token budget

#### **Information Gets Excluded When:**
- ❌ **Old and unreferenced**: Early topics not mentioned recently fall outside token budget
- ❌ **No recent reinforcement**: Details from beginning that haven't come up again
- ❌ **Outside token window**: Messages exceed the token budget for context retrieval

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

#### **Scenario 2: Early Details** (Why they're excluded)
```
Message 2:  "I work at Microsoft"              → [Outside token budget]
Message 3:  "I have a dog named Buddy"         → [Outside token budget]  
[... 20 messages about other topics ...]
Message 25: "Where do I work?"                 → [Recent, but context lost]
Message 26: "I don't see that information     → [Can't access messages
             in our recent conversation"           outside token budget]

Result: AI can't access early details that fall outside the token budget
```

#### **Scenario 3: Natural Conversation Flow**
```
Messages 1-5:   Discuss weekend plans          → [Outside token budget]
Messages 6-10:  Talk about work projects       → [Outside token budget]
Messages 11-15: Conversation about cooking     → [May be outside budget]
Messages 16-20: Return to work discussion      → [In token window]
Messages 21-25: More work-related topics       → [In token window]

Result: AI remembers recent work discussion, can't access weekend plans
```

### 🔍 **Testing Memory Behavior**

To verify the rolling window works correctly, try:

#### **Test Excluded Information:**
- Ask about topics from your **first few messages** that you haven't mentioned recently
- Example: "What was the first thing I told you about myself?"
- **Expected**: AI won't remember if those messages fall outside the token budget

#### **Test Remembered Information:**
- Ask about topics you've discussed **recently or repeatedly**  
- Example: "What's my name?" (if asked multiple times recently)
- **Expected**: AI remembers because those messages are within the token budget

### 🚀 **Why This Design is Optimal**

1. **🧠 Natural Conversation Flow**: Like human memory, recent topics stay accessible
2. **⚡ Optimal Performance**: Always uses maximum available context efficiently  
3. **🔄 Continuous Context**: No jarring "memory wipes" that break conversation flow
4. **🎯 Relevance-Based**: Important information naturally stays through reinforcement
5. **📈 Scalable**: Works identically across tiny to massive models
6. **💾 Data Preservation**: All messages remain in database, only query results are limited

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
```

**This ensures:**
- ✅ **Fresh context**: AI always sees most relevant recent messages within token budget
- ✅ **No overflow**: Context never exceeds model limits
- ✅ **Smooth experience**: No mid-conversation memory loss
- ✅ **Data integrity**: All messages preserved in database

## Dynamic Token Budget

### Automatic Calculation

The system examines your active inference provider configuration and extracts the context window size to calculate a token budget:

| Provider | Primary Parameter | Universal Parameter | Typical Range |
|----------|------------------|-------------------|---------------|
| llama.cpp | `n_ctx` | `context_window` | 1,024 - 8,192 |
| Ollama | `num_ctx` | `context_window` | 2,048 - 32,768 |
| OpenAI | `context_window` | `max_context_length` | 8,192 - 128,000+ |
| Anthropic | `context_window` | `max_context_length` | 100,000 - 200,000+ |
| Gemini | `context_window` | `max_context_length` | 32,768 - 1,000,000+ |
| Groq | `context_window` | `max_context_length` | 8,192 - 32,768 |
| DeepSeek | `context_window` | `max_context_length` | 16,384 - 32,768 |
| HuggingFace | `max_length` | `context_window` | 512 - 4,096 |
| Others | `context_window` | `max_context_length` | Varies |

### Example Calculations

**Small Model (llama.cpp with n_ctx: 1,024)**:
```
Token Budget: 1,024 - 350 = 674 tokens
Safety Minimum: 100 tokens (applied)
Result: 674 tokens available for conversation history
```

**Medium Model (Ollama with num_ctx: 8,192)**:
```
Token Budget: 8,192 - 350 = 7,842 tokens
Result: 7,842 tokens available for conversation history
```

**Large Model (OpenAI GPT-4 with ~32K context)**:
```
Token Budget: 32,768 - 350 = 32,418 tokens
Result: 32,418 tokens available for conversation history
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

**Typical Results**:
- 1K context → 674 tokens available (minimum 100 tokens enforced)
- 4K context → 3,746 tokens available
- 8K context → 7,842 tokens available

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

**Fallbacks**: Uses defaults when not configured
- OpenAI: 32,768 tokens → 32,418 token budget
- Anthropic: 200,000 tokens → 199,650 token budget (capped at 800,000)
- Groq: 8,192 tokens → 7,842 token budget

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
  # No config found?           # ← 3rd priority: Default (32,768 tokens)
```

### Fallback Behavior

**For unknown providers or missing configuration**:
- **Default context window**: 4,096 tokens
- **Resulting token budget**: 3,746 tokens
- **Graceful degradation**: System continues working with reasonable defaults
- **Verbose logging**: Shows which defaults are being used

**Benefits of Enhanced Detection**:
- ✅ **Consistent behavior** across all providers
- ✅ **User control** over context windows for any provider
- ✅ **Defaults** when configuration is missing
- ✅ **No breaking changes** to existing configurations

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
- Token budget: 674 tokens (minimum 100 tokens enforced)
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
- Token budget: 7,842 tokens
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
- Context window: 32,768 tokens (default)
- Token budget: 32,418 tokens
- Conversation length: Varies based on message sizes

### Example 4: Switching Providers

When you change providers, limits automatically adjust:

```yaml
# Before: Using small local model
general:
  inference_provider: "llama_cpp"  # 674 token budget

# After: Switching to cloud API  
general:
  inference_provider: "anthropic"  # 199,650 token budget
```

**No restart required** - token budget recalculates on service initialization.

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

**Results**:
- **OpenAI**: 64,000 tokens → 63,650 token budget
- **Anthropic**: 150,000 tokens → 149,650 token budget
- **Ollama**: 16,384 tokens → 16,034 token budget
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
System prompt:                           ~200 tokens
Current user query:                       ~50 tokens
Response generation buffer:              ~100 tokens
Total reserved:                          ~350 tokens
```

### Rolling Window Query

The system uses a token-based rolling window query approach:

1. **Query Strategy**: Fetches messages from newest to oldest
2. **Token Accumulation**: Adds messages until token budget is reached
3. **Natural Limiting**: Query automatically stops when budget would be exceeded
4. **Chronological Order**: Results are reversed to oldest-to-newest for LLM context
5. **No Archiving**: All messages remain in database, only query results are limited

**Example**: If token budget is 7,842 tokens:
- Query fetches messages starting from most recent
- Accumulates: Message 1 (150 tokens), Message 2 (200 tokens), ...
- Stops when adding next message would exceed 7,842 tokens
- Returns selected messages in chronological order

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
Chat History Service initialized with max_token_budget=7842 tokens
```

### Verbose Logging

Enable verbose mode for detailed calculation logs:

```yaml
general:
  verbose: true
```

**Verbose Output**:
```
Token budget calculation: provider=ollama, context_window=8192, 
reserved=350, available=7842, max_budget=7842
```

### Health Check Endpoint

Monitor the service via the admin API:

```bash
GET /admin/chat-history-stats
```

**Response**:
```json
{
  "active_sessions": 15,
  "tracked_sessions": 42,
  "messages_today": 234,
  "max_token_budget": 7842,
  "max_tracked_sessions": 10000,
  "retention_days": 90
}
```

### Common Issues

**Issue**: Token budget seems too low
```
Solution: Check your inference provider's context window setting
- llama.cpp: Increase n_ctx
- ollama: Increase num_ctx  
- Cloud providers: Set context_window parameter
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
**Computation**: Calculation happens once at service startup

### Migration from Fixed Limits

If you previously used a fixed `max_conversation_messages`:

1. **Remove** the parameter from your config
2. **Restart** the service
3. **Verify** new token budget in startup logs
4. **Enjoy** automatic optimization!

The system will seamlessly transition to dynamic token budget calculation without data loss. All existing messages remain in the database and will be included in rolling window queries based on their token counts.

## Conversation Limit Warnings

### 🔔 Proactive Memory Alerts

The system automatically warns users when their conversation approaches the token budget limit, preventing unexpected context exclusion. Users receive clear notifications when it's time to consider starting a new conversation.

### Warning Thresholds

The system uses a **single warning threshold** based on token usage:

| Threshold | Calculation | Purpose |
|-----------|-------------|---------|
| **Warning** | 90% of token budget | Early notice before older messages are excluded |

### Example Warning Messages

**⚠️ Memory Warning** (at 90% token threshold):
```
⚠️ **WARNING**: This conversation is using 7057/7842 tokens. Older messages 
will be automatically excluded from context to stay within limits. Consider 
starting a new conversation if you want to preserve the full context.
```

The warning message can be customized via the `messages.conversation_limit_warning` configuration option, which supports `{current_tokens}` and `{max_tokens}` placeholders.

### Warning Behavior by Model Size

**Small Models** (e.g., TinyLLama with 1K context → 674 token budget):
- Warning at 607 tokens (90% of 674)
- Tight limits require immediate action

**Medium Models** (e.g., Ollama with 8K context → 7,842 token budget):
- Warning at 7,058 tokens (90% of 7,842)
- "Older messages will be automatically excluded from context"

**Large Models** (e.g., GPT-4 with 32K context → 32,418 token budget):
- Warning at 29,176 tokens (90% of 32,418)
- "Consider starting a new conversation if you want to preserve the full context"
