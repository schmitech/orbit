# Cloud Secrets Management Setup

This guide walks through wiring ORBIT's `${VAR_NAME}` config placeholders up to a cloud
secrets manager — AWS Secrets Manager, Azure Key Vault, or GCP Secret Manager — instead of
(or in addition to) a local `.env` file, so production credentials don't have to live in
plaintext on disk.

For the config schema reference see [Configuration Guide → Secrets Management](../configuration.md#secrets-management).

## How it works

ORBIT resolves every `${VAR_NAME}` and `${VAR_NAME:-default}` placeholder in `config/*.yaml`
through `secrets_management.provider` in `config/config.yaml`:

- **`env`** (default) — resolves from `.env` / the process environment only. No setup, no
  behavior change from before this feature existed.
- **`aws` / `azure` / `gcp`** — the cloud provider is consulted **first** for each
  placeholder name. Only names it doesn't have fall back to `.env`/environment, then to any
  `${VAR:-default}`. This ordering means a stale or leaked local `.env` value can't silently
  shadow a hardened secret.

**Naming**: each `${VAR_NAME}` is looked up as a secret of the exact same name — e.g.
`${DATASOURCE_POSTGRES_PASSWORD}` looks up a secret named `DATASOURCE_POSTGRES_PASSWORD` in
AWS Secrets Manager or GCP Secret Manager. Azure Key Vault disallows underscores in secret
names, so ORBIT translates underscores to hyphens for that provider only —
`DATASOURCE_POSTGRES_PASSWORD` becomes `DATASOURCE-POSTGRES-PASSWORD`. **No existing
`config/*.yaml` file needs to change** to adopt a cloud provider; only the resolution source
changes.

## Prerequisites

ORBIT installed with the `secrets-management` dependency profile (extends `cloud-services`,
adding `azure-keyvault-secrets` and `google-cloud-secret-manager`; `boto3` for AWS is already
included):

```bash
./install/setup.sh --profile secrets-management
```

## AWS Secrets Manager

1. Create a secret per credential, named exactly like the `${VAR_NAME}` it replaces:
   ```bash
   aws secretsmanager create-secret \
     --name DATASOURCE_POSTGRES_PASSWORD \
     --secret-string 'your-password-here'
   ```
2. Set in `.env` (only the connection settings — never the secrets themselves):
   ```env
   ORBIT_SECRETS_PROVIDER=aws
   AWS_REGION=us-east-1
   ```
3. Credentials for reaching Secrets Manager itself follow the boto3 default chain (env /
   instance role / SSO) — omit `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` to use it.

## Azure Key Vault

1. Create a secret per credential, using hyphens instead of underscores:
   ```bash
   az keyvault secret set \
     --vault-name your-vault \
     --name DATASOURCE-POSTGRES-PASSWORD \
     --value 'your-password-here'
   ```
2. Set in `.env`:
   ```env
   ORBIT_SECRETS_PROVIDER=azure
   AZURE_KEY_VAULT_URL=https://your-vault.vault.azure.net/
   ```
3. Authentication uses `DefaultAzureCredential` (managed identity, `az login`, or environment
   credentials) — grant the identity running ORBIT a Key Vault "Secrets User" role/access
   policy.

## GCP Secret Manager

1. Create a secret per credential, named exactly like the `${VAR_NAME}` it replaces:
   ```bash
   echo -n 'your-password-here' | gcloud secrets create DATASOURCE_POSTGRES_PASSWORD \
     --data-file=- --project=your-project-id
   ```
2. Set in `.env`:
   ```env
   ORBIT_SECRETS_PROVIDER=gcp
   GOOGLE_CLOUD_PROJECT=your-project-id
   ```
3. Authentication uses Application Default Credentials (`gcloud auth application-default
   login` locally, or Workload Identity on GCP) — grant the identity running ORBIT the
   "Secret Manager Secret Accessor" role.

## Failure behavior

ORBIT never crashes startup over secrets-manager problems:

- If the backend can't be reached at startup (bad credentials, network, wrong
  region/vault/project), ORBIT logs a warning and falls back to `.env`/environment-only
  resolution for the entire config.
- If a specific secret lookup fails (not found, permission denied) after the backend is up,
  ORBIT logs a warning for that one placeholder and falls back to `.env`/environment, then to
  its `${VAR:-default}` if any.

This means you can migrate credentials to the cloud provider incrementally — set only the
ones you've created there, and everything else keeps resolving from `.env` exactly as before.

## Verifying

Start the server and check the logs for secrets-backend initialization and any per-variable
fallback warnings:

```bash
python3 server/main.py
```

No warning for a variable you moved to the cloud provider means it resolved successfully
from there.
