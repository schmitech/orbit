# Manual/Integration Check: PII Moderation (privacy_filter)

End-to-end verification of the `privacy_filter` moderation provider, using a
real running server and the orbitchat UI. The provider detects personally
identifiable information (PII) in user messages with OpenAI's
`openai/privacy-filter` token-classification model, running fully locally.

The automated unit tests (`test_privacy_filter_moderation.py`) already cover
configuration parsing, span-to-result mapping, threshold and category
filtering, batch alignment, and fail-open behavior with a mocked pipeline.
This playbook exercises the real model download and inference path, the
guardrail integration in the chat pipeline, and the operational config knobs
(threshold, flag_categories) that unit tests mock away.

Prerequisites:

- The `huggingface` dependency profile is installed
  (`./install/setup.sh --profile huggingface`). The first run downloads the
  model (~1.5B params) from HuggingFace; allow a few minutes and disk space.
- ORBIT runs at `http://localhost:3000` with an API key bound to any
  chat-capable adapter.
- orbitchat UI running against the server (`cd clients/orbitchat && npm run dev`).

## 0. Enable PII moderation

In `config/guardrails.yaml`:

```yaml
safety:
  enabled: true
  moderator: "privacy_filter"
```

The `moderations.privacy_filter` block in `config/moderators.yaml` works
as shipped (all 8 categories flagged at threshold 0.5). Restart ORBIT and
confirm the model loads:

```
Loading privacy filter model: openai/privacy-filter
Privacy filter model loaded: openai/privacy-filter (device=...)
Safety service using moderator: privacy_filter
```

## 1. Baseline: benign message passes

In orbitchat, send:

> What are your support hours?

Expected: a normal answer. No moderation warnings in the server log.

## 2. Personal identifiers are blocked

Send each of the following as separate messages:

> Hi, my name is Alice Smith and my email is alice.smith@example.com

> Call me back at 416-555-0192

> I live at 22 Baker Street, Toronto

Expected: each message is blocked with the moderation refusal message
instead of a normal answer. The server log shows
`Message blocked by Moderator Service` and (at DEBUG level) the detected
categories, e.g. `pii.private_person`, `pii.private_email`,
`pii.private_phone`, `pii.private_address`.

## 3. Secrets are blocked

Send:

> Here is our API key: sk-live-4f8a2b91c3d7e6f0a1b2c3d4

Expected: blocked, with `pii.secret` in the logged categories.

## 4. Threshold tuning

In `config/moderators.yaml`, set:

```yaml
  privacy_filter:
    threshold: 0.99
```

Restart, then resend the message from step 2. High-confidence detections
(clear emails/names) should still block. Now try an ambiguous case:

> ask about smith

Expected: passes at 0.99 (low-confidence person-name detection no longer
crosses the threshold). Reset `threshold: 0.5` afterwards.

## 5. Category scoping

In `config/moderators.yaml`, remove `private_date` from `flag_categories`
(leave the others). Restart, then send:

> I was born on March 12, 1988

Expected: the message passes; if DEBUG logging is on, `pii.private_date`
still appears in the category scores (reported but not flagged). A message
containing an email still blocks. Restore the full list afterwards.

## 6. Fail-open on model failure

In `config/moderators.yaml`, set `model: "openai/does-not-exist"` and
restart. Send a message containing an email address.

Expected: the message is NOT blocked (moderation fails open, consistent
with the other moderators), and the server log shows a warning such as
`Moderation check failed, allowing content through` or
`Privacy filter initialization failed`. Restore
`model: "openai/privacy-filter"` afterwards.

> Note: fail-open means a moderation outage silently disables PII blocking.
> If your deployment treats PII leakage as worse than downtime, monitor for
> these warnings.

## 7. No regressions for other moderators

Set `safety.moderator` back to your previous provider (e.g. `openai` or
`ollama`), restart, and send one benign and one unsafe message.

Expected: behavior unchanged from before this feature; the privacy filter
model is not loaded (no `Loading privacy filter model` log line).

## Cleanup

Restore `config/guardrails.yaml` and `config/moderators.yaml` to their
original values and restart.
