# Dedupe Prompt-Parsing Block in Inference Services — Implementation Plan

**Status: Complete.** The shared `_build_messages` helper was added to
`OpenAICompatibleBaseService` and all 11 in-scope providers were migrated to
it. NearAI was left as-is per the "separate decision" note below (option 1).

## Summary

Extract the repeated prompt-to-`messages` parsing block out of the individual
OpenAI-compatible inference services and into `OpenAICompatibleBaseService`,
so each provider calls one shared helper instead of carrying its own copy.

Found during review of PR #434 (Cheaper Inference provider): the same block
is copy-pasted into both `generate()` and `generate_stream()` of most
OpenAI-compatible providers.

```python
messages = kwargs.pop('messages', None)
if messages is None:
    if "\nUser:" in prompt and "Assistant:" in prompt:
        parts = prompt.split("\nUser:", 1)
        if len(parts) == 2:
            system_part = parts[0].strip()
            user_part = parts[1].replace("Assistant:", "").strip()
            messages = [
                {"role": "system", "content": system_part},
                {"role": "user", "content": user_part}
            ]
    else:
        messages = [{"role": "user", "content": prompt}]
```

### Scope (corrected)

11 providers carry this exact inline block in both `generate()` and
`generate_stream()` — 22 copies, not 24:
`venice`, `minimax`, `scaleway`, `deepinfra`, `lmstudio`, `cohere`, `nebius`,
`groq`, `moonshot`, `cheaperinference`, `cerebras`
(`server/ai_services/implementations/inference/`).

`nearai_inference_service.py` is **not** part of this duplication and needs
a separate decision (see below) — it already extracted its own
`_messages_from_prompt()` method, and additionally runs a
`_normalize_messages()` pass (remapping `developer` role to `system`) that
the other 11 providers don't do.

## Why this matters

- Any fix or change to the parsing rule (e.g. a malformed-prompt edge case)
  has to be hand-applied to 22 call sites today, and more with every new
  provider — easy to miss one.
- New providers copy the existing pattern by example, so the duplication
  grows with each addition (Cheaper Inference is the latest instance).
- Not a correctness bug in the current code — this is a maintainability /
  simplification cleanup, not a behavior-changing fix.

## Approach

Add one method to `OpenAICompatibleBaseService`
(`server/ai_services/providers/openai_compatible_base.py`):

```python
@staticmethod
def _build_messages(prompt: str, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    """Pop 'messages' from kwargs if present, else derive it from prompt.

    Return type is list[dict[str, Any]], not list[dict[str, str]]: an
    explicit `messages` kwarg passed by a caller may carry non-string
    content (e.g. multimodal content-block lists), so the value type
    must not be narrowed to str.
    """
    messages = kwargs.pop('messages', None)
    if messages is not None:
        return messages

    if "\nUser:" in prompt and "Assistant:" in prompt:
        parts = prompt.split("\nUser:", 1)
        if len(parts) == 2:
            system_part = parts[0].strip()
            user_part = parts[1].replace("Assistant:", "").strip()
            return [
                {"role": "system", "content": system_part},
                {"role": "user", "content": user_part},
            ]

    return [{"role": "user", "content": prompt}]
```

Replace the inline block in each of the 11 providers' `generate()` and
`generate_stream()` with:

```python
messages = self._build_messages(prompt, kwargs)
```

Keep everything else in each provider untouched — `reasoning_effort`
handling, param assembly, usage reporting, and error handling all stay as
they are today. This is a pure extraction: same control flow, same output
for every input, just one implementation instead of 22.

### NearAI — separate decision, not auto-migrated

Do not silently fold NearAI into the shared helper. Options to decide at
implementation time:

1. Leave `nearai_inference_service.py` as-is (it's already de-duplicated
   locally) and only migrate the other 11.
2. Migrate it to call the shared `_build_messages()` and keep its own
   `_normalize_messages()` as a separate post-processing step applied on
   top of the result.

Either is acceptable; just don't delete `_normalize_messages()` or change
NearAI's `developer`→`system` remapping behavior as a side effect of this
cleanup.

## Scope / out of scope

- In scope: the 11 providers listed above, all using
  `OpenAICompatibleBaseService` and carrying the exact duplicated block.
- Separate decision, not auto-migrated: NearAI (see above).
- Out of scope: the `yield f"Error: {e!s}"` pattern in `generate_stream`'s
  error handling, and any other provider-specific logic. Those are separate,
  independently-verified conventions and not part of this cleanup.
- Out of scope: non-OpenAI-compatible providers (Anthropic, Gemini, Bedrock,
  etc.) — they don't share this base class or this parsing pattern.

## Verification

Test files currently exist only for `nearai` and `cheaperinference`
(`server/tests/test_inference/test_nearai_inference_service.py`,
`test_cheaperinference_inference_service.py`). The other 10 providers in
scope have **no existing test file** — tests for them must be written as
part of this work, not merely "kept passing".

- For `cheaperinference` (has tests): confirm the existing
  `test_generate` / `test_generate_stream` assertions on `messages` still
  pass unmodified after switching to the shared helper.
- For the other 10 providers with no test file: add one test file per
  provider (or a parametrized shared test module, implementer's choice)
  covering, through both `generate()` and `generate_stream()`:
  - a plain prompt (no `"\nUser:"`/`"Assistant:"` markers) →
    `[{"role": "user", "content": prompt}]`.
  - a `"\nUser:"`/`"Assistant:"`-formatted prompt → split into
    system/user messages as today.
  - an explicit `messages` kwarg passed through unchanged (including a
    case with non-string content, e.g. a content-block list, to confirm
    the helper doesn't coerce or drop it).
- Add a direct unit test for `_build_messages` on
  `OpenAICompatibleBaseService` covering the same three cases in isolation.
- If NearAI is migrated (option 2 above), add/extend its test to confirm
  `_normalize_messages()` still remaps `developer`→`system` after the
  shared helper runs.
- `ruff check server/ai_services/` must stay clean relative to the current
  baseline — several pre-existing, unrelated ruff findings exist in this
  area (noted in the PR #434 review) and are not in scope here.
