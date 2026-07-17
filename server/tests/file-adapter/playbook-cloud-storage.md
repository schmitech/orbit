# Manual/Integration Check: Cloud File Storage (AWS S3, MinIO, Azure Blob, GCS)

End-to-end verification of the pluggable file-storage backends, using real
object stores:

- **Part 1 — MinIO (local S3):** the fastest path; a local S3-compatible store,
  no cloud account needed.
- **Part 2 — AWS S3:** the same round-trip against a real S3 bucket.
- **Part 3 — Azure Blob:** against Azurite (local emulator) or a real container.
- **Part 4 — Google Cloud Storage:** against a real GCS bucket.

The automated unit tests (`test_cloud_storage.py`) already cover the backend
logic against `moto` (in-memory S3) and in-memory Azure/GCS fakes — put/get/
delete/list/metadata, prefix isolation, not-found mapping, and factory
selection. This playbook exercises the real network round-trips, credential
resolution, and startup-time bucket/container verification that unit tests
can't.

Prerequisites: an admin can create an API key (`orbit key create`) bound to a
file adapter, ORBIT runs at `http://localhost:3000`, and Docker is available for
the local MinIO/Azurite emulators.

## 0. Install the dependency profile

The cloud SDKs are opt-in:

```bash
./install/setup.sh --profile cloud-services   # boto3, azure-storage-blob, azure-identity, google-cloud-storage
```

Verify:

```bash
venv/bin/python -c "import boto3; print('boto3', boto3.__version__)"
venv/bin/python -c "import azure.storage.blob as b; print('azure-storage-blob ok')"
venv/bin/python -c "import google.cloud.storage as g; print('google-cloud-storage ok')"
```

If `files.storage_backend` is set to `s3`/`minio`/`azure`/`gcs` but the SDK is
missing, the server **fails fast at startup** with an install hint naming the
`cloud-services` profile — that itself is scenario **S2**.

## Common setup: an API key + a test file

Create an API key bound to the file adapter (as a password admin), and a small
file to upload:

```bash
orbit login --username admin
orbit key create --adapter file-document-qa --name "storage-playbook"
export API_KEY=orbit_...        # the key printed above
export SESSION=playbook-session
echo "hello cloud storage" > /tmp/hello.txt
```

Helper functions used throughout (paste into your shell):

```bash
upload() { curl -s -H "X-API-Key: $API_KEY" -H "X-Session-ID: $SESSION" \
  -F "file=@$1" http://localhost:3000/api/files/upload; }
download() { curl -s -H "X-API-Key: $API_KEY" -H "X-Session-ID: $SESSION" \
  http://localhost:3000/api/files/$1/content; }
listfiles() { curl -s -H "X-API-Key: $API_KEY" -H "X-Session-ID: $SESSION" \
  http://localhost:3000/api/files; }
delfile() { curl -s -X DELETE -H "X-API-Key: $API_KEY" -H "X-Session-ID: $SESSION" \
  http://localhost:3000/api/files/$1; }
```

The storage key ORBIT writes is `{api_key}/{file_id}/{filename}` (plus a
`{filename}.metadata.json` sidecar), under any configured `prefix`. Note the
`file_id` returned by `upload`.

---

# Part 1 — MinIO (local S3)

## 1. Start MinIO and create the bucket

```bash
docker run -d --name minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  quay.io/minio/minio server /data --console-address ":9001"

# Create the bucket (via the AWS CLI pointed at MinIO, or the console at :9001)
AWS_ACCESS_KEY_ID=minioadmin AWS_SECRET_ACCESS_KEY=minioadmin \
  aws --endpoint-url http://localhost:9000 s3 mb s3://orbit-uploads
```

## 2. Configure ORBIT for MinIO

In `config/config.yaml`, set the backend and point it at MinIO:

```yaml
files:
  storage_backend: "minio"
  s3:
    bucket: "${ORBIT_S3_BUCKET}"
    prefix: "${ORBIT_S3_PREFIX:-}"
    region: "${AWS_REGION:-us-east-1}"
    endpoint_url: "${ORBIT_S3_ENDPOINT_URL:-}"
    access_key_id: "${AWS_ACCESS_KEY_ID:-}"
    secret_access_key: "${AWS_SECRET_ACCESS_KEY:-}"
```

Export the env and restart ORBIT (config is read at startup):

```bash
export ORBIT_S3_BUCKET=orbit-uploads
export ORBIT_S3_PREFIX=orbit/uploads       # optional; exercises prefix handling
export ORBIT_S3_ENDPOINT_URL=http://localhost:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
python3 server/main.py                      # or ./bin/orbit.sh start
```

Startup log should include `Initialized S3Storage (bucket=orbit-uploads, prefix='orbit/uploads/', endpoint=http://localhost:9000)`.
`storage_backend: minio` selects **path-style addressing** automatically.

## 3. Round-trip a file

```bash
FILE_ID=$(upload /tmp/hello.txt | python3 -c "import sys,json; print(json.load(sys.stdin)['file_id'])")
echo "file_id=$FILE_ID"

download "$FILE_ID"          # -> "hello cloud storage"
listfiles                    # -> the file appears with status
delfile "$FILE_ID"           # -> success
```

Confirm:
- `download` returns the exact bytes.
- `listfiles` shows the file (backed by the DB metadata index, not the bucket).
- `delfile` returns success and a subsequent `download` returns **404**.

## 4. Verify what actually landed in the object store

```bash
aws --endpoint-url http://localhost:9000 s3 ls --recursive s3://orbit-uploads
```

Before the delete, confirm **two** objects exist under the prefix:

```
orbit/uploads/<API_KEY>/<file_id>/hello.txt
orbit/uploads/<API_KEY>/<file_id>/hello.txt.metadata.json
```

- The `orbit/uploads/` prefix confirms `prefix` is applied (**S4**).
- The `.metadata.json` sidecar confirms metadata handling (**S5**).
- After `delfile`, confirm **both** objects are gone (sidecar cleaned up, **S11**).

---

# Part 2 — AWS S3 (real bucket)

Only the configuration differs from MinIO — the code path is identical.

## 5. Configure for AWS

Create (or reuse) an S3 bucket, then:

```yaml
files:
  storage_backend: "s3"        # not "minio" — no endpoint_url, virtual-hosted addressing
```

```bash
export ORBIT_S3_BUCKET=<your-real-bucket>
export AWS_REGION=us-east-1
unset ORBIT_S3_ENDPOINT_URL     # important: no custom endpoint for real AWS
# Credentials: either export explicit keys, OR omit them to use the default chain.
```

**Credential resolution (S8):** leave `access_key_id`/`secret_access_key`
commented out in config to use the **boto3 default chain** — environment
variables, a shared profile (`AWS_PROFILE`), SSO, or an EC2/ECS instance role.
This is the recommended production setup. Verify it works with only
`AWS_PROFILE` set (no keys in config or env).

Restart and repeat step 3 (round-trip) and step 4 with the AWS CLI (drop
`--endpoint-url`). Same observable behavior.

---

# Part 3 — Azure Blob

## 6a. Azurite (local emulator)

```bash
docker run -d --name azurite -p 10000:10000 mcr.microsoft.com/azure-storage/azurite \
  azurite-blob --blobHost 0.0.0.0

# Create the container using the well-known Azurite dev connection string
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
az storage container create --name orbit-uploads \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
```

Configure ORBIT:

```yaml
files:
  storage_backend: "azure"
  azure:
    container: "${ORBIT_AZURE_CONTAINER}"
    prefix: "${ORBIT_AZURE_PREFIX:-}"
    connection_string: "${AZURE_STORAGE_CONNECTION_STRING:-}"
```

```bash
export ORBIT_AZURE_CONTAINER=orbit-uploads
export ORBIT_AZURE_PREFIX=orbit/uploads
# AZURE_STORAGE_CONNECTION_STRING already exported above
python3 server/main.py
```

Startup log: `Initialized AzureBlobStorage (container=orbit-uploads, prefix='orbit/uploads/')`.

Repeat the step-3 round-trip. Verify the blobs (and sidecar) in the container:

```bash
az storage blob list --container-name orbit-uploads \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
  --query "[].name" -o tsv
```

## 6b. Real Azure Storage account

Same config. Two auth options:

- **Connection string** — set `AZURE_STORAGE_CONNECTION_STRING` (from the portal
  → Access keys).
- **Identity-based (recommended)** — comment out `connection_string`, set
  `account_url`, and omit `account_key` to use `DefaultAzureCredential`
  (managed identity in Azure, or `az login` / env locally). Grant the identity
  the **Storage Blob Data Contributor** role on the account/container.

```yaml
  azure:
    container: "${ORBIT_AZURE_CONTAINER}"
    account_url: "${AZURE_STORAGE_ACCOUNT_URL:-}"
    # account_key omitted -> DefaultAzureCredential
```

```bash
export AZURE_STORAGE_ACCOUNT_URL=https://<youraccount>.blob.core.windows.net
az login    # so DefaultAzureCredential can resolve a token locally
```

Confirm the round-trip works with **no** connection string or account key
present — proving the managed-identity/Entra path (**Azure S8**).

---

# Part 4 — Google Cloud Storage

GCS uses the native `google-cloud-storage` SDK (not the S3-interop layer), so the
code path is separate from S3 but the observable behavior is identical.

## 6c. Create a bucket and configure ORBIT

```bash
gcloud storage buckets create gs://orbit-uploads --location=us-central1
```

Configure ORBIT:

```yaml
files:
  storage_backend: "gcs"
  gcs:
    bucket: "${ORBIT_GCS_BUCKET}"
    prefix: "${ORBIT_GCS_PREFIX:-}"
    project: "${GOOGLE_CLOUD_PROJECT:-}"
    # Omit credentials_path to use Application Default Credentials (ADC):
    # credentials_path: "${GOOGLE_APPLICATION_CREDENTIALS:-}"
```

Two auth options:

- **Application Default Credentials (recommended)** — comment out
  `credentials_path`. Locally, run `gcloud auth application-default login`; on
  GCP (GKE/Cloud Run/GCE), Workload Identity or the attached service account is
  used automatically. The identity needs object read/write plus
  `storage.buckets.get` on the bucket (the **Storage Object Admin** +
  **Storage Legacy Bucket Reader** roles, or a custom role, cover this).
- **Service-account key file** — set `GOOGLE_APPLICATION_CREDENTIALS` (or
  `credentials_path`) to a JSON key file.

```bash
export ORBIT_GCS_BUCKET=orbit-uploads
export ORBIT_GCS_PREFIX=orbit/uploads
export GOOGLE_CLOUD_PROJECT=<your-gcp-project>
gcloud auth application-default login    # so ADC can resolve a token locally
python3 server/main.py
```

Startup log: `Initialized GcsStorage (bucket=orbit-uploads, prefix='orbit/uploads/')`.

Repeat the step-3 round-trip. Verify the objects (and sidecar) in the bucket:

```bash
gcloud storage ls --recursive gs://orbit-uploads/**
```

Confirm both `.../hello.txt` and `.../hello.txt.metadata.json` exist under the
`orbit/uploads/` prefix, and that both are gone after `delfile`.

> **Why native GCS, not S3-interop:** GCS does expose an S3-compatible XML API,
> but its `ListObjectsV2` support is unreliable — and `list_files()` depends on
> it. The native SDK avoids that class of quirk, so `gcs` is a first-class
> backend rather than an `s3` + `endpoint_url` workaround.

---

## Additional scenarios (failure modes & guarantees)

### S1. Fail-fast when the bucket / container is missing

Point `ORBIT_S3_BUCKET` / `ORBIT_AZURE_CONTAINER` / `ORBIT_GCS_BUCKET` at a name
that does **not** exist and start ORBIT. Confirm startup aborts with a clear
error — `S3 bucket '...' is not accessible` / `Azure container '...' is not
accessible` / `GCS bucket '...' is not accessible` — naming the missing
resource, rather than starting and 500-ing on first upload. The backend verifies
access in `__init__` (`head_bucket` / `get_container_properties` / `get_bucket`).

### S2. Fail-fast when the SDK is missing

In a venv **without** `cloud-services`, set `storage_backend` to `s3`, `azure`,
or `gcs` and start ORBIT. Confirm the failure names the `cloud-services` profile
/ `pip install boto3` (S3), `azure-storage-blob` (Azure), or
`google-cloud-storage` (GCS). Cloud SDKs are lazy-imported, so the filesystem
backend never needs them.

### S3. Unknown backend value rejected

Set `storage_backend: "dropbox"` and start ORBIT. Confirm a `ValueError: Unknown
storage_backend 'dropbox'. Valid options: filesystem, s3, minio, azure, gcs.` —
never a silent fallback to filesystem.

### S4. Prefix isolation (no `api_key_1` vs `api_key_10` collision)

With a `prefix` configured, upload files under two API keys whose names share a
prefix (e.g. `...key1` and `...key10`). Confirm listing/scoping for one key
does not return the other's objects. (Locked in by `test_list_files_delimits_prefix`.)

### S5 / S11. Metadata sidecar lifecycle

Confirm every upload writes a `{filename}.metadata.json` sidecar next to the
file (step 4), the sidecar is **excluded** from `list_files` results, and
deleting a file removes **both** the object and its sidecar. Deleting a
nonexistent file returns gracefully (no error).

### S6. Backend is selected globally (per-adapter key is doc-only)

In an adapter config (`config/adapters/*.yaml`) set `storage_backend: "filesystem"`
while `files.storage_backend: s3` globally. Upload a file. Confirm it still
lands in **S3** — the global setting wins; the per-adapter key is
documentation-only (`files.storage_backend` takes precedence in the factory).

### S7. Filesystem default is unaffected

Set `storage_backend: "filesystem"` (or remove it). Confirm uploads land under
`./uploads/{api_key}/{file_id}/` on local disk exactly as before — the factory
is transparent to existing deployments, and no cloud SDK is required.

### S8. Credential resolution

- **Explicit keys (recommended):** set `ORBIT_S3_ACCESS_KEY_ID`/
  `ORBIT_S3_SECRET_ACCESS_KEY` (e.g. via `utils/scripts/setup_s3_app_user.sh`, see
  `docs/aws/s3-file-storage-setup.md`) — a long-lived key scoped to just the
  bucket, so a locally expiring SSO session never breaks uploads. Round-trip
  works.
- **Default chain:** leave `access_key_id`/`secret_access_key` empty; rely on
  `AWS_PROFILE` / instance role. Round-trip still works, but an SSO session
  will eventually expire and uploads will start failing until it's refreshed.
- **Wrong credentials:** set a bad `ORBIT_S3_SECRET_ACCESS_KEY`. Confirm ORBIT
  fails fast at startup (the `head_bucket` access check fails), not on first
  upload.

### S9. Generated media also persists to the cloud

If an image/document-generator adapter is enabled, generate an asset in a chat
turn (it flows through `pipeline_chat_service` → the same shared storage
backend). Confirm the generated file is written to the configured cloud bucket/
container under `{_generated or api_key}/{file_id}/...`, and is retrievable via
its `/api/files/{file_id}/content` URL. This proves **all** storage writes —
not just uploads — go through the selected backend.

---

## 7. Run the automated checks

```bash
ruff check server/services/file_storage/ server/tests/file-adapter/test_cloud_storage.py
cd server && ../venv/bin/python -m pytest tests/file-adapter/test_cloud_storage.py tests/file-adapter/test_file_storage.py -v
```

Expect all green: `test_cloud_storage.py` (S3 via moto + Azure and GCS via
in-memory fakes + factory selection) and `test_file_storage.py` (filesystem
regression — behavior unchanged). The cloud tests `importorskip` when `moto` /
`azure-storage-blob` / `google-cloud-storage` are absent, so they skip cleanly
rather than fail in a base install.

---

## Troubleshooting

- **Server refuses to start after setting a cloud backend:** either the bucket/
  container doesn't exist (S1), credentials are wrong (S8), or the
  `cloud-services` profile isn't installed (S2). Read the startup error — it
  names which.
- **MinIO: `SignatureDoesNotMatch` / connection errors:** ensure
  `storage_backend: minio` (enables path-style) **or** an `endpoint_url` is set,
  the keys match `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, and the endpoint host/
  port are reachable from the ORBIT process.
- **AWS: works with MinIO but not real S3:** make sure `ORBIT_S3_ENDPOINT_URL`
  is **unset** for real AWS and `storage_backend` is `s3` (not `minio`), so
  virtual-hosted addressing and the AWS endpoint are used.
- **Azure: `AuthorizationPermissionMismatch` with `DefaultAzureCredential`:** the
  identity needs the **Storage Blob Data Contributor** role (data-plane), not
  just account-management roles. For local dev, `az login` first.
- **GCS: `403` / `AccessDenied` at startup or on upload:** the identity needs
  object read/write **and** `storage.buckets.get` (the startup check calls
  `get_bucket`). For local dev, run `gcloud auth application-default login`; on
  GCP, attach a service account / Workload Identity with those permissions.
- **Uploads land on local disk instead of the cloud:** `files.storage_backend`
  is still `filesystem`, or you edited a per-adapter `storage_backend` expecting
  it to switch backends — selection is global (S6). Check the startup log for
  the `Initialized S3Storage`/`AzureBlobStorage`/`GcsStorage` line.
- **Objects have no prefix / an unexpected prefix:** `prefix` is normalized to a
  single trailing slash; an empty prefix stores at the bucket root. Verify with
  the `aws s3 ls --recursive` / `az storage blob list` / `gcloud storage ls`
  commands above.
- **Inspect the DB metadata index:** `sqlite3 orbit.db "SELECT file_id, filename, storage_key, storage_type FROM uploaded_files;"` — `storage_key` is backend-agnostic; the bytes live wherever the active backend points.
