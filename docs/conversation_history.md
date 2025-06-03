# Conversation History System

Orbit includes a conversation history system that automatically adapts to your chosen AI model's capabilities. This system maintains context across conversations while optimally utilizing available memory.

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Sliding Window Memory](#sliding-window-memory)
- [Dynamic Message Limits](#dynamic-message-limits)
- [Provider-Specific Behavior](#provider-specific-behavior)
- [Configuration](#configuration)
- [Examples](#examples)
- [Technical Details](#technical-details)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
- [Conversation Limit Warnings](#conversation-limit-warnings)

## Overview

The conversation history system provides:

- **Automatic Context Management**: Maintains conversation context without manual tuning
- **Memory Usage**: Dynamically calculates optimal message limits based on your AI model
- **Provider Awareness**: Adapts to different inference providers (llama.cpp, Ollama, OpenAI, etc.)
- **Efficient Resource Utilization**: Uses ~99% of available context window efficiently
- **Automatic Archiving**: Moves old messages to archive when limits are reached
- **⚠️ Proactive Warnings**: Alerts users before conversation memory gets archived

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

### The Solution

The system **dynamically calculates** the optimal number of conversation messages based on:

1. **Active inference provider** configuration
2. **Model's context window size**
3. **Estimated tokens per message**
4. **Reserved space** for system prompts and current queries

### The Calculation Process

```
Available Context = Context Window - Reserved Tokens
Max Messages = Available Context ÷ Average Tokens Per Message
```

Where:
- **Reserved Tokens**: 350 (system prompts + current query + response buffer)
- **Average Tokens Per Message**: 100 (conservative estimate including formatting)
- **Safety Bounds**: Minimum 10 messages, maximum 1,000 messages

## Sliding Window Memory

### 🔄 How Memory Actually Works

**IMPORTANT**: The system uses **sliding window memory**, not complete deletion. This is crucial to understand:

### ❌ **What It Does NOT Do** (Common Misconception):
```
Conversation: [1,2,3,4,5,6,7,8,9,10] → DELETE ALL → Start fresh from 0
```

### ✅ **What It Actually Does** (Sliding Window):
```
Messages: [1,2,3,4,5,6,7,8,9,10] → Archive [1,2] → Keep [3,4,5,6,7,8,9,10]
Add new:  [3,4,5,6,7,8,9,10,11,12] → Archive [3,4] → Keep [5,6,7,8,9,10,11,12]
```
ß
**The AI remembers information based on recency, not arbitrary cutoffs:**

#### **Information Gets Remembered When:**
- ✅ **Recently discussed**: "What's my name?" → AI recalls because it's in recent window
- ✅ **Frequently reinforced**: Topics you keep bringing up stay accessible
- ✅ **Context-relevant**: Information that connects to recent conversations

#### **Information Gets Forgotten When:**
- ❌ **Old and unreferenced**: Early topics not mentioned recently get archived
- ❌ **No recent reinforcement**: Details from beginning that haven't come up again
- ❌ **Outside sliding window**: Falls beyond the recent message limit

### 📊 **Real Example Scenarios**

#### **Scenario 1: Name Memory** (Why it persists)
```
Message 1:  "Hi, I'm Sarah"                    → [Eventually archived]
Message 15: "What's my name?"                  → [In recent window]
Message 16: "Your name is Sarah"               → [In recent window]
Message 25: "What's my name again?"            → [In recent window]  
Message 26: "Your name is Sarah"               → [In recent window]

Result: AI remembers "Sarah" because recent exchanges reinforced it
```

#### **Scenario 2: Early Details** (Why they're forgotten)
```
Message 2:  "I work at Microsoft"              → [Gets archived]
Message 3:  "I have a dog named Buddy"         → [Gets archived]  
[... 20 messages about other topics ...]
Message 25: "Where do I work?"                 → [Recent, but context lost]
Message 26: "I don't see that information     → [Can't access archived
             in our recent conversation"           messages]

Result: AI forgets early details not reinforced in recent conversation
```

#### **Scenario 3: Natural Conversation Flow**
```
Messages 1-5:   Discuss weekend plans          → [Eventually archived]
Messages 6-10:  Talk about work projects       → [Eventually archived]
Messages 11-15: Conversation about cooking     → [May be archived]
Messages 16-20: Return to work discussion      → [In recent window]
Messages 21-25: More work-related topics       → [In recent window]

Result: AI remembers recent work discussion, forgets weekend plans
```

### 🔍 **Testing Memory Behavior**

To verify the sliding window works correctly, try:

#### **Test Forgotten Information:**
- Ask about topics from your **first few messages** that you haven't mentioned recently
- Example: "What was the first thing I told you about myself?"
- **Expected**: AI won't remember if it's been archived

#### **Test Remembered Information:**
- Ask about topics you've discussed **recently or repeatedly**  
- Example: "What's my name?" (if asked multiple times recently)
- **Expected**: AI remembers because it's in the sliding window

### 🚀 **Why This Design is Optimal**

1. **🧠 Natural Conversation Flow**: Like human memory, recent topics stay accessible
2. **⚡ Optimal Performance**: Always uses maximum available context efficiently  
3. **🔄 Continuous Context**: No jarring "memory wipes" that break conversation flow
4. **🎯 Relevance-Based**: Important information naturally stays through reinforcement
5. **📈 Scalable**: Works identically across tiny to massive models

### 🔧 **How Archiving Timing Works**

**Archiving happens BEFORE each new conversation turn:**

```
1. User asks question
2. System checks: "Will this exceed limit?"
3. If yes: Archive oldest messages first
4. Then: Retrieve recent context (post-archiving)
5. Generate response using clean recent context
6. Store new user question + AI response
```

**This ensures:**
- ✅ **Fresh context**: AI always sees most relevant recent messages
- ✅ **No overflow**: Context never exceeds model limits
- ✅ **Smooth experience**: No mid-conversation memory loss

## Dynamic Message Limits

### Automatic Calculation

The system examines your active inference provider configuration and extracts the context window size:

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
Available: 1,024 - 350 = 674 tokens
Max Messages: 674 ÷ 100 = 6.7 → 10 messages (safety minimum)
```

**Medium Model (Ollama with num_ctx: 8,192)**:
```
Available: 8,192 - 350 = 7,842 tokens  
Max Messages: 7,842 ÷ 100 = 78 messages
```

**Large Model (OpenAI GPT-4 with ~32K context)**:
```
Available: 32,768 - 350 = 32,418 tokens
Max Messages: 32,418 ÷ 100 = 324 messages
```

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
- 1K context → ~10 messages
- 4K context → ~37 messages  
- 8K context → ~78 messages

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
- OpenAI: 32,768 tokens → ~324 messages
- Anthropic: 200,000 tokens → 1,000 messages (capped)
- Groq: 8,192 tokens → ~78 messages

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
- **Resulting message limit**: ~37 messages  
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
- Max messages: 10 (safety minimum)
- Conversation length: ~5 back-and-forth exchanges

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
- Max messages: 78
- Conversation length: ~39 back-and-forth exchanges

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
- Max messages: 324
- Conversation length: ~162 back-and-forth exchanges

### Example 4: Switching Providers

When you change providers, limits automatically adjust:

```yaml
# Before: Using small local model
general:
  inference_provider: "llama_cpp"  # 10 messages max

# After: Switching to cloud API  
general:
  inference_provider: "anthropic"  # 1000 messages max
```

**No restart required** - limits recalculate on service initialization.

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
- **OpenAI**: 64,000 tokens → 636 conversation messages
- **Anthropic**: 150,000 tokens → 1,000 messages (safety cap)
- **Ollama**: 16,384 tokens → 163 conversation messages
- **Automatic scaling** based on your exact configuration

## Technical Details

### Token Estimation

The system uses conservative estimates:

**Per Message Breakdown**:
```
Role label: "User: " or "Assistant: "     ~5 tokens
Average message content:                  ~80 tokens  
Formatting and separators:                ~15 tokens
Total per message:                        ~100 tokens
```

**Reserved Space Breakdown**:
```
System prompt:                           ~200 tokens
Current user query:                       ~50 tokens
Response generation buffer:              ~100 tokens
Total reserved:                          ~350 tokens
```

### Message Archiving

When conversation exceeds the limit:

1. **Archive Trigger**: When messages >= `max_conversation_messages`
2. **Archive Amount**: Keep 80% of limit, archive the rest
3. **Archive Location**: `{collection_name}_archive` MongoDB collection
4. **Process**: Atomic MongoDB transaction ensures data integrity

**Example**: If limit is 100 messages and conversation reaches 100:
- Keep: 80 newest messages in active conversation
- Archive: 20 oldest messages moved to archive collection

### Safety Bounds

**Minimum Limit**: 10 messages
- Ensures basic conversation functionality
- Applied even for very small context windows

**Maximum Limit**: 1,000 messages  
- Prevents excessive memory usage
- Applied even for very large context windows (e.g., Claude 3)

### Efficiency Metrics

The system targets **~99% context window utilization**:

```
Efficiency = (Reserved + Message_Tokens) / Context_Window
Target: ~99%
```

This maximizes conversation length while preventing context overflow.

## Monitoring and Troubleshooting

### Startup Logging

When the service starts, you'll see:

```
Chat History Service initialized with max_conversation_messages=78 (inference-only mode)
```

### Verbose Logging

Enable verbose mode for detailed calculation logs:

```yaml
general:
  verbose: true
```

**Verbose Output**:
```
Context window calculation: provider=ollama, context_window=8192, 
available_tokens=7842, max_messages=78
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
  "archived_messages": 1200,
  "max_tracked_sessions": 10000,
  "retention_days": 90
}
```

### Common Issues

**Issue**: Max messages seems too low
```
Solution: Check your inference provider's context window setting
- llama.cpp: Increase n_ctx
- ollama: Increase num_ctx  
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
Fallback: System uses 100 messages as safe default
Check logs for: "Error calculating max conversation messages"
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
3. **Verify** new limits in startup logs
4. **Enjoy** automatic optimization!

The system will seamlessly transition to dynamic calculation without data loss.

## Conversation Limit Warnings

### 🔔 Proactive Memory Alerts

The system automatically warns users before their conversation reaches the memory limit, preventing unexpected context loss. Users receive clear notifications when it's time to consider starting a new conversation.

### Warning Thresholds

The system uses **two-tier warning thresholds** that adapt to your model's context window:

| Threshold | Calculation | Purpose | Message Type |
|-----------|-------------|---------|--------------|
| **Warning** | 90% of limit OR 5 messages before | Early notice | ℹ️ Memory Notice |
| **Critical** | 95% of limit OR 2 messages before | Urgent alert | ⚠️ Memory Warning |

### Example Warning Messages

**ℹ️ Memory Notice** (at 90% threshold):
```
ℹ️ Memory Notice: This conversation has 33/37 messages. After 4 more 
messages, older parts of our conversation will be automatically archived 
to maintain performance.
```

**⚠️ Memory Warning** (at 95% threshold):
```
⚠️ Memory Warning: This conversation has 35/37 messages. The next few 
messages will trigger automatic memory management - older messages will 
be archived to maintain optimal performance. Consider starting a new 
conversation if you want to preserve the full context.
```

### Warning Behavior by Model Size

**Small Models** (e.g., TinyLLama with 1K context → 10 messages):
- Warning at message 9: **Critical warning immediately**
- Tight limits require immediate action

**Medium Models** (e.g., Ollama with 8K context → 78 messages):
- Warning at message 70: "After 8 more messages, archiving will begin"
- Critical at message 74: "Consider starting new conversation"

**Large Models** (e.g., GPT-4 with 32K context → 324 messages):
- Warning at message 291: "After 33 more messages, archiving will begin"
- Critical at message 307: "Next few messages will trigger archiving"
