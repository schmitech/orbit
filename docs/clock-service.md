# 🕒 Clock Service

## Overview

The **Clock Service** is a new feature in ORBIT that provides timezone-aware date and time information to the LLM during the inference process. This allows the LLM to have temporal context, enabling more accurate and personalized responses based on the user's local time.

### Key Features
- **Timezone-Aware**: Provides the current time in any specified timezone.
- **Configurable**: Can be enabled/disabled globally and configured per-adapter.
- **Automatic Prompt Injection**: Seamlessly prepends the current date and time to the user's prompt.
- **Personalization**: Enhances the LLM's ability to give time-sensitive and location-aware answers.
- **Works Offline**: Does not require an internet connection, making it suitable for air-gapped environments.

## Offline and Air-Gapped Environments

The Clock Service is designed to work entirely offline and does not require an internet connection.

-   **Local System Time**: It retrieves the current time from the server's local operating system clock. It does not connect to any external time servers (e.g., NTP).
-   **Local Timezone Database**: Timezone conversions are handled using a local database of timezone information that is included with Python's standard libraries.

This makes the feature fully functional in secure, air-gapped environments. The only requirement is that the system clock on the server running ORBIT is set accurately.

## How It Works

The system uses a dedicated `ClockService` that is initialized at startup. When a request is processed, the service does the following:

1.  **Checks Adapter Configuration**: It looks for a `timezone` setting in the configuration of the adapter being used.
2.  **Gets Current Time**: It retrieves the current time and formats it according to the specified timezone. If no timezone is set for the adapter, it falls back to a global default (or UTC).
3.  **Injects into Prompt**: The formatted date and time string is prepended to the user's prompt as a `System` message before being sent to the LLM.

This ensures the LLM always has the most relevant temporal context for the request.

## Configuration

Configuration is managed in two places: globally in `config.yaml` and per-adapter in `adapters.yaml`.

### Global Configuration (`config/config.yaml`)

A new `clock_service` section has been added to `config.yaml` to control the service globally.

```yaml
# In config.yaml

clock_service:
  enabled: true
  default_timezone: "UTC"  # A sensible default, e.g., "America/New_York", "Europe/London"
  format: "%A, %B %d, %Y at %I:%M:%S %p %Z" # e.g., "Tuesday, August 19, 2025 at 05:30:00 PM UTC"
```

-   `enabled`: Set to `true` to enable the service.
-   `default_timezone`: The timezone to use if an adapter does not specify one. A list of valid timezone names can be found on Wikipedia's list of tz database time zones.
-   `format`: The Python `strftime` format for the timestamp string.

### Adapter-Specific Configuration (`config/adapters.yaml`)

You can specify a timezone for each adapter to provide location-specific context.

```yaml
# In config/adapters.yaml

adapters:
  - name: "qa-vector-qdrant-demo"
    enabled: true
    type: "retriever"
    # ... other settings
    config:
      collection: "demo"
      # ... other settings
      timezone: "America/New_York" # This adapter will use Eastern Time
```

If the `timezone` key is omitted, the adapter will use the `default_timezone` from `config.yaml`.

## Implementation Details

### `ClockService` (`server/services/clock_service.py`)

This new service contains all the logic for handling timezones and formatting timestamps. It uses Python's built-in `zoneinfo` library (or `pytz` as a fallback) for accurate timezone management.

### `LLMProvider` Integration

The `LLMProvider` implementations (e.g., `OllamaProvider`) have been updated to:
1.  Accept the `ClockService` during initialization.
2.  Accept a `timezone` parameter in their `generate` and `generate_stream` methods.
3.  Call a `_prepare_prompt` method to prepend the timestamp to the user's prompt.

### Example Prompt Modification

**Original Prompt:**
```
"What are today's top headlines?"
```

**Modified Prompt Sent to LLM (with `timezone: "America/Los_Angeles"`):**
```
System: The current date and time is Tuesday, August 19, 2025 at 02:45:15 PM PDT.

User: What are today's top headlines?
```
