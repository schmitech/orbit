# Manual/Integration Check: PII Moderation (presidio)

End-to-end verification of the `presidio` moderation provider, using a real
running server, a real Presidio analyzer container, and the orbitchat UI. The
provider detects personally identifiable information (PII) in user messages by
calling the Presidio analyzer's REST API, so no Python dependencies or local
models are involved.

The automated unit tests (`test_presidio_moderation_service.py`) already cover
configuration parsing, base-URL normalization, response mapping, batch ordering,
error propagation, and lifecycle against a fake HTTP session. This playbook
exercises the real analyzer, the guardrail integration in the chat pipeline, the
operational config knobs (`score_threshold`, `entities`, `language`), and the
failure policy — which is where this provider deliberately differs from
`privacy_filter`.

Prerequisites:

- Docker running. No ORBIT dependency profile is needed — the HTTP transport adds
  no Python packages.
- ORBIT runs at `http://localhost:3000` with an API key bound to any
  chat-capable adapter.
- orbitchat UI running against the server (`cd clients/orbitchat && npm run dev`).

> Reference values in this playbook were measured against
> `ghcr.io/data-privacy-stack/presidio-analyzer:latest`. Scores are
> model/version dependent; if a step disagrees, check the raw score with the
> `curl` in step 1 before assuming a regression.

## 0. Start the analyzer

```bash
docker run -d --name presidio-analyzer -p 5002:3000 \
  ghcr.io/data-privacy-stack/presidio-analyzer:latest
```

The image is ~1-2GB and the first pull takes a few minutes. Wait for health:

```bash
curl -s localhost:5002/health
# Presidio Analyzer service is up
```

> Presidio moved from `microsoft/presidio` to the Data Privacy Stack org. The
> `mcr.microsoft.com/presidio-analyzer` image still exists but is no longer
> updated — use the `ghcr.io` one above.

## 1. Confirm the analyzer directly (before involving ORBIT)

This isolates analyzer problems from ORBIT problems.

```bash
curl -s "localhost:5002/supportedentities?language=en"
```

Expected: a JSON array including all nine ORBIT defaults — `CREDIT_CARD`,
`CRYPTO`, `EMAIL_ADDRESS`, `IBAN_CODE`, `IP_ADDRESS`, `MEDICAL_LICENSE`,
`PHONE_NUMBER`, `US_BANK_NUMBER`, `US_SSN`.

```bash
curl -s -X POST localhost:5002/analyze -H 'Content-Type: application/json' \
  -d '{"text":"email me at john.doe@example.com","language":"en","score_threshold":0.0}'
```

Expected: one `EMAIL_ADDRESS` result with `score` 1.0. Use this call with
`score_threshold: 0.0` throughout the playbook whenever you want to see what the
analyzer actually detected, including detections ORBIT filters out.

## 2. Enable Presidio moderation in ORBIT

In `config/guardrails.yaml`:

```yaml
safety:
  enabled: true
  moderator: "presidio"
  allow_on_timeout: false
```

The `moderations.presidio` block in `config/moderators.yaml` works as shipped.
Restart ORBIT and confirm:

```
Safety service using moderator: presidio
```

There should be **no** warning about unsupported entities. If you see
`Presidio analyzer at ... does not support configured entities [...]`, either the
analyzer is an older image or an entity name in your config is misspelled.

## 3. Baseline: benign message passes

In orbitchat, send:

> What are your support hours?

Expected: a normal answer. No moderation warnings in the server log.

## 4. High-confidence identifiers are blocked

Send each of the following as separate messages:

> email me at john.doe@example.com

> my card is 4111111111111111

> transfer to IBAN DE89370400440532013000

> my ssn 856-45-6789

> my wallet is 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2

Expected: each is blocked with a PII-specific refusal naming the entity, e.g.

> I cannot process messages containing an email address. Please remove it and try again.

The server log shows `🛑 MODERATION BLOCKED: Query was flagged as UNSAFE by
presidio moderator` and the flagged categories: `pii.email_address` (1.0),
`pii.credit_card` (1.0), `pii.iban_code` (1.0), `pii.us_ssn` (0.85),
`pii.crypto` (1.0).

## 5. Names and locations are NOT blocked by default

Send:

> My name is John Smith and I live in Seattle

Expected: a normal answer. `PERSON` and `LOCATION` are deliberately absent from
the default `entities` list because they fire on ordinary conversation. Confirm
the analyzer did detect them, and that ORBIT chose not to act:

```bash
curl -s -X POST localhost:5002/analyze -H 'Content-Type: application/json' \
  -d '{"text":"My name is John Smith and I live in Seattle","language":"en","score_threshold":0.0}'
```

Expected: `PERSON` and `LOCATION` results present in the raw analyzer output.

## 6. Context words change what blocks

Send these two messages:

> call me on 212-456-7890

> my phone 212-456-7890

Expected: the **first passes** and the **second is blocked**. Presidio's phone
recognizer scores 0.4 without a nearby context word and 0.75 with one, and the
default `score_threshold` is 0.5. This is the most surprising behavior of the
provider and worth confirming rather than assuming.

To catch context-free numbers, set in `config/moderators.yaml`:

```yaml
  presidio:
    score_threshold: 0.4
```

Restart and resend `call me on 212-456-7890`.

Expected: now blocked, with the refusal naming a phone number and
`pii.phone_number` (0.4) in the log. Note the tradeoff — at 0.4 several
recognizers emit speculative matches (any 11-digit number scores 0.4 as
`US_BANK_NUMBER`). Reset `score_threshold: 0.5` afterwards.

## 7. Entity scoping suppresses cross-locale false positives

Send:

> call me on +1 415 555 2671

Expected: passes. Now look at what the analyzer actually found:

```bash
curl -s -X POST localhost:5002/analyze -H 'Content-Type: application/json' \
  -d '{"text":"call me on +1 415 555 2671","language":"en","score_threshold":0.0}'
```

Expected: a `UK_NHS` match at score **1.0** on this US phone number, alongside a
0.4 `PHONE_NUMBER`. Because `UK_NHS` is not in the configured `entities` list,
ORBIT scores and logs it but does not block.

Now demonstrate the cost of enabling everything — add `UK_NHS` to `entities`,
restart, and resend the same message.

Expected: now blocked as a false positive. This is why the shipped `entities`
list is short. Remove `UK_NHS` afterwards.

## 8. Reported-but-not-flagged categories

With the default config, send:

> server is at 192.168.1.10 and my name is John Smith

Expected: blocked for `pii.ip_address` (0.6). At DEBUG level the logged category
scores include only entities the analyzer returned for the configured list —
`PERSON` is not requested, so it will not appear. To see everything the analyzer
would report, temporarily add `PERSON` to `entities` and compare; it will then be
both scored and flagged.

## 9. Failure policy: blocking when the analyzer is down

**This is where `presidio` differs from `privacy_filter`.** With
`allow_on_timeout: false` (the default) in `config/guardrails.yaml`:

```bash
docker stop presidio-analyzer
```

Send:

> email me at john.doe@example.com

Expected: the message is **blocked** with

> I cannot assist with that request due to a service issue. Please try again later.

The server log shows `❌ Error in moderator safety check` for each retry, then
`🚫 MODERATION FAILED: Blocking query after multiple failed attempts`. A PII gate
that stops enforcing when its backend dies is worse than none, so this provider
raises to the safety layer rather than failing open.

Note that ORBIT still **starts** with the analyzer down — startup logs
`Could not reach Presidio analyzer at ... during initialization` as a warning and
continues, so a restart ordering problem does not take the server down.

## 10. Failure policy: allowing when availability matters more

In `config/guardrails.yaml`, set `allow_on_timeout: true`, restart, and with the
analyzer still stopped resend the same message.

Expected: the message is **allowed through** and answered normally, with
`⚠️ MODERATION ERROR: Allowing query through due to allow_on_timeout setting` in
the log.

Restart the analyzer and restore `allow_on_timeout: false`:

```bash
docker start presidio-analyzer
```

## 11. Language handling

In `config/moderators.yaml`, set `language: "de"` and restart. Send:

> email me at john.doe@example.com

Expected: the message is blocked with the service-issue refusal (with
`allow_on_timeout: false`), because the stock image has no German NLP model
loaded — the analyzer returns HTTP 500
(`No matching recognizers were found to serve the request`) and the provider
raises rather than reporting "no PII found". The startup log warns
`Presidio /supportedentities returned HTTP 500; skipping entity validation`.

This is the important case: a language misconfiguration fails loudly instead of
silently passing every message. Restore `language: "en"`.

## 12. Environment variable override

Stop ORBIT, set an intentionally wrong base URL in `config/moderators.yaml`
(e.g. `base_url: "http://localhost:9999"`), then start ORBIT with:

```bash
PRESIDIO_ANALYZER_API_BASE=http://localhost:5002 python3 server/main.py
```

Expected: moderation works normally — the environment variable takes precedence
over YAML. Restore `base_url: "http://localhost:5002"` afterwards.

## 13. No regressions for other moderators

Set `safety.moderator` back to your previous provider (e.g. `privacy_filter`,
`openai`, or `ollama`), restart, and send one benign and one unsafe message.

Expected: behavior unchanged from before this feature. Note that
`privacy_filter` fails open on error regardless of `allow_on_timeout`, so its
behavior in an outage differs from step 9 by design.

## Cleanup

```bash
docker rm -f presidio-analyzer
```

Restore `config/guardrails.yaml` and `config/moderators.yaml` to their original
values and restart.
