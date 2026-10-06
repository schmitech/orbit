# API Key Pepper Setup

ORBIT never stores API keys in plaintext. Only an HMAC-SHA256 hash of the key — peppered with
a server-side secret — is persisted in the `api_keys` collection/table (`api_key_hash`); the
raw key is returned to the caller once, in the creation response, and is not recoverable from
the database afterward. This guide covers setting up that pepper.

For the underlying schema see [`docs/sqlite-schema.md#api_keys`](../sqlite-schema.md#api_keys)
and [`docs/postgres-schema.md`](../postgres-schema.md) (MongoDB uses the same fields, schemaless).

## How it works

`ApiKeyService.hash_api_key()` computes `HMAC-SHA256(pepper, raw_key)` and stores only that
digest. Every lookup — request authentication, quota/throttle keying, rename, deactivate,
delete — hashes the presented key the same way and looks up the hash; the pepper is never
stored anywhere near the hashed keys themselves.

The pepper is resolved in this order:

1. `ORBIT_API_KEY_PEPPER` environment variable (recommended — keep it out of `config/*.yaml`
   and version control, same as any other secret in `.env`)
2. `api_keys.hash_pepper` in `config/config.yaml`
3. A fixed, built-in insecure default — used only so a fresh install still works out of the
   box. Using it logs a warning on every server start:

   ```
   ORBIT_API_KEY_PEPPER is not set; using an insecure built-in default to hash API keys.
   Set ORBIT_API_KEY_PEPPER (or api_keys.hash_pepper in config) to a random secret in production.
   ```

**Set a real pepper before going to production.** Without one, every ORBIT install shares the
same built-in default, which means anyone with read access to the source (it's public) could
verify a guessed key against a stolen hash — the pepper is what makes that infeasible.

## Setting it up

1. Generate a random secret:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Set it in `.env` (see [`env.example`](../../env.example)):

   ```env
   ORBIT_API_KEY_PEPPER=<the generated value>
   ```

3. Restart the server. No config file changes or migration step are required.

If you'd rather manage it through `secrets_management` (AWS/Azure/GCP) instead of `.env`, treat
`ORBIT_API_KEY_PEPPER` like any other secret name — see
[Cloud Secrets Management Setup](secrets-management-setup.md).

## Rotating the pepper

Changing the pepper invalidates every previously stored `api_key_hash` — a key hashed under the
old pepper will no longer match a lookup computed with the new one, and the row has no
recoverable plaintext to rehash from (unless it predates hashing entirely; see below). Treat a
pepper rotation like a full API key rotation: after changing `ORBIT_API_KEY_PEPPER`, every
existing key stops authenticating and must be recreated (`orbit key create`) and redistributed
to clients.

Before rotating, find out the blast radius:

```bash
orbit key rotate-pepper --dry-run
```

This reports how many active (and total) keys exist today — i.e. how many would stop
authenticating — so you know the blast radius before you act.

There is no way to avoid a break window with the current design: `ApiKeyService` looks up a key by
hashing it with whatever pepper is *currently* configured, so the moment `ORBIT_API_KEY_PEPPER`
changes, every existing key stops matching — including one created seconds beforehand under the
old pepper. A "generate new keys first, confirm they're in use, then rotate" sequence does not
work here; it would just add a second batch of keys that *also* break the instant you rotate.
Minimize the window instead:

1. Prepare in advance: have the full client list and your key-creation/redistribution tooling
   ready to run immediately after the rotation (e.g. scripted `orbit key create` calls per
   client), ideally during a maintenance window.
2. Change `ORBIT_API_KEY_PEPPER` and restart the server.
3. Immediately recreate and redistribute keys to every affected client.

Treat this like a full API key rotation across your whole client base, timed to minimize — not
eliminate — the outage.

If the pepper does change between restarts without this step having been run deliberately — for
example a misconfigured deployment losing track of the configured secret — `ApiKeyService` logs a
warning naming how many active keys will fail to validate, rather than each key failing silently
one at a time in production traffic. This detection is based on a non-reversible fingerprint of
the pepper persisted alongside the API key store; the pepper itself is never stored.

## Upgrading an existing installation

Rows created before this feature shipped have the real plaintext key in the legacy `api_key`
column and no `api_key_hash`. There is no bulk migration script and none is needed: the first
time each such key is successfully validated, `ApiKeyService._find_by_raw_key()` computes its
hash under whatever pepper is currently configured, backfills `api_key_hash` (and a
non-secret `key_suffix` used only for admin-panel display), and overwrites the legacy `api_key`
column with the hash — clearing the plaintext. This happens transparently, with no downtime and
no change in behavior for the caller.

Because this migration happens at first-use time under whatever pepper is active then, set
`ORBIT_API_KEY_PEPPER` **before** upgrading if you want existing keys migrated under a
deliberately chosen pepper rather than the insecure built-in default.

## Verifying

After setting the pepper and restarting, confirm the warning above no longer appears in the
server logs, and that a freshly created key's row in `api_keys` has `api_key_hash` populated
(inspect via `sqlite3`/`psql`/`mongosh` directly — there is no admin API that returns raw key
material).
