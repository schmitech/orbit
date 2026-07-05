# AWS S3 File Storage Setup

This guide walks through provisioning an S3 bucket and wiring it into ORBIT so uploaded
files and generated media are stored in S3 instead of the local filesystem. It assumes
you already have an AWS identity (SSO session, IAM user, or instance role) and want to
verify the setup end-to-end before pointing a production adapter at it.

For the full storage abstraction (filesystem, S3, MinIO, Azure Blob, GCS) see
[File Adapter Guide → Storage Backends](../adapters/file-adapter-guide.md#storage-backends).
For a deeper test matrix across all backends see
[playbook-cloud-storage.md](../../server/tests/file-adapter/playbook-cloud-storage.md).

## Prerequisites

- AWS CLI installed and an active session — either `aws sso login`, a configured IAM
  user/access key, or an EC2/ECS instance role.
- Permission to create and configure an S3 bucket (`s3:CreateBucket`, `s3:PutBucketPublicAccessBlock`)
  in the target account.
- ORBIT installed with the `cloud-services` dependency profile (provides `boto3`). Check with:
  ```bash
  venv/bin/python -c "import boto3; print(boto3.__version__)"
  ```
  If missing, re-run `./install/setup.sh --profile cloud-services` (or `--profile all`).

---

## 1. Confirm your AWS session

```bash
aws configure list-profiles      # see what's available
export AWS_PROFILE=<your-profile>
aws sts get-caller-identity      # confirms the session is live and shows the account
aws configure get region --profile $AWS_PROFILE
```

Note the account ID and region — you'll use the region when creating the bucket and in
ORBIT's config.

---

## 2. Create the bucket

Bucket names are globally unique across all of AWS, so it's worth baking your account ID
into the name to avoid collisions:

```bash
aws s3api create-bucket \
  --bucket orbit-file-storage-<your-account-id> \
  --region <your-region> \
  --create-bucket-configuration LocationConstraint=<your-region>
```

Lock down public access (uploads should never be publicly readable):

```bash
aws s3api put-public-access-block \
  --bucket orbit-file-storage-<your-account-id> \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Verify it exists and is reachable:

```bash
aws s3api head-bucket --bucket orbit-file-storage-<your-account-id> && echo OK
```

> ORBIT does **not** create the bucket for you — `create_storage_backend` requires the
> bucket to already exist and fails loudly at startup if it doesn't (least-privilege: the
> app never needs `s3:CreateBucket` permission at runtime).

---

## 3. Set environment variables

Add to your `.env` (or export in the shell that runs the server):

```env
ORBIT_S3_BUCKET=orbit-file-storage-<your-account-id>
AWS_REGION=<your-region>
# ORBIT_S3_PREFIX=                     # optional key prefix within the bucket
# ORBIT_S3_ENDPOINT_URL=               # only set for MinIO / S3-compatible stores
```

If you're using SSO or an instance role, that's all you need — boto3 picks up credentials
from the ambient session automatically. Only set `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` if you're using static keys (not recommended; prefer SSO or an
instance role).

```bash
export AWS_PROFILE=<your-profile>   # if using SSO, so boto3 can find the session
```

---

## 4. Configure ORBIT

In `config/config.yaml`, find the `files:` block and set `storage_backend` to `s3`:

```yaml
files:
  storage_backend: "s3"   # filesystem | s3 | minio | azure | gcs

  s3:
    bucket: "${ORBIT_S3_BUCKET}"
    prefix: "${ORBIT_S3_PREFIX:-}"
    region: "${AWS_REGION:-us-east-1}"
    endpoint_url: "${ORBIT_S3_ENDPOINT_URL:-}"
    # Omit credentials to use the boto3 default chain (SSO / env / instance role):
    # access_key_id: "${AWS_ACCESS_KEY_ID:-}"
    # secret_access_key: "${AWS_SECRET_ACCESS_KEY:-}"
```

Never inline the bucket name or credentials directly in the YAML — always reference the
env vars, as shown above.

---

## 5. Verify

### Smoke test the backend directly

Before starting the full server, exercise the backend in isolation:

```bash
cd server
AWS_PROFILE=<your-profile> \
ORBIT_S3_BUCKET=orbit-file-storage-<your-account-id> \
AWS_REGION=<your-region> \
venv/bin/python -c "
import asyncio
from services.file_storage import S3Storage

async def main():
    s = S3Storage(bucket='orbit-file-storage-<your-account-id>', region_name='<your-region>')
    key = await s.put_file(b'hello from orbit', 'smoke-test.txt', {'note': 'setup test'})
    print('put_file ->', key)
    print('get_file ->', await s.get_file(key))
    print('get_metadata ->', await s.get_metadata(key))
    print('list_files ->', await s.list_files(''))
    print('file_exists ->', await s.file_exists(key))
    print('delete_file ->', await s.delete_file(key))
    print('file_exists after delete ->', await s.file_exists(key))

asyncio.run(main())
"
```

Expected output: `put_file` returns the key, `get_file` returns the original bytes,
`list_files` shows the key, and `file_exists` is `False` after delete.

> `put_file(file_data, key, metadata)` — data first, then key. Getting the argument order
> backwards is the most common mistake here; it silently uploads an object under a garbled
> key instead of raising.

### Start the server and test via the API

Start ORBIT normally (`python3 server/main.py`) and check the logs confirm the S3 backend
initialized (bucket existence is verified at startup — a missing or misnamed bucket fails
loudly here). Then upload a file through a file-capable adapter (e.g. `simple-chat-with-files`)
via `/v1/files` or the chat API, and confirm the object shows up in S3:

```bash
aws s3 ls s3://orbit-file-storage-<your-account-id>/ --recursive
```

For the full upload → download → delete cycle through the API, along with edge cases
(large files, unicode metadata, concurrent uploads), follow **Part 2 (AWS S3)** of
[playbook-cloud-storage.md](../../server/tests/file-adapter/playbook-cloud-storage.md).

---

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `Unable to locate credentials` | No active AWS session in the shell running ORBIT | `export AWS_PROFILE=<profile>` and confirm with `aws sts get-caller-identity` |
| `NoSuchBucket` / bucket check fails at startup | Bucket doesn't exist, or region mismatch | Verify with `aws s3api head-bucket --bucket <name>`; check `region` matches where the bucket was created |
| `Unknown storage_backend` | Typo in `files.storage_backend` | Must be exactly `filesystem`, `s3`, `minio`, `azure`, or `gcs` |
| Object uploads under a garbled/bytes-looking key | `put_file` called with `(key, data)` instead of `(data, key)` | Check argument order: `put_file(file_data, key, metadata)` |
| `boto3` `ImportError` | `cloud-services` dependency profile not installed | `./install/setup.sh --profile cloud-services` |
| `403 Forbidden` on put/get | IAM identity lacks `s3:PutObject`/`s3:GetObject`/`s3:DeleteObject`/`s3:ListBucket` on the bucket | Attach a policy scoped to the bucket ARN with those actions |

---

## Notes

- ORBIT wraps all boto3 calls in `asyncio.to_thread` since boto3 is sync-only — this keeps
  the async interface honest without needing `aioboto3`.
- Object metadata is stored as a JSON sidecar (`{key}.metadata.json`) rather than native S3
  object metadata, to avoid the 2KB/ASCII-only limits on S3 metadata headers.
- `storage_backend: "minio"` reuses the same `S3Storage` class with path-style addressing
  enabled — set `endpoint_url` to your MinIO/SeaweedFS endpoint. See
  [File Adapter Guide → Storage Backends](../adapters/file-adapter-guide.md#storage-backends)
  for MinIO/SeaweedFS-specific config.
- The `files.storage_backend` selection is global — all adapters share the same storage
  backend in this release (no per-adapter override yet).
