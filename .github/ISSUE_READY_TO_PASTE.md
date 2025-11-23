# Feature Request: Support Prompt Strings in Addition to Files

## Summary

Currently, the ORBIT CLI commands (`key create` and `prompt create`) only accept prompts via `--prompt-file` (file path). It would be helpful to also support passing prompt text directly as a string parameter for convenience and ease of use.

## Current Behavior

The CLI requires creating a temporary file or using process substitution to pass prompt text:

```bash
# Current workaround using process substitution
./docker/orbit-docker.sh --container orbit-basic cli key create \
  --adapter simple-chat \
  --name "Default Chat Key" \
  --prompt-name "Default Assistant Prompt" \
  --prompt-file <(echo "You are a helpful assistant. Be concise and friendly.")

# Or creating a temp file first
docker exec -it orbit-basic sh -c 'echo "You are a helpful assistant..." > /tmp/prompt.txt && python /orbit/bin/orbit.py key create --adapter simple-chat --name "Key" --prompt-file /tmp/prompt.txt'
```

## Proposed Behavior

Add support for `--prompt-text` parameter that accepts a string directly:

```bash
# Proposed usage
./docker/orbit-docker.sh --container orbit-basic cli key create \
  --adapter simple-chat \
  --name "Default Chat Key" \
  --prompt-name "Default Assistant Prompt" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."

# Or for prompt create
./docker/orbit-docker.sh --container orbit-basic cli prompt create \
  --name "My Prompt" \
  --prompt-text "You are a helpful assistant..."
```

## Use Cases

1. **Quick onboarding**: New developers can create API keys with simple prompts without needing to create files
2. **CI/CD pipelines**: Easier to pass prompts as environment variables or command-line arguments
3. **Docker/containerized environments**: Avoids the need for file mounts or temporary file creation
4. **Interactive workflows**: More intuitive for simple prompts that don't warrant a separate file

## Implementation Details

### Commands to Update

1. **`key create`** (`bin/orbit/commands/keys.py`):
   - Add `--prompt-text` argument
   - Update `ApiService.create_api_key()` to accept `prompt_text` parameter
   - Priority: `--prompt-text` > `--prompt-file` (if both provided, use `--prompt-text`)

2. **`prompt create`** (`bin/orbit/commands/prompts.py`):
   - Add `--prompt-text` argument as alternative to `--file`
   - Update logic to accept either `--file` or `--prompt-text` (mutually exclusive or priority-based)

### Files to Modify

- `bin/orbit/commands/keys.py` - Add `--prompt-text` argument
- `bin/orbit/commands/prompts.py` - Add `--prompt-text` argument
- `bin/orbit/services/api_service.py` - Update `create_api_key()` and `create_prompt()` methods

### Backward Compatibility

- Keep `--prompt-file` and `--file` parameters for backward compatibility
- If both `--prompt-text` and `--prompt-file` are provided, `--prompt-text` takes precedence (or show an error)

## Example Implementation

```python
# In keys.py
parser.add_argument('--prompt-text', help='Prompt text as a string (alternative to --prompt-file)')
parser.add_argument('--prompt-file', help='Path to file containing system prompt')

# In execute method
if args.prompt_text:
    prompt_text = args.prompt_text
elif args.prompt_file:
    prompt_text = self.api_service.api_client.read_file_content(args.prompt_file)
else:
    prompt_text = None
```

## Priority

**Medium** - Nice-to-have feature that improves developer experience, especially for onboarding and Docker usage, but current workarounds are functional.

## Related Context

- Current documentation in `docker/README-BASIC.md` shows workarounds using process substitution
- Main `README.md` includes Docker setup instructions that would benefit from this feature
- Issue discovered during Docker basic image onboarding documentation work

