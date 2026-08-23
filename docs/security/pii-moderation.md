# PII Moderation

ORBIT can detect personally identifiable information (PII) in user messages and
block them before they reach the LLM. Two moderation providers cover this, and
they trade off in opposite directions:

| | `privacy_filter` | `presidio` |
|:---|:---|:---|
| Where it runs | In-process transformers model | External analyzer service over HTTP |
| Dependencies | `transformers` + `torch` (~1.5B-param model) | None (`aiohttp` is already a core dep) |
| Detection method | Token classification (NER) | Rule/regex + checksum + NER, per entity |
| Entity taxonomy | 8 fixed span categories | ~100 types across many locales, configurable |
| Languages | Primarily English | Configurable per analyzer deployment |
| On failure | Fails open (allows content) | Surfaced to `safety.allow_on_timeout` |

Pick `presidio` when you want broad, tunable entity coverage or a
dependency-light gateway; pick `privacy_filter` when you cannot run a second
service and want everything in one process.

Both are ordinary moderation providers, selected the same way as `openai`,
`anthropic`, or `ollama` moderation. When the safety layer is enabled, every user
message is checked before inference, and a message with PII detected above the
confidence threshold is blocked with a PII-specific refusal message.

Detected spans are reported as `ModerationResult` categories named
`pii.<category>` with the confidence score, so audit logs record which PII types
were seen. The naming is shared between the two providers, so switching between
them does not change the shape of your audit data.

> **Detection only, no redaction.** A flagged message is blocked, not masked.
> Presidio's anonymizer service is not used: ORBIT's safety contract
> (`ModeratorService.check_safety`) returns an allow/refuse decision and has no
> channel for handing modified text back into the pipeline. Redaction would be a
> larger change.

---

## Presidio

[Presidio](https://presidio.dataprivacystack.org/) is a mature open-source PII
engine combining regex patterns, checksum validation, context words, and NER.
ORBIT calls its **analyzer REST API** rather than importing its Python packages,
so spaCy and the ~600MB NER model stay inside the analyzer container and ORBIT
gains no new dependencies.

> Presidio moved from `microsoft/presidio` to the
> [Data Privacy Stack](https://github.com/data-privacy-stack/presidio)
> organisation. It is the same project — the repository was transferred, not
> forked — and the REST contract is unchanged. Only the container registry moved:
> `mcr.microsoft.com/presidio-analyzer` is no longer updated, and
> `ghcr.io/data-privacy-stack/presidio-analyzer` is current.

### Setup

1. Run the analyzer service:

   ```bash
   docker run -d -p 5002:3000 ghcr.io/data-privacy-stack/presidio-analyzer:latest
   ```

   Or as a compose service alongside ORBIT (pin a version in production):

   ```yaml
   presidio-analyzer:
     image: ghcr.io/data-privacy-stack/presidio-analyzer:latest
     ports:
       - "5002:3000"
     restart: unless-stopped
   ```

   Verify it: `curl localhost:5002/health`

2. Select the moderator in `config/guardrails.yaml`:

   ```yaml
   safety:
     enabled: true
     moderator: "presidio"
   ```

3. (Optional) Tune the provider in `config/moderators.yaml`:

   ```yaml
   moderations:
     presidio:
       base_url: "http://localhost:5002"   # PRESIDIO_ANALYZER_API_BASE overrides
       language: "en"
       score_threshold: 0.5
       request_timeout: 10
       batch_size: 8
       entities:
         - "CREDIT_CARD"
         - "EMAIL_ADDRESS"
         - "US_SSN"
   ```

`PRESIDIO_ANALYZER_API_BASE` takes precedence over `base_url`, matching the
convention other gateways use, so containerized deployments need no YAML edit.
The base URL may include or omit a trailing slash, and may carry a path prefix if
the analyzer sits behind a reverse proxy.

### Entity coverage

The default `entities` list is deliberately conservative — nine high-confidence
identifiers: `CREDIT_CARD`, `CRYPTO`, `EMAIL_ADDRESS`, `IBAN_CODE`,
`IP_ADDRESS`, `MEDICAL_LICENSE`, `PHONE_NUMBER`, `US_BANK_NUMBER`, `US_SSN`.

Presidio supports roughly 100 entity types, including country-specific
identifiers (`UK_NINO`, `DE_TAX_ID`, `IN_AADHAAR`, `AU_TFN`, …) and clinical
entities. Notably **not** enabled by default are `PERSON`, `LOCATION`,
`DATE_TIME`, and `NRP`, which fire constantly on ordinary prose and would block
most normal conversation. Add them only if you genuinely want that.

Ask your analyzer what it actually supports — coverage depends on the language
and which recognizers are loaded:

```bash
curl "localhost:5002/supportedentities?language=en"
```

ORBIT logs a warning at startup for any configured entity the running analyzer
does not support, so a typo or a locale gap surfaces immediately rather than
silently never matching. The full documented list is at
[supported entities](https://presidio.dataprivacystack.org/supported_entities/).

### Tuning

- **`score_threshold`** is passed to the analyzer and re-checked locally. Regex
  and checksum-backed entities score near 1.0; NER-backed ones vary far more.
- **`entities`** scopes both what is requested and what blocks. Entities the
  analyzer returns anyway are still scored and logged as `pii.<entity>`, just not
  flagged.
- **`language`** must be one the analyzer has an NLP model loaded for. Presidio
  instantiates recognizers per language, so a multi-language deployment needs the
  analyzer configured accordingly.
- **`batch_size`** bounds concurrent analyze calls; the analyzer has no batch
  endpoint, so batches fan out as parallel requests.

### Detection confidence in practice

Presidio's scores vary a lot by entity, and the `score_threshold` you pick
decides what actually blocks. Measured against the stock analyzer image:

| Input | Entity | Score | Blocked at 0.5? |
|:---|:---|:---|:---|
| `john.doe@example.com` | `EMAIL_ADDRESS` | 1.00 | yes |
| `4111111111111111` | `CREDIT_CARD` | 1.00 | yes |
| `DE89370400440532013000` | `IBAN_CODE` | 1.00 | yes |
| `1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2` | `CRYPTO` | 1.00 | yes |
| `my ssn 856-45-6789` | `US_SSN` | 0.85 | yes |
| `192.168.1.10` | `IP_ADDRESS` | 0.60 | yes |
| `my phone 212-456-7890` | `PHONE_NUMBER` | 0.75 | yes |
| `call me on 212-456-7890` | `PHONE_NUMBER` | 0.40 | **no** |

Two things worth knowing:

- **Context words matter.** Checksum- and pattern-validated entities score at or
  near 1.0, but recognizers that rely on surrounding context score 0.4 without it
  and 0.75 with it. A bare phone number therefore passes the 0.5 default. Lower
  `score_threshold` to 0.4 if you need to catch those - at the cost of more false
  positives, since several recognizers also emit 0.4 speculatively (any 11-digit
  number scores 0.4 as `US_BANK_NUMBER`).
- **Restricting `entities` suppresses cross-locale false positives.** The US phone
  number `+1 415 555 2671` matches `UK_NHS` at score **1.00** on the stock
  analyzer. Because `UK_NHS` is not in the default `entities` list it is scored
  and logged but does not block. Enabling every entity type would turn that into
  a hard block on a plain phone number - which is the main reason the default list
  is short.

### Failure behavior

Presidio is a network dependency, so this provider does **not** silently fail
open. Transport errors, non-200 responses, and malformed payloads are raised to
the safety layer, which applies the policy already in `config/guardrails.yaml`:

```yaml
safety:
  max_retries: 3
  retry_delay: 1.0
  allow_on_timeout: false   # false (default) = block when Presidio is unreachable
```

With `allow_on_timeout: false`, an unreachable analyzer means requests are
refused — a PII gate that stops enforcing when its backend dies is worse than
none. Set it to `true` if availability matters more than PII containment for your
deployment.

Note this differs from `privacy_filter`, which allows content through on any
error regardless of `allow_on_timeout`.

---

## Privacy Filter

`privacy_filter` runs OpenAI's
[privacy-filter](https://huggingface.co/openai/privacy-filter) model, a
bidirectional token-classification model (Apache 2.0) that labels PII spans in a
single forward pass. It runs fully on-premises through the `transformers`
library: no API key, no external calls, and a 128k-token context window so long
messages are processed without chunking.

### Detected categories

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

### Setup

1. Install the PyTorch/Hugging Face dependencies (transformers + torch):

   ```bash
   ./install/setup.sh --profile torch
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

The model (~1.5B parameters, 50M active) is downloaded from HuggingFace on first
startup and cached locally. GPU is not required; CPU inference is practical for
chat-message-sized inputs.

### Tuning

- **`threshold`** controls the precision/recall tradeoff. Lower values catch more
  PII but flag more false positives (e.g. public figures' names); higher values
  only block high-confidence detections.
- **`flag_categories`** scopes which PII types block a message. Categories
  removed from the list are still scored and logged (`pii.<category>`), just not
  flagged. For example, teams that only care about credential leakage can flag
  only `secret` and `account_number` while still auditing the rest.
- **`model`** accepts any HuggingFace token-classification model that emits the
  same label taxonomy, so a fine-tuned variant of privacy-filter can be dropped
  in for organization-specific label policies.

### Limitations

- **Fail-open.** Technical failures (model failed to load, inference error) allow
  content through with a warning in the logs rather than blocking traffic, and
  this is not governed by `safety.allow_on_timeout`. Monitor for
  `Moderation check failed, allowing content through` if PII leakage is a bigger
  risk than downtime for your deployment.
- **Model limitations.** The model is primarily English-trained; recall may drop
  on non-English text, non-Latin scripts, uncommon name conventions, and novel
  credential formats. Per the model card, it should be one layer in a
  privacy-by-design approach, not an anonymization guarantee.

---

## Verification

- Presidio unit tests: `server/tests/test_services/test_presidio_moderation_service.py`
- Privacy filter unit tests: `server/tests/test_services/test_privacy_filter_moderation.py`
- Scenario playbook: `server/tests/test_services/playbook-pii-moderation.md`
