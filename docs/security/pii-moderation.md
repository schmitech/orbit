# PII Moderation with Privacy Filter

ORBIT can detect personally identifiable information (PII) in user messages
and block them before they reach the LLM, using the `privacy_filter`
moderation provider. It runs OpenAI's
[privacy-filter](https://huggingface.co/openai/privacy-filter) model, a
bidirectional token-classification model (Apache 2.0) that labels PII spans
in a single forward pass. The model runs fully on-premises through the
`transformers` library: no API key, no external calls, and a 128k-token
context window so long messages are processed without chunking.

## How it fits in

`privacy_filter` is a standard moderation provider, selected the same way as
`openai`, `anthropic`, or `ollama` moderation. When the safety layer is
enabled, every user message is checked before inference; a message with PII
detected above the confidence threshold is blocked with the moderation
refusal message.

Detected spans are reported as `ModerationResult` categories named
`pii.<category>` with the model's confidence score, so audit logs record
which PII types were seen.

## Detected categories

| Category | Examples |
|:---|:---|
| `private_person` | Personal names |
| `private_email` | Email addresses |
| `private_phone` | Phone numbers |
| `private_address` | Street/home addresses |
| `account_number` | Bank/account identifiers |
| `private_url` | Personal URLs |
| `private_date` | Personal dates (e.g. birth dates) |
| `secret` | API keys, credentials, tokens |

## Setup

1. Install the `huggingface` dependency profile (transformers + torch):

   ```bash
   ./install/setup.sh --profile huggingface
   ```

2. Select the moderator in `config/guardrails.yaml`:

   ```yaml
   safety:
     enabled: true
     moderator: "privacy_filter"
   ```

3. (Optional) Tune the provider in `config/moderators.yaml`:

   ```yaml
   moderations:
     privacy_filter:
       model: "openai/privacy-filter"   # Or a fine-tuned variant
       device: "auto"                   # auto, cpu, cuda, or mps
       threshold: 0.5                   # Minimum span confidence to flag
       flag_categories:                 # Categories that block when detected
         - "account_number"
         - "private_address"
         - "private_email"
         - "private_person"
         - "private_phone"
         - "private_url"
         - "private_date"
         - "secret"
   ```

The model (~1.5B parameters, 50M active) is downloaded from HuggingFace on
first startup and cached locally. GPU is not required; CPU inference is
practical for chat-message-sized inputs.

## Tuning

- **`threshold`** controls the precision/recall tradeoff. Lower values catch
  more PII but flag more false positives (e.g. public figures' names);
  higher values only block high-confidence detections.
- **`flag_categories`** scopes which PII types block a message. Categories
  removed from the list are still scored and logged (`pii.<category>`), just
  not flagged. For example, teams that only care about credential leakage
  can flag only `secret` and `account_number` while still auditing the rest.
- **`model`** accepts any HuggingFace token-classification model that emits
  the same label taxonomy, so a fine-tuned variant of privacy-filter can be
  dropped in for organization-specific label policies.

## Limitations

- **Detection only, no redaction.** A flagged message is blocked, not
  masked. Redaction (masking PII and letting the request continue) is a
  possible future enhancement.
- **Fail-open.** Consistent with ORBIT's other moderators, technical
  failures (model failed to load, inference error) allow content through
  with a warning in the logs rather than blocking all traffic. Monitor for
  `Moderation check failed, allowing content through` if PII leakage is a
  bigger risk than downtime for your deployment.
- **Model limitations.** The model is primarily English-trained; recall may
  drop on non-English text, non-Latin scripts, uncommon name conventions,
  and novel credential formats. Per the model card, it should be one layer
  in a privacy-by-design approach, not an anonymization guarantee.

## Verification

- Unit tests: `server/tests/test_services/test_privacy_filter_moderation.py`
- Scenario playbook: `server/tests/test_services/playbook-pii-moderation.md`
