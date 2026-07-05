# Manual/Integration Check: File Encryption at Rest (AES-256-GCM)

End-to-end verification of per-adapter file encryption, using a real running
server:

- **Part 1 — Filesystem backend:** the fastest path; encryption is
  backend-agnostic, so this exercises the full behavior without any cloud
  account.
- **Part 2 — Cloud backend (S3/MinIO):** confirms encryption composes with a
  cloud storage backend exactly the same way (it wraps whichever backend
  `files.storage_backend` selects).

The automated unit tests (`test_file_encryption.py`) already cover the
primitive and wrapper logic in isolation — encrypt/decrypt round-trips, tamper
detection, wrong-key rejection, AAD binding (ciphertext-swap protection),
metadata-merge durability, and fail-closed behavior on lookup errors. This
playbook exercises the real HTTP upload/download path, adapter opt-in via
config, and the operational failure modes (missing key, disabled encryption,
mixed encrypted/plaintext adapters) that unit tests can't.

Prerequisites: an admin can create an API key (`orbit key create`) bound to a
file adapter, ORBIT runs at `http://localhost:3000`.

## Scope reminder

Encryption covers **file bytes and the storage backend's metadata sidecar**
only. Extracted content (OCR/vision descriptions, audio transcriptions) that
lands in the database's `uploaded_files.metadata_json`, and chunk text indexed
into the vector store, are **not** encrypted by this feature — don't rely on
it alone for content where the extracted/indexed text itself is classified.

---

## 0. Generate a key and enable encryption

```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
export ORBIT_FILE_ENCRYPTION_KEY=<generated-key>
```

In `config/config.yaml`:

```yaml
files:
  encryption:
    enabled: true
```

## 1. Mark one adapter as requiring encryption

Add `requires_encryption: true` to a test adapter's capabilities — e.g. in
`config/adapters/file.yaml` (or `adapters.yaml`), on a **copy** of the
`file-document-qa` adapter named `classified-docs` so you can compare against
an unmodified plaintext adapter side by side:

```yaml
adapters:
  - name: classified-docs
    # ... same as file-document-qa ...
    capabilities:
      requires_encryption: true
      # ... other capabilities unchanged ...
```

Leave a second adapter (e.g. the existing `file-document-qa`, or any other
file-capable adapter) **without** the flag — you'll compare behavior between
the two throughout this playbook.

Create one API key per adapter:

```bash
orbit login --username admin
orbit key create --adapter classified-docs --name "encryption-playbook-classified"
orbit key create --adapter file-document-qa --name "encryption-playbook-plain"
export CLASSIFIED_KEY=orbit_...    # from the first command
export PLAIN_KEY=orbit_...         # from the second command
export SESSION=encryption-playbook
echo "classified: launch codes" > /tmp/classified.txt
echo "just a memo" > /tmp/memo.txt
```

Helper functions (paste into your shell):

```bash
upload() { curl -s -H "X-API-Key: $1" -H "X-Session-ID: $SESSION" \
  -F "file=@$2" http://localhost:3000/api/files/upload; }
download() { curl -s -H "X-API-Key: $1" -H "X-Session-ID: $SESSION" \
  http://localhost:3000/api/files/$2/content; }
delfile() { curl -s -X DELETE -H "X-API-Key: $1" -H "X-Session-ID: $SESSION" \
  http://localhost:3000/api/files/$2; }
```

Restart ORBIT after the config/env changes (config is read at startup):

```bash
python3 server/main.py    # or ./bin/orbit.sh start
```

---

# Part 1 — Filesystem backend

## 2. Upload through the classified adapter and inspect the raw bytes on disk

```bash
CLASSIFIED_ID=$(upload "$CLASSIFIED_KEY" /tmp/classified.txt | python3 -c "import sys,json; print(json.load(sys.stdin)['file_id'])")
echo "classified file_id=$CLASSIFIED_ID"

cat "./uploads/$CLASSIFIED_KEY/$CLASSIFIED_ID/classified.txt"
```

Confirm the raw file on disk is **ciphertext** — it must not contain the
string `launch codes` or any readable fragment of the original content.

## 3. Upload through the plain adapter and confirm it's untouched

```bash
PLAIN_ID=$(upload "$PLAIN_KEY" /tmp/memo.txt | python3 -c "import sys,json; print(json.load(sys.stdin)['file_id'])")
echo "plain file_id=$PLAIN_ID"

cat "./uploads/$PLAIN_KEY/$PLAIN_ID/memo.txt"
```

Confirm this file is **plaintext** on disk (`just a memo`), byte-for-byte
identical to the original — encrypting one adapter must not affect another.

## 4. Download both through the API

```bash
download "$CLASSIFIED_KEY" "$CLASSIFIED_ID"   # -> "classified: launch codes"
download "$PLAIN_KEY" "$PLAIN_ID"              # -> "just a memo"
```

Both must return the exact original plaintext — the classified file
transparently decrypts on the way out; the plain file is served as-is.

## 5. Clean up

```bash
delfile "$CLASSIFIED_KEY" "$CLASSIFIED_ID"
delfile "$PLAIN_KEY" "$PLAIN_ID"
```

Confirm both deletes succeed and both files' storage-backend objects (and
metadata sidecars) are gone.

---

# Part 2 — Cloud backend (S3/MinIO)

Encryption wraps whichever backend `files.storage_backend` selects, so the
same behavior should hold against a cloud backend. Follow
[playbook-cloud-storage.md](./playbook-cloud-storage.md) to point ORBIT at a
MinIO or real S3 bucket, keeping `files.encryption.enabled: true` and the
`classified-docs` adapter's `requires_encryption: true` from Part 1.

## 6. Repeat the round-trip against the cloud backend

```bash
CLASSIFIED_ID=$(upload "$CLASSIFIED_KEY" /tmp/classified.txt | python3 -c "import sys,json; print(json.load(sys.stdin)['file_id'])")
aws --endpoint-url http://localhost:9000 s3 cp \
  "s3://orbit-uploads/$CLASSIFIED_KEY/$CLASSIFIED_ID/classified.txt" - | cat
```

Confirm the object fetched directly from the bucket is ciphertext, and
`download "$CLASSIFIED_KEY" "$CLASSIFIED_ID"` via the API still returns the
original plaintext. This proves encryption composes with the storage-backend
abstraction rather than being filesystem-specific.

---

## Additional scenarios (failure modes & guarantees)

### S1. Fail loudly when encryption is required but not enabled

With `files.encryption.enabled: false` (or `ORBIT_FILE_ENCRYPTION_KEY` unset),
upload through the `classified-docs` adapter:

```bash
upload "$CLASSIFIED_KEY" /tmp/classified.txt
```

Confirm the upload **fails** with a clear error naming
`capabilities.requires_encryption` and instructing you to set
`files.encryption.enabled: true` + `ORBIT_FILE_ENCRYPTION_KEY` — never a
silent fallback to plaintext storage.

### S2. Fail loudly on a missing or invalid key

With `files.encryption.enabled: true` but `ORBIT_FILE_ENCRYPTION_KEY` unset
(or set to something that isn't valid base64, or that doesn't decode to
exactly 32 bytes), start ORBIT. Confirm **startup itself fails** with an error
naming the env var and a key-generation command — not a runtime failure on
first upload.

### S3. Unaffected adapters keep working exactly as before

Repeat step 3/4 for the plain adapter with encryption fully enabled globally.
Confirm plaintext adapters are completely unaffected — same bytes on disk,
same API behavior as before this feature existed.

### S4. Reads fail loudly if encryption becomes unavailable after upload

1. Upload a file through `classified-docs` (encryption enabled) and note its
   `file_id`.
2. Stop ORBIT, set `files.encryption.enabled: false` (or unset
   `ORBIT_FILE_ENCRYPTION_KEY`), restart.
3. Attempt `download "$CLASSIFIED_KEY" "$CLASSIFIED_ID"`.

Confirm this **fails with a clear error** ("this file was stored with
encryption enabled, but files.encryption is not currently configured...") —
it must never silently return raw AES-GCM ciphertext as if it were the file's
content. Restore the key/config afterward to continue testing.

### S5. Encryption state survives a failed background processing run

This applies to the async image/audio upload path (`quick_upload` +
background `process_file_content`), where a processing error or timeout
writes a partial metadata update.

1. Upload an image or audio file through an encryption-required adapter that
   uses the quick-upload path (e.g. a multimodal adapter with
   `requires_encryption: true`).
2. Force a processing failure or timeout if you can (e.g. point the adapter's
   vision/STT provider at an unreachable endpoint), or inspect the DB directly
   after a natural failure.
3. Once the file's `processing_status` is `failed`, confirm via
   `download "$CLASSIFIED_KEY" "$FILE_ID"` that the file **still decrypts
   correctly** — the error/failed_at fields recorded on the failure path must
   not have clobbered the `encrypted` flag from upload time.

### S6. Ciphertext cannot be swapped between files

This is best verified with the automated test
(`test_swapped_ciphertext_between_files_fails_to_decrypt`), but to see it
manually against the filesystem backend:

```bash
ID_A=$(upload "$CLASSIFIED_KEY" /tmp/classified.txt | python3 -c "import sys,json; print(json.load(sys.stdin)['file_id'])")
echo "other secret" > /tmp/other.txt
ID_B=$(upload "$CLASSIFIED_KEY" /tmp/other.txt | python3 -c "import sys,json; print(json.load(sys.stdin)['file_id'])")

# Copy file A's encrypted bytes onto file B's storage path
cp "./uploads/$CLASSIFIED_KEY/$ID_A/classified.txt" "./uploads/$CLASSIFIED_KEY/$ID_B/other.txt"

download "$CLASSIFIED_KEY" "$ID_B"
```

Confirm this returns a decryption error (500), **not** file A's plaintext
content — the ciphertext is bound to its own storage key (AAD), so a swapped
blob fails to authenticate rather than silently decrypting as the wrong file.

### S7. A transient capability-lookup failure fails the upload, not the encryption check

Hard to trigger manually (it requires the adapter manager or API key service
to throw mid-lookup), so this is covered by the automated test
(`test_upload_fails_closed_when_capability_lookup_errors`) rather than a
manual step here. The guarantee: if ORBIT can't determine whether an adapter
requires encryption due to an actual error (not simply "no adapter found"),
the upload must fail rather than defaulting to "encryption not required."

### S8. Reprocessing an encrypted file works transparently

```bash
# after uploading via classified-docs and getting $CLASSIFIED_ID
curl -s -X POST -H "X-API-Key: $CLASSIFIED_KEY" -H "X-Session-ID: $SESSION" \
  http://localhost:3000/api/files/$CLASSIFIED_ID/reprocess
```

Confirm reprocessing succeeds and chunk count/status update normally — the
original bytes are reloaded through the same decrypt-aware read path used by
`download`, so re-extraction sees plaintext, not ciphertext.

### S9. `get_metadata` / file size behave sensibly for encrypted files

If you have an admin/inspection endpoint or direct DB access, confirm:
- The storage backend's metadata sidecar for an encrypted file is itself
  encrypted (not readable JSON) when inspected directly (e.g.
  `cat ./uploads/$CLASSIFIED_KEY/$CLASSIFIED_ID/classified.txt.metadata.json`).
- Any size shown for the raw stored object is the **ciphertext** size (original
  size + 28 bytes of nonce/tag overhead) — this is expected, not a bug.

---

## 7. Run the automated checks

```bash
ruff check server/services/file_storage/ server/services/file_metadata/metadata_store.py \
  server/services/file_processing/file_processing_service.py server/adapters/capabilities.py
cd server && ../venv/bin/python -m pytest tests/file-adapter/test_file_encryption.py \
  tests/file-adapter/test_file_storage.py tests/file-adapter/test_cloud_storage.py \
  tests/test_adapters/test_adapter_capabilities.py -v
```

Expect all green: `test_file_encryption.py` covers the `FileEncryptor`
primitive (round-trip, tamper detection, wrong key, AAD binding/ciphertext-swap
protection, missing/invalid key), the `EncryptedFileStorageBackend` contract,
and `FileProcessingService`-level opt-in behavior (per-adapter encryption,
fail-loud on missing config, fail-closed on lookup errors, metadata-merge
durability). The filesystem/cloud-storage/capabilities regression suites
should show no behavior change for anything that doesn't opt into encryption.

---

## Troubleshooting

- **Upload fails with "requires encrypted file storage" (S1):** either set
  `files.encryption.enabled: true` and `ORBIT_FILE_ENCRYPTION_KEY`, or remove
  `requires_encryption: true` from the adapter if encryption isn't actually
  needed for it.
- **Server refuses to start after enabling encryption (S2):**
  `ORBIT_FILE_ENCRYPTION_KEY` is missing, not valid base64, or doesn't decode
  to exactly 32 bytes. Regenerate with the command in step 0.
- **Download returns binary garbage instead of the file content (S4):** the
  file was uploaded while encryption was enabled but is now being read with
  encryption disabled/misconfigured — this should raise a clear error instead;
  if you see raw ciphertext returned, that's a regression of the fail-loud
  read-path check (`_select_storage_for_read` in `file_processing_service.py`).
- **A `failed`-then-retried encrypted upload comes back readable as plaintext,
  or reprocessing fails oddly (S5):** check that
  `FileMetadataStore.update_file_metadata` is merging into existing metadata
  rather than replacing `metadata_json` outright — a regression here silently
  drops the `encrypted` flag on any error/timeout write.
- **Swapped/corrupted ciphertext decrypts without error (S6):** this would mean
  the AAD (storage key) binding was removed from `encrypt`/`decrypt` calls in
  `encrypted_storage.py` — should never happen; if it does, treat it as a
  security regression, not a flaky test.
- **Plaintext adapter's files are suddenly encrypted, or vice versa:** check
  the adapter's `capabilities.requires_encryption` value and the global
  `files.encryption.enabled` — selection is per-adapter, and disabling the
  global switch only blocks *new* uploads through encryption-required
  adapters (it does not retroactively decrypt already-stored files).
- **Cloud backend (Part 2) round-trip works but bytes in the bucket look like
  plaintext:** confirm you're looking at the `classified-docs` adapter's
  upload, not the plain adapter's — encryption is per-adapter, not global to
  the bucket.
