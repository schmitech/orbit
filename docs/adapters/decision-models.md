# Decision Model Adapters

Decision models (also called "System One" or Jev-style models) are a different kind of model from the chat LLMs used by most ORBIT adapters. They **do not generate text**. You give them some context (the `state`) and a set of typed questions, and they return typed answers with a probability for every candidate. Because they only score a fixed set of answers instead of writing a reply, they are fast (roughly 100 ms per decision on a local GPU or Apple Silicon) and predictable. That makes them a good fit for light, real-time decisions inside an application: ticket triage, content moderation, request routing, and similar checks.

ORBIT exposes these models through the `decision_model` adapter type, with two providers:

| Provider | Where it runs | Models | How ORBIT calls it |
|----------|---------------|--------|--------------------|
| `ollama` | Local, Ollama 0.35+ | `nimble` (9B, Bespoke Labs), `tev1` (4B), `tev1:0.8b` (0.8B, Together AI) | Plain HTTP to `POST /v1/systemone` (no extra dependency) |
| `typesafe` | Hosted by [TypeSafe](https://docs.typesafe.ai) | `jev-latest` (resolves to a version such as `jev-1.13.0`) | The official `typesafe-sdk` (`AsyncTypeSafeClient`) |

Both providers speak the same System One protocol, so an adapter can switch between local and hosted by changing one line.

---

## Quick Comparison with Chat Adapters

| | Chat / passthrough adapters | Decision model adapters |
|---|---|---|
| **Adapter type** | `passthrough`, `retriever`, … | `decision_model` |
| **Output** | Generated text | Typed answers + probabilities (JSON) |
| **Latency** | Seconds, grows with output length | Around 100 ms, fixed output size |
| **Provider config** | `config/inference.yaml` | `config/decision.yaml` |
| **Pipeline step** | `LLMInferenceStep` | `DecisionModelStep` (`LLMInferenceStep` is skipped) |
| **Streaming** | Token by token | One final event carrying the whole decision |

---

## Question Types

Each adapter declares a set of named questions. There are three types:

| Type | What it answers | `criteria` | Answer fields |
|------|-----------------|------------|---------------|
| `choice` | Pick one option from a list | **Required**: a mapping of option name to description | `choice`, `probabilities`, `confidence` |
| `noul` | A yes/no condition | Optional | `noul`, the probability (0–1) that the answer is yes |
| `score` | An ordered rubric | **Required**: a list of at least 2 levels, lowest first | `score` (the expected level), `legend`, `probabilities`, `confidence` |

Every question also needs non-empty `instructions`. ORBIT checks questions before calling the provider and returns a clear error if one is invalid.

Example request sent to the provider for the `ticket-triage` adapter:

```json
{
  "model": "nimble",
  "state": {"ticket": "I was charged twice. Please refund the extra payment."},
  "questions": {
    "team": {
      "type": "choice",
      "instructions": "Which team should handle this ticket?",
      "criteria": {"billing": "Payments and refunds", "technical": "Bugs and integrations", "other": "None of the above"}
    },
    "refund_requested": {"type": "noul", "instructions": "Does the customer explicitly ask for a refund?"},
    "urgency": {"type": "score", "instructions": "How urgent is this ticket?", "criteria": ["Routine", "Soon", "Urgent"]}
  }
}
```

And the typed result:

```json
{
  "model": "nimble",
  "answers": {
    "team": {"type": "choice", "choice": "billing",
             "probabilities": {"billing": 0.985, "technical": 0.012, "other": 0.003}, "confidence": 0.922},
    "refund_requested": {"type": "noul", "noul": 0.997},
    "urgency": {"type": "score", "score": 0.815, "legend": {"0": "Routine", "1": "Soon", "2": "Urgent"},
                "probabilities": {"0": 0.378, "1": 0.429, "2": 0.193}, "confidence": 0.046}
  },
  "usage": {"input_tokens": 841, "output_tokens": 4}
}
```

---

## Setup

### 1. Configure the providers (`config/decision.yaml`)

`config/config.yaml` imports this file. It sets the default provider and each provider's connection settings:

```yaml
decision:
  provider: "ollama"   # Default decision provider: ollama, typesafe
  enabled: true        # Whether decision models are enabled globally

decision_models:
  ollama:
    enabled: true
    base_url: "http://localhost:11434"
    model: "nimble"               # nimble (9B), tev1 (4B), tev1:0.8b (0.8B)
    timeout:
      connect: 5000
      total: 30000                # milliseconds
    retry:
      enabled: true
      max_retries: 2
      initial_wait_ms: 500
      max_wait_ms: 5000
      exponential_base: 2

  typesafe:
    enabled: true
    api_key: ${TYPESAFE_API_KEY}
    base_url: "https://api.typesafe.ai"
    model: "jev-latest"
    timeout:
      total: 30000                # milliseconds (converted to seconds for the SDK)
```

- **Ollama retries**: only connection errors, timeouts, HTTP 429 and HTTP 5xx are retried. Any other error (for example a 404 for a model that isn't pulled, or a 422 for an invalid question) fails right away and returns the provider's own error message.
- **TypeSafe retries**: handled by the SDK.
- Setting `decision.enabled: false` turns off every decision provider. Setting `decision_models.<provider>.enabled: false` turns off just that one.

### 2. Get a model

**Local (Ollama):**

```bash
ollama pull nimble        # 9B, best accuracy
ollama pull tev1:0.8b     # 0.8B, fastest
```

Check that Ollama is serving decision models:

```bash
curl http://localhost:11434/v1/systemone -d '{
  "model": "tev1:0.8b",
  "state": {"ticket": "I was charged twice."},
  "questions": {"refund": {"type": "noul", "instructions": "Does the customer ask for a refund?"}}
}'
```

**Hosted (TypeSafe):** create a key at [console.typesafe.ai/keys](https://console.typesafe.ai/keys) and add it to `.env`:

```bash
TYPESAFE_API_KEY=your-key
```

The `typesafe-sdk` package is part of the default install profile (`install/dependencies.toml`). To add it to an existing environment:

```bash
pip install "typesafe-sdk>=0.7.2,<0.8"
```

If the SDK isn't installed, ORBIT skips the `typesafe` provider at startup and `ollama` keeps working. If the API key is missing, requests to a TypeSafe adapter fail with `TypeSafe API key not configured (set TYPESAFE_API_KEY)`.

### 3. Enable the adapters

The example adapters live in `config/adapters/decision.yaml`. Enable them in `config/adapters.yaml`:

```yaml
import:
  - "adapters/decision.yaml"
```

Then create an API key for each adapter you want to call (see [API Keys](../api-keys.md)).

---

## Adapter Configuration

```yaml
adapters:
  - name: "ticket-triage"
    enabled: true
    type: "decision_model"
    datasource: "none"
    adapter: "multimodal"
    implementation: "implementations.passthrough.multimodal.MultimodalImplementation"
    decision_provider: "ollama"      # ollama | typesafe (defaults to decision.provider)
    model: "nimble"                  # optional; defaults to the provider's configured model
    capabilities:
      retrieval_behavior: "none"
      formatting_style: "clean"
      supports_threading: false
      supports_session_tracking: false
    config:
      state_key: "ticket"            # the user message becomes {"ticket": "<message>"}; default "input"
      allow_question_override: true  # let a request send its own questions (default false)
      questions:
        team:
          type: "choice"
          instructions: "Which team should handle this ticket?"
          criteria:
            billing: "Payments, invoices, charges and refunds"
            technical: "Bugs, errors, outages and integrations"
            account: "Login, passwords, profile and account settings"
            other: "None of the above"
        refund_requested:
          type: "noul"
          instructions: "Does the customer explicitly ask for a refund?"
        urgency:
          type: "score"
          instructions: "How urgent is this ticket?"
          criteria: ["Routine", "Soon", "Urgent"]
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Must be `decision_model` |
| `decision_provider` | No | Provider for this adapter. Defaults to `decision.provider` in `decision.yaml` |
| `model` | No | Model override for this adapter. Defaults to the provider's `model` |
| `config.questions` | Yes | The questions to ask (see [Question Types](#question-types)) |
| `config.state_key` | No | Key the plain-text message is stored under in `state`. Default: `input` |
| `config.allow_question_override` | No | When `true`, a request can replace the questions for that call. Default: `false` |

No `inference_provider` is needed: decision adapters never call a chat LLM.

### Shipped examples

| Adapter | Provider / model | Questions |
|---------|------------------|-----------|
| `ticket-triage` | `ollama` / `tev1:0.8b` | `team` (choice), `refund_requested` (noul), `urgency` (score). Question override enabled |
| `content-moderation` | `typesafe` / `jev-latest` | `category` (choice), `needs_human_review` (noul), `severity` (score) |
| `ticket-triage-typesafe` | `typesafe` / `jev-latest` | Same questions as `ticket-triage`, answered by TypeSafe |
| `skill-router` | `ollama` / `tev1:0.8b` | `skill` (choice across ORBIT skills), `needs_retrieval` (noul) |

`skill-router` is an example configuration only. ORBIT's built-in skill router doesn't use it yet, but an application can call it as a fast routing step before deciding which adapter to send a request to.

For a live, human-vs-AI booth demo of `ticket-triage` over the message queue, see [Triage Rush](../../examples/triage-rush-mq/README.md).

---

## Calling a Decision Adapter

### Plain text

The message text becomes the state (`{"<state_key>": "<message>"}`):

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <ticket-triage API key>" \
  -H "X-Session-ID: demo-session" \
  -d '{"messages":[{"role":"user","content":"I was charged twice for my subscription, please refund the extra payment."}],
       "stream": false}'
```

### Structured state and per-request questions

Send the message as a JSON object with a `state` object. This lets you pass several fields at once, and, if the adapter allows it, your own questions:

```json
{
  "state": {"ticket": "Your API returns 500 on every POST since this morning", "customer_tier": "enterprise"},
  "questions": {
    "is_outage": {"type": "noul", "instructions": "Is this a service outage?"}
  }
}
```

- If `allow_question_override` is `false`, ORBIT ignores `questions` (and logs a warning) and uses the adapter's questions.
- A JSON message with no `state` object is treated as plain text.

### Response

The response text is the `answers` JSON, so a chat UI shows the decision directly. Programs should read the typed `decision` field instead, which holds the full `{model, answers, usage}` result:

| Endpoint | Where to find the decision |
|----------|----------------------------|
| `POST /v1/chat` (non-streaming) | `decision` in the response body |
| `POST /v1/chat` (streaming) | `decision` on the final `{"done": true, ...}` event |
| `POST /v1/chat/completions` | `orbit.decision` (streaming: on the final chunk) |
| Message queue (`orbit.requests`) | `decision` on the `completed` reply envelope |

```json
{
  "response": "{\n  \"team\": {\"type\": \"choice\", \"choice\": \"billing\", ...}\n}",
  "decision": {
    "model": "nimble",
    "answers": {
      "team": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.98, "technical": 0.01, "account": 0.005, "other": 0.005}, "confidence": 0.92},
      "refund_requested": {"type": "noul", "noul": 0.96},
      "urgency": {"type": "score", "score": 0.98, "legend": {"0": "Routine", "1": "Soon", "2": "Urgent"}, "probabilities": {"0": 0.3, "1": 0.42, "2": 0.28}, "confidence": 0.05}
    },
    "usage": {"input_tokens": 830, "output_tokens": 4}
  },
  "model": "nimble"
}
```

`model` reports the model that actually answered. For TypeSafe that is the resolved version (for example `jev-1.13.0`). Token usage is recorded like any other request (`call_type: "decision"`), so it shows up in usage and cost tracking.

### Reading the answers

- **choice**: use `choice` as the decision. `confidence` tells you how sure the model is, so you can send low-confidence cases to a person.
- **noul**: compare `noul` against a threshold that suits your use case, for example `> 0.5` to act, or `> 0.9` for high-stakes actions.
- **score**: `score` is the expected level on a `0 … N-1` scale. `legend` maps each index to its label, and `probabilities` gives the full distribution.

---

## How It Works

```
User request
    ↓
RequestContextBuilder: resolves adapter (type: decision_model)
    ↓
DecisionModelStep
    ├─ parse input: plain text → {state_key: message}, or a JSON {"state", "questions"} message
    ├─ validate questions (types, instructions, criteria)
    ├─ resolve provider: runtime override → adapter decision_provider → decision.provider
    ├─ resolve model:    runtime override → adapter model → provider default
    └─ DecisionService.decide(state, questions, model)
          ├─ ollama:   POST {base_url}/v1/systemone
          └─ typesafe: AsyncTypeSafeClient.system_one(...)
    ↓
context.decision = {model, answers, usage}; context.response = answers JSON
    ↓
LLMInferenceStep skipped → done event / result carries `decision`
```

Decision services are cached per provider and preloaded when an adapter sets `decision_provider`. If preloading fails (for example Ollama isn't running), startup continues and the service is loaded on the first request.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `Ollama decision error (HTTP 404): model "nimble" not found` | Run `ollama pull nimble`, or set the adapter's `model` to a model you have pulled |
| `Ollama decision error (HTTP 404)` even for a pulled model | `/v1/systemone` needs Ollama 0.35+. Check with `ollama --version` |
| `HTTP 503: …` after retries | Ollama is overloaded or still loading the model. The first request after a model loads is slower |
| `Decision provider 'typesafe' is unavailable: TypeSafe API key not configured` | Set `TYPESAFE_API_KEY` in `.env` and restart |
| `Decision provider 'typesafe' is unavailable` right after startup | `typesafe-sdk` isn't installed, or `decision_models.typesafe.enabled` is `false` |
| `Choice question 'x' requires a non-empty 'criteria' mapping…` | Fix the question definition (see [Question Types](#question-types)) |
| Request questions are ignored | Set `allow_question_override: true` on the adapter |

---

## Implementation Reference

| Component | File | Role |
|-----------|------|------|
| Service interface | `server/ai_services/services/decision_service.py` | `DecisionService.decide()`; config under `decision_models` |
| Ollama provider | `server/ai_services/implementations/decision/ollama_decision_service.py` | HTTP client for `/v1/systemone`, restricted retries |
| TypeSafe provider | `server/ai_services/implementations/decision/typesafe_decision_service.py` | `typesafe-sdk` client, question conversion, response normalization |
| Service registration | `server/ai_services/registry.py` | `register_decision_services()` |
| Service cache | `server/services/cache/decision_cache_manager.py` | Per-provider caching; used by `DynamicAdapterManager.get_decision_service()` |
| Pipeline step | `server/inference/pipeline/steps/decision_model.py` | `DecisionModelStep`, `validate_questions()` |
| Pipeline wiring | `server/inference/pipeline/pipeline.py` | `DecisionModelStep` inserted before `LLMInferenceStep` |
| Adapter registration | `server/adapters/__init__.py` | Registers the `decision_model` type in `ADAPTER_REGISTRY` |
| Output plumbing | `server/services/chat_handlers/streaming_events.py`, `streaming_handler.py`, `response_processor.py` | `decision` on done events and results |
| Provider config | `config/decision.yaml` | Default provider, per-provider settings |
| Example adapters | `config/adapters/decision.yaml` | `ticket-triage`, `content-moderation`, `skill-router` |
| Tests | `server/tests/test_decision/` | Services, step, registry, output plumbing, SDK contract, adapter configs |
