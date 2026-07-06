# Manual/Integration Check: Cloud Secrets Management (AWS, Azure, GCP)

End-to-end verification of the pluggable secrets backends, using real cloud
secrets managers:

- **Part 1 — AWS Secrets Manager:** the fastest path if you already have an
  AWS session.
- **Part 2 — Azure Key Vault:** including the underscore → hyphen name
  translation.
- **Part 3 — GCP Secret Manager:** against a real project.

The automated unit tests (`test_secrets_backends.py`, `test_secrets_precedence.py`)
already cover the backend logic against `moto` (in-memory AWS) and in-memory
Azure/GCP fakes — get/miss/cache behavior, name translation, factory
selection, and the full resolution-precedence chain. This playbook exercises
the real network round-trips, credential resolution, and the fall-back
behavior (never fail-fast) that unit tests can't.

Prerequisites: ORBIT runs at `http://localhost:3000` with a `.env` you can
edit and a config-reload-triggering restart between steps (config is read at
startup).

## 0. Install the dependency profile

The cloud SDKs are opt-in:

```bash
./install/setup.sh --profile secrets-management   # boto3, azure-keyvault-secrets, azure-identity, google-cloud-secret-manager
```

Verify:

```bash
venv/bin/python -c "import boto3; print('boto3', boto3.__version__)"
venv/bin/python -c "import azure.keyvault.secrets as k; print('azure-keyvault-secrets ok')"
venv/bin/python -c "import google.cloud.secretmanager as s; print('google-cloud-secret-manager ok')"
```

If `secrets_management.provider` is set to `aws`/`azure`/`gcp` but the SDK is
missing, ORBIT does **not** fail startup — it logs a warning naming the
`secrets-management` profile and falls back to `.env`/environment-only
resolution for the whole config. That itself is scenario **T2** below (a
deliberate difference from the cloud file-storage backends, which do fail
fast — secrets resolution is designed to degrade gracefully since a startup
crash over a secrets-manager hiccup would be worse than temporarily falling
back to `.env`).

## Common setup: a canary variable

Throughout, use a placeholder that's easy to tell apart from its `.env`
value, e.g. a datasource password:

```bash
echo 'DATASOURCE_POSTGRES_PASSWORD=local-dotenv-value' >> .env
```

You'll create a cloud secret of the same name with a different value and
confirm the cloud value wins once the provider is enabled (proving
precedence), and that removing it falls back to the `.env` value again
(proving fallback).

---

# Part 1 — AWS Secrets Manager

## 1. Confirm your AWS session

```bash
aws configure list-profiles
export AWS_PROFILE=<your-profile>
aws sts get-caller-identity
```

## 2. Create the secret

```bash
aws secretsmanager create-secret \
  --name DATASOURCE_POSTGRES_PASSWORD \
  --secret-string 'from-aws-secrets-manager'
```

## 3. Configure ORBIT

In `config/config.yaml` (already ships with this block — just point
`ORBIT_SECRETS_PROVIDER` at `aws`):

```yaml
secrets_management:
  provider: "${ORBIT_SECRETS_PROVIDER:-env}"
  aws:
    region: "${AWS_REGION:-us-east-1}"
```

```bash
export ORBIT_SECRETS_PROVIDER=aws
export AWS_REGION=<your-region>
python3 server/main.py      # or ./bin/orbit.sh start
```

Startup log should include `Initialized AWSSecretsManagerBackend
(region=<your-region>)`.

## 4. Confirm precedence

Query the effective config (or just observe DB connectivity if
`internal_services.backend.type: postgres` is configured with this
password), or add a temporary debug read:

```bash
venv/bin/python -c "
import sys; sys.path.insert(0, 'server')
from config.config_manager import clear_config_cache, load_config
clear_config_cache()
cfg = load_config('config/config.yaml')
print(cfg['datasources']['postgres']['password'])
"
```

Confirm it prints `from-aws-secrets-manager`, **not** `local-dotenv-value` —
the cloud secret won even though `.env` also defines the name (**T1**).

## 5. Confirm fallback for names not in Secrets Manager

Pick any other `${VAR}`-backed value that has **no** matching AWS secret
(e.g. `ANTHROPIC_API_KEY`, still only in `.env`). Confirm it still resolves
from `.env` — only names actually present in Secrets Manager take the cloud
path; everything else is unaffected (**T3**).

---

# Part 2 — Azure Key Vault

## 6. Create the secret (note the hyphens)

Key Vault disallows underscores, so ORBIT translates them automatically.
Create the secret using **hyphens**:

```bash
az keyvault secret set \
  --vault-name <your-vault> \
  --name DATASOURCE-POSTGRES-PASSWORD \
  --value 'from-azure-key-vault'
```

## 7. Configure ORBIT

```bash
export ORBIT_SECRETS_PROVIDER=azure
export AZURE_KEY_VAULT_URL=https://<your-vault>.vault.azure.net/
az login    # so DefaultAzureCredential can resolve a token locally
python3 server/main.py
```

Startup log: `Initialized AzureKeyVaultBackend (vault_url=https://<your-vault>.vault.azure.net/)`.

## 8. Confirm the name translation and precedence

Repeat the debug read from step 4. Confirm it prints `from-azure-key-vault` —
proving ORBIT queried the vault for `DATASOURCE-POSTGRES-PASSWORD` (hyphens)
even though the config still says `${DATASOURCE_POSTGRES_PASSWORD}`
(underscores) (**T4**).

---

# Part 3 — GCP Secret Manager

## 9. Create the secret

```bash
echo -n 'from-gcp-secret-manager' | gcloud secrets create DATASOURCE_POSTGRES_PASSWORD \
  --data-file=- --project=<your-project-id>
```

## 10. Configure ORBIT

```bash
export ORBIT_SECRETS_PROVIDER=gcp
export GOOGLE_CLOUD_PROJECT=<your-project-id>
gcloud auth application-default login
python3 server/main.py
```

Startup log: `Initialized GCPSecretManagerBackend (project=<your-project-id>)`.

## 11. Confirm precedence

Repeat the debug read from step 4. Confirm it prints `from-gcp-secret-manager`.

---

## Additional scenarios (failure modes & guarantees)

### T1. Secrets manager wins over a conflicting `.env` value

With any provider enabled and a secret of the same name present in both
places, the cloud value is used (steps 4/8/11 above). This is the opposite
precedence from a naive "env first" design — deliberate, so a stale local
`.env` can't silently shadow a hardened secret.

### T2. Missing SDK does not crash startup

In a venv **without** the `secrets-management` profile, set
`ORBIT_SECRETS_PROVIDER=aws` (or `azure`/`gcp`) and start ORBIT. Confirm:
- Startup **succeeds** (unlike the cloud file-storage backends, which fail
  fast on a missing SDK).
- The log includes a warning: `Failed to initialize secrets backend, falling
  back to environment variables only: ...` naming the missing package.
- All `${VAR}` placeholders resolve from `.env`/environment exactly as if
  `provider: env` had been set.

### T3. Unreachable backend / bad credentials does not crash startup

Set a wrong region/vault URL/project, or revoke credentials, then start
ORBIT. Confirm the same graceful-fallback warning as T2 (not a stack trace or
failed startup) and that the server otherwise starts and serves requests
using `.env` values.

### T4. Per-secret miss falls through, not the whole config

With a provider enabled and only **some** secrets created in the cloud
(step 5), confirm variables without a matching cloud secret still resolve
from `.env`/`:-default` — a single missing secret doesn't disable resolution
for the rest of the config.

### T5. Unknown provider value rejected

Set `secrets_management.provider: "vault"` and start ORBIT. Confirm a
`ValueError: Unknown secrets_management.provider 'vault'. Valid options: env,
aws, azure, gcp.` in the startup logs — never a silent fallback to `env`.

### T6. Repeated config reload does not re-hit the cloud API

Trigger an admin adapter reload twice in a row (e.g. toggle an adapter via
the admin panel, or call the reload endpoint) while a provider is enabled.
Confirm (via the cloud provider's own request logs/CloudTrail, or by
temporarily adding a log line in `get_secret`) that the same secret name is
only fetched once — the in-memory cache inside the backend instance persists
across reloads (`clear_config_cache()` is the only thing that resets it,
used by tests/full restarts).

### T7. Default (`env`) provider is unaffected

Unset `ORBIT_SECRETS_PROVIDER` (or set it to `env`) and confirm ORBIT starts
and resolves every `${VAR}` from `.env`/environment exactly as before this
feature existed — no `secrets-management` profile required, no behavior
change.

---

## 12. Run the automated checks

```bash
ruff check server/services/secrets/ server/config/config_manager.py
cd server && ../venv/bin/python -m pytest tests/secrets/test_secrets_backends.py tests/test_config/test_secrets_precedence.py tests/test_config/test_config_manager_internals.py -v
```

Expect all green: `test_secrets_backends.py` (AWS via moto + Azure/GCP via
in-memory fakes + factory selection + caching), `test_secrets_precedence.py`
(the full secrets → env → default resolution chain), and
`test_config_manager_internals.py` (existing `_process_env_vars` behavior
unchanged when no backend is supplied). The cloud tests `importorskip` when
`moto` / `azure-keyvault-secrets` / `google-cloud-secret-manager` are absent,
so they skip cleanly rather than fail in a base install.

---

## Troubleshooting

- **Server starts but a secret isn't resolving from the cloud:** check the
  startup logs for a per-variable warning
  (`Secrets backend lookup failed for '...'`) or a whole-backend warning
  (`Failed to initialize secrets backend`). Both mean it silently fell back
  to `.env` — this is by design (T2/T3), not a bug, but it means the secret
  name/permissions need fixing.
- **AWS: `AccessDeniedException` on `get_secret_value`:** the identity needs
  `secretsmanager:GetSecretValue` (and `secretsmanager:ListSecrets` for the
  startup connectivity check) on the target secret/ARN.
- **Azure: secret not found even though it exists:** check the name uses
  hyphens, not underscores — `DATASOURCE_POSTGRES_PASSWORD` in config maps to
  `DATASOURCE-POSTGRES-PASSWORD` in the vault (T4).
- **Azure: `Forbidden` / `AuthorizationFailed`:** the identity needs a Key
  Vault "Secrets User" role (or the legacy access-policy equivalent) with
  `get`/`list` permissions.
- **GCP: `PermissionDenied` on `access_secret_version`:** the identity needs
  the "Secret Manager Secret Accessor" role on the project/secret.
- **Values still coming from `.env` after enabling a provider:** confirm
  `ORBIT_SECRETS_PROVIDER` is actually set in the environment the server
  process sees (not just your shell) and that the server was restarted —
  the provider and connection settings are read once at startup.
- **Inspect what's cached:** the backend caches both hits and misses for the
  process lifetime; to force a fresh lookup during testing, restart the
  server (or call `clear_config_cache()` in a Python shell against a running
  test harness).
