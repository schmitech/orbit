# Clock Service

## Overview

The **Clock Service** is a feature in ORBIT that provides timezone-aware date and time information to the LLM during the inference process. This allows the LLM to have temporal context, enabling more accurate and personalized responses based on the user's local time.

### Key Features
- **Timezone-Aware**: Provides the current time in any specified timezone.
- **Configurable**: Can be enabled/disabled globally and configured per-adapter.
- **Per-Adapter Format Override**: Each adapter can specify its own time format.
- **Customizable Instruction Template**: Configure how the time is presented to the LLM.
- **Automatic Prompt Injection**: Seamlessly prepends the current date and time to the user's prompt.
- **Timezone Caching**: Caches timezone objects for improved performance.
- **Startup Validation**: Validates timezone configuration at startup.
- **Health Check**: Built-in health check method for monitoring.
- **Works Offline**: Does not require an internet connection, making it suitable for air-gapped environments.

## Offline and Air-Gapped Environments

The Clock Service is designed to work entirely offline and does not require an internet connection.

-   **Local System Time**: It retrieves the current time from the server's local operating system clock. It does not connect to any external time servers (e.g., NTP).
-   **Local Timezone Database**: Timezone conversions are handled using a local database of timezone information that is included with Python's standard libraries.

This makes the feature fully functional in secure, air-gapped environments. The only requirement is that the system clock on the server running ORBIT is set accurately.

## How It Works

The system uses a dedicated `ClockService` that is initialized at startup. When a request is processed, the service does the following:

1.  **Checks Adapter Configuration**: It looks for `timezone` and `time_format` settings in the configuration of the adapter being used.
2.  **Gets Current Time**: It retrieves the current time and formats it according to the specified timezone and format. If no timezone is set for the adapter, it falls back to a global default (or UTC).
3.  **Injects into Prompt**: The formatted date and time string is prepended to the user's prompt as a `System` message before being sent to the LLM.

This ensures the LLM always has the most relevant temporal context for the request.

## Configuration

Configuration is managed in two places: globally in `config.yaml` and per-adapter in `adapters.yaml`.

### Global Configuration (`config/config.yaml`)

A `clock_service` section controls the service globally.

```yaml
# In config.yaml

clock_service:
  enabled: true
  default_timezone: "UTC"  # A sensible default, e.g., "America/New_York", "Europe/London"
  format: "%A, %B %d, %Y at %I:%M:%S %p %Z"  # e.g., "Tuesday, August 19, 2025 at 05:30:00 PM UTC"
  instruction_template: "System: The current date and time is {time}."  # Customizable template
```

Configuration options:

| Option | Description | Default |
|--------|-------------|---------|
| `enabled` | Set to `true` to enable the service | `false` |
| `default_timezone` | The timezone to use if an adapter does not specify one | `"UTC"` |
| `format` | The Python `strftime` format for the timestamp string | `"%Y-%m-%d %H:%M:%S %Z"` |
| `instruction_template` | Template for the time instruction. Use `{time}` as placeholder. | `"System: The current date and time is {time}."` |

### Adapter-Specific Configuration (`config/adapters.yaml`)

You can specify a timezone and/or time format for each adapter to provide location-specific context.

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
      timezone: "America/New_York"  # This adapter will use Eastern Time
      time_format: "%Y-%m-%d %H:%M"  # Optional: Override the format for this adapter
```

Configuration options per adapter:

| Option | Description |
|--------|-------------|
| `timezone` | Override the default timezone for this adapter |
| `time_format` | Override the default time format for this adapter |

If the `timezone` key is omitted, the adapter will use the `default_timezone` from `config.yaml`.
If the `time_format` key is omitted, the adapter will use the global `format` from `config.yaml`.

### Custom Instruction Templates

The `instruction_template` configuration allows you to customize how the time is presented to the LLM. The `{time}` placeholder will be replaced with the formatted timestamp.

Examples:

```yaml
# Default template
instruction_template: "System: The current date and time is {time}."
# Output: "System: The current date and time is Tuesday, August 19, 2025 at 05:30:00 PM UTC."

# Simple template
instruction_template: "Current time: {time}"
# Output: "Current time: Tuesday, August 19, 2025 at 05:30:00 PM UTC."

# Contextual template
instruction_template: "[Time Context] It is currently {time}. Use this for time-sensitive responses."
# Output: "[Time Context] It is currently Tuesday, August 19, 2025 at 05:30:00 PM UTC. Use this for time-sensitive responses."
```

## Implementation Details

### `ClockService` (`server/services/clock_service.py`)

This service contains all the logic for handling timezones and formatting timestamps. It uses Python's built-in `zoneinfo` library (Python 3.9+) or `pytz` as a fallback for accurate timezone management.

Key features:
- **Timezone Caching**: Uses `@lru_cache` to cache timezone objects for performance
- **Startup Validation**: Validates the default timezone at initialization
- **pytz Compatibility**: Full compatibility with pytz for older Python versions
- **Health Check**: Provides `health_check()` and `is_healthy()` methods

### Health Check

The ClockService provides a health check method that returns detailed status information:

```python
service = ClockService(config)
health = service.health_check()

# Returns:
{
    "enabled": True,
    "timezone_library": "zoneinfo",  # or "pytz"
    "default_timezone": "America/Toronto",
    "default_timezone_valid": True,
    "sample_output": "Wednesday, December 18, 2024 at 02:30:00 PM EST",
    "format": "%A, %B %d, %Y at %I:%M:%S %p %Z",
    "instruction_template": "System: The current date and time is {time}."
}
```

### `LLMProvider` Integration

The `LLMInferenceStep` in the pipeline has been updated to:
1.  Retrieve the `ClockService` from the service container.
2.  Get `timezone` and `time_format` from the `ProcessingContext`.
3.  Call `clock_service.get_time_instruction()` to get the formatted instruction.
4.  Prepend the instruction to the user's prompt.

### Example Prompt Modification

**Original Prompt:**
```
"What are today's top headlines?"
```

**Modified Prompt Sent to LLM (with `timezone: "America/Toronto"`):**
```
System: The current date and time is Tuesday, August 19, 2025 at 02:45:15 PM EDT.

User: What are today's top headlines?
```

## Timezone Reference

A list of valid timezone names follows the IANA Time Zone Database format (e.g., `America/New_York`, `Europe/London`, `Asia/Tokyo`). Common timezones include:

| Region | Timezone |
|--------|----------|
| US Eastern | `America/New_York` |
| US Central | `America/Chicago` |
| US Mountain | `America/Denver` |
| US Pacific | `America/Los_Angeles` |
| UK | `Europe/London` |
| Central Europe | `Europe/Paris` |
| Japan | `Asia/Tokyo` |
| Australia | `Australia/Sydney` |
| UTC | `UTC` |

For a complete list, see [Wikipedia's list of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

## Format String Reference

The format string uses Python's `strftime` format codes. Common codes include:

| Code | Description | Example |
|------|-------------|---------|
| `%Y` | 4-digit year | 2025 |
| `%m` | Month (01-12) | 08 |
| `%d` | Day (01-31) | 19 |
| `%H` | Hour (00-23) | 14 |
| `%I` | Hour (01-12) | 02 |
| `%M` | Minute (00-59) | 45 |
| `%S` | Second (00-59) | 15 |
| `%p` | AM/PM | PM |
| `%A` | Full weekday | Tuesday |
| `%B` | Full month | August |
| `%Z` | Timezone abbreviation | EDT |

Example formats:
- `%Y-%m-%d %H:%M:%S %Z` → `2025-08-19 14:45:15 EDT`
- `%A, %B %d, %Y at %I:%M:%S %p %Z` → `Tuesday, August 19, 2025 at 02:45:15 PM EDT`
- `%Y-%m-%d` → `2025-08-19` (date only)
- `%H:%M` → `14:45` (24-hour time only)
