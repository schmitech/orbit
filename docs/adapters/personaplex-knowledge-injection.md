# PersonaPlex Knowledge Injection

This guide explains how to configure PersonaPlex voice adapters with knowledge injection, enabling grounded factual responses in full-duplex voice conversations.

## Overview

PersonaPlex is NVIDIA's full-duplex speech-to-speech model that enables natural, conversational voice interactions. Unlike traditional voice assistants, PersonaPlex can listen and speak simultaneously, supporting natural conversational dynamics like backchannels, interruptions, and overlapping speech.

**Key Challenge**: PersonaPlex's system prompt (`text_prompt`) must be set at WebSocket connection time and cannot be changed mid-session. This means dynamic RAG (Retrieval-Augmented Generation) during conversation is not possible.

**Solution**: Knowledge Injection loads verified facts from static text files and embeds them directly into the system prompt, giving PersonaPlex grounded knowledge to answer factual questions.

## Architecture

```
User connects to /ws/voice/{adapter}
    |
    v
PersonaPlexWebSocketHandler.initialize()
    |
    +-- Load base prompt from database (PromptService)
    |
    +-- Load facts from static file (PersonaPlexKnowledgeService)
    |
    +-- Get current time (ClockService)
    |
    +-- Build augmented prompt: base_prompt + time + facts
    |
    v
PersonaPlexProxyService.create_session(text_prompt=augmented_prompt)
    |
    v
Full-duplex conversation with embedded knowledge
```

## Configuration

### Adapter Configuration

Add a `knowledge` section to your PersonaPlex adapter pointing to a facts file:

```yaml
adapters:
  - name: "personaplex-city-general"
    enabled: true
    type: "speech_to_speech"
    adapter: "personaplex"
    implementation: "ai_services.implementations.speech_to_speech.PersonaPlexService"

    capabilities:
      supports_realtime_audio: true
      supports_full_duplex: true
      supports_interruption: true
      supports_backchannels: true

    persona:
      voice_prompt: "NATF2.pt"

    # Knowledge injection from static file
    knowledge:
      enabled: true
      facts_file: "examples/city-facts/general-facts.txt"

    config:
      websocket_enabled: true
      max_session_duration_seconds: 1800
      timezone: "America/Toronto"  # For clock service
```

### Facts File Format

Create a plain text file with one fact per line. Lines starting with `#` are comments:

```text
# City General Facts
# Verified facts for PersonaPlex knowledge injection
# Lines starting with # are ignored

City Hall is open Monday-Friday 8:30 AM to 4:30 PM.
Birth certificates cost $20 at the Vital Records Office.
Residential parking permits cost $25 per year.
The non-emergency police line is 555-0100.
Property tax bills are due January 31st and July 31st.
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable/disable knowledge injection |
| `facts_file` | string | required | Path to text file (relative to project root) |
| `max_items` | integer | all | Maximum facts to include (optional limit) |

## Topic-Specific Adapters

For large knowledge bases, create topic-specific adapters with focused facts files:

```yaml
# General inquiries
- name: "personaplex-city-general"
  knowledge:
    enabled: true
    facts_file: "examples/city-facts/general-facts.txt"

# Permits and licenses
- name: "personaplex-city-permits"
  knowledge:
    enabled: true
    facts_file: "examples/city-facts/permits-facts.txt"

# Utilities (water, garbage, etc.)
- name: "personaplex-city-utilities"
  knowledge:
    enabled: true
    facts_file: "examples/city-facts/utilities-facts.txt"

# Vital records, parks, recreation
- name: "personaplex-city-records"
  knowledge:
    enabled: true
    facts_file: "examples/city-facts/records-facts.txt"
```

Route users to the appropriate adapter based on their needs for better accuracy.

## Dynamic Services

### Clock Service (Time Awareness)

When the global clock service is enabled, the current date/time is automatically injected into the system prompt. Configure per-adapter timezone in the `config` section:

```yaml
config:
  timezone: "America/Toronto"
```

The resulting prompt will include:
```
System: The current date and time is 2024-02-04 14:30:00 EST.
```

## System Prompts

Create prompts that instruct PersonaPlex to use the injected facts:

```markdown
You are Alex, a City Services assistant.

CRITICAL INSTRUCTION: Below this prompt is a "VERIFIED FACTS" section.
When someone asks about ANYTHING in that section, you MUST quote the
EXACT value. Do not round, estimate, or give ranges.

Your job:
- Answer questions using ONLY the facts provided below
- Quote exact prices, hours, and details
- If a question isn't covered in your facts, say "I don't have that specific information"
- Never guess or make up numbers
```

## Example: Complete Prompt Structure

When a user connects, the final prompt looks like:

```
You are Alex, a City Services assistant.

CRITICAL INSTRUCTION: Below this prompt is a "VERIFIED FACTS" section...

System: The current date and time is 2024-02-04 14:30:00 EST.

VERIFIED FACTS (you MUST use these exact values when answering):
• City Hall is open Monday-Friday 8:30 AM to 4:30 PM.
• Birth certificates cost $20 at the Vital Records Office.
• Residential parking permits cost $25 per year.
• The non-emergency police line is 555-0100.
... (more facts)

When asked about any topic above, use the EXACT information provided.
Do not estimate or guess different values.
```

## Generating Facts Files

You can extract facts from a QA database using a simple script:

```python
import json

with open('examples/city-qa-pairs.json', 'r') as f:
    data = json.load(f)

# Extract answers as facts
facts = [item['answer'] for item in data if item.get('answer')]

# Write to facts file
with open('examples/city-facts/all-facts.txt', 'w') as f:
    f.write("# City Facts\n\n")
    for fact in facts[:50]:  # Limit to 50
        f.write(f"{fact}\n")
```

For topic-specific files, filter by keywords in the question field.

## Performance

### Benefits of Static Files

- **No vector DB dependency** - Simpler deployment
- **Faster startup** - No embedding generation (saves 500ms+)
- **Predictable** - Same facts every time
- **Easy to test** - Just read the text file

### Prompt Size Limits

PersonaPlex has practical limits on prompt size:
- **Recommended**: Keep total prompt under 3000 characters
- **Maximum**: ~4000 characters before significant latency
- Increase `handshake_timeout` in `config/personaplex.yaml` for larger prompts

### Recommended Limits

- 40-50 facts per adapter works well
- Split into topic-specific adapters for larger knowledge bases
- Keep individual facts concise (one sentence)

## Troubleshooting

### No Knowledge Being Injected

Check the logs for:
```
INFO - Loaded 50 facts from 'examples/city-facts/general-facts.txt'
```

If missing:
1. Verify `knowledge.enabled: true` in adapter config
2. Check that `facts_file` path is correct
3. Verify the file exists and has content

### Facts File Not Found

```
ERROR - Facts file not found: examples/city-facts/missing.txt
```

Solution: Check the file path. Paths are relative to the project root.

### Inaccurate Answers

If PersonaPlex gives incorrect answers:
1. Verify the fact is in the facts file
2. Check the system prompt includes strong instructions to use exact values
3. Keep facts as direct statements (not questions)

### Timeout During Handshake

```
ERROR - PersonaPlex handshake timeout
```

Solution: Increase `handshake_timeout` in `config/personaplex.yaml`:
```yaml
proxy:
  handshake_timeout: 120  # seconds
```

## File Locations

- **Facts files**: `examples/city-facts/*.txt`
- **System prompts**: `examples/prompts/audio/personaplex-*.md`
- **Adapter config**: `config/adapters/personaplex.yaml`
- **PersonaPlex config**: `config/personaplex.yaml`
