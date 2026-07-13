# GPU Validation Playbook — privacy_filter PII moderation (PR #166)

Goal: **prove the `openai/privacy-filter` integration actually detects PII in
production**, on a real GPU box (AWS), before trusting/merging it. The shipped
unit tests all mock the model, so they cannot catch the one real risk:

> The model emits **BIOES** labels (`B-`, `I-`, `E-`, `S-`). The transformers
> pipeline's `aggregation_strategy="simple"` only strips `B-`/`I-` prefixes, so
> single-token PII tagged `S-private_email` (a bare email/phone/account number)
> can surface as `entity_group="S-private_email"` — which the service silently
> drops. Multi-word PII would still work, masking the gap.

The decisive check is **Step 4**. Everything before it is setup.

---

## 0. Provision the box

Any CUDA GPU instance works; the model is ~1.5B params (50M active), so even a
small GPU (e.g. `g5.xlarge`, A10G) is plenty. CPU works too but is slow.

Requirements:
- Python 3.12 (project venv target)
- **torch ≥ 2.4** with CUDA (transformers 5.x disables torch < 2.4)
- Disk for the model download (~3–6 GB, F32/BF16)

## 1. Get the code (the PR branch)

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit
git remote add rhiannalitchfield https://github.com/rhiannalitchfield/orbit.git
git fetch rhiannalitchfield feat/166-privacy-filter-moderation:pr-166
git checkout pr-166
```

> Or, if you push your local `test-pr-166` branch somewhere, clone that instead —
> it's `main` + this PR.

## 2. Install deps (huggingface profile = transformers + torch)

```bash
./install/setup.sh --profile huggingface
# Verify torch sees the GPU:
./venv/bin/python -c "import torch; print('cuda:', torch.cuda.is_available(), torch.__version__)"
```

Expect `cuda: True`. If `False`, install the CUDA build of torch for your driver
before continuing (otherwise you're only validating CPU behavior).

## 3. Sanity: mocked unit tests still green

```bash
./venv/bin/python -m pytest server/tests/test_services/test_privacy_filter_moderation.py -v
```

All should pass. This only confirms the span→result plumbing — not the model.

---

## 4. ⭐ Decisive check: real model, real detections

This drives the **actual** `PrivacyFilterModerationService.moderate_content`
path against the downloaded model, with test cases that isolate the BIOES risk
(single-token vs multi-token PII).

```bash
./venv/bin/python server/tests/test_services/validate_privacy_filter_model.py
```

First run downloads the model (a few minutes). Then read the output:

**PASS looks like:**
```
=== model id2label (ground truth) ===
['B-account_number', ..., 'S-secret', 'O']         # raw labels are BIOES
...
[OK] (single-token) 'alice.smith@example.com'
    flagged=True  categories={'pii.private_email': 0.99}
...
RESULT: PASS. All expected PII detected, no false positives...
```
→ The pipeline's aggregation collapses BIOES correctly for THIS model. Ship it.

**FAIL looks like:**
```
[!] These raw labels are NOT bare categories ... the service will DROP them:
    ['E-private_email', 'S-private_email', 'S-secret', ...]
[MISS] (single-token) 'alice.smith@example.com'
    flagged=False  categories={}
    raw pipeline entity_groups: [('S-private_email', 0.99, 'alice.smith@example.com')]
...
[OK] (multi-token) 'Hi, my email is alice.smith@example.com'   # <- longer text still works
RESULT: N failure(s)...
```
→ Bug confirmed. Single-token PII is invisible to the filter. **Do not merge as-is.**

### If Step 4 fails — the fix

Normalize the BIOES prefix where labels are read. In
`server/ai_services/implementations/moderation/privacy_filter_moderation_service.py`,
`_spans_to_result`, replace the raw label read with a stripped one:

```python
import re
_BIOES = re.compile(r'^[BIES]-')
...
raw = span.get('entity_group')
label = _BIOES.sub('', raw) if raw else raw
```

(Everything downstream — `PRIVACY_FILTER_CATEGORIES` membership, `max()` per
category — then works unchanged.) Re-run Step 4 until it's PASS. If even the raw
`entity_group` values look wrong (spans split mid-entity, garbage scores), the
model likely needs the model card's constrained BIOES span decoding rather than
`aggregation_strategy="simple"` — a larger change; flag it back to the author.

---

## 5. End-to-end through the server (the PR's own playbook)

Once Step 4 passes, run the shipped functional playbook to confirm the guardrail
integration, config knobs, and fail-open path:

→ `server/tests/test_services/playbook-pii-moderation.md`

**Add these short/single-token messages** to its Step 2 (they're the ones Step 4
flagged as risky — make sure the *running server* blocks them too):

> alice.smith@example.com

> 416-555-0192

> 000123456789

Each should be blocked with the moderation refusal, not answered.

---

## Decision

| Step 4 result | Verdict |
|---|---|
| PASS + Step 5 blocks short PII | ✅ Correct in production — safe to merge |
| Step 4 MISS on single-token only | ⚠️ BIOES leak — apply the fix, re-validate |
| Model won't load / arch error | ⛔ Needs `trust_remote_code` or custom loader — back to author |

> Reminder: this moderator **fails open** — if the model can't load, PII passes
> through unfiltered (only a warning is logged). For a privacy control that's a
> policy call worth confirming with the team; consider alerting on
> `Privacy filter initialization failed` / `Moderation check failed`.
