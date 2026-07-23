# Flavor Images Update Playbook

Step-by-step checklist for updating `schmitech/orbit-ollama`,
`schmitech/orbit-openai`, `schmitech/orbit-gemini` after a code or config
change. See [`docker/README.md`](README.md) for the full flag/option
reference and [`docs/docker-bundle-plan.md`](../docs/docker-bundle-plan.md)
for the design. Prerequisite: `docker login` to the `schmitech` Docker Hub
account (Docker Desktop's stored credentials work).

## 1. Decide if a flavor rebuild is actually needed

Rebuild when you changed any of:

- `server/`, `bin/` (ORBIT code)
- `install/default-config/` (canonical config — the resolver's source of truth)
- `docker/runtime_profiles.py`, `docker/entrypoint-flavor.sh`, `docker/Dockerfile.flavor`
- `clients/orbitchat/` (UI code)

You do **not** need a flavor rebuild for changes to `docker/Dockerfile`,
`docker/docker-entrypoint.sh`, `docker/publish.sh`, or `docker/compose/*` —
those belong to the separate lean server-only image.

## 2. Rebuild orbitchat if you touched it

`docker/Dockerfile.flavor` copies the **prebuilt** `clients/orbitchat/dist/`;
it does not run a build inside the image.

```bash
cd clients/orbitchat && npm ci && npm run build && cd ../..
```

Skip this step if `clients/orbitchat/` didn't change — the existing `dist/`
is still valid.

## 3. Run the resolver unit tests

Fast, catches profile/config regressions before spending time on a Docker build.

```bash
python -m pytest docker/tests/ -q
python -m ruff check docker/
```

## 4. Build one flavor locally and smoke-test it

Always test at least one flavor end-to-end before publishing — a clean
server start is not proof the chat path works (see the enabled-flag bug
history in `docs/docker-bundle-plan.md`). `openai` is the cheapest to
iterate on (no Ollama binary/model pull).

```bash
cd docker
docker build -f Dockerfile.flavor \
  --build-arg ORBIT_FLAVOR=openai --build-arg INCLUDE_OLLAMA=false \
  -t orbit-flavor-test:openai ..

docker rm -f orbit-flavor-test 2>/dev/null
docker run -d --name orbit-flavor-test -p 13000:3000 -p 15173:5173 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  orbit-flavor-test:openai

# Wait for health, then check the log for an actual failure vs. false-positive success
until curl -sf http://localhost:13000/health >/dev/null 2>&1 || \
      [ "$(docker inspect -f '{{.State.Status}}' orbit-flavor-test 2>/dev/null)" != "running" ]; do
  sleep 2
done
docker logs orbit-flavor-test | grep -A3 "CONFIGURATION WARNING" || echo "no registry warnings — good"
```

**Prove the chat path actually works** (not just that the container started):

```bash
curl -s -X POST http://localhost:13000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: multimodal' \
  -H 'X-Session-ID: playbook-smoke-test' \
  -d '{"messages":[{"role":"user","content":"hello"}]}'
```

With a real API key you should get a real reply. With a placeholder/invalid
key you should still get a **provider-level** error (e.g. an OpenAI auth
error) — if you instead see `"No service registered for inference with
provider ..."`, the resolver isn't enabling that provider and something in
step 1 broke it; do not publish until this is fixed.

If you changed the ollama flavor specifically (inference.yaml, ollama.yaml
presets, or the gemma4 model choice), also build and run it at least once —
the model pull adds several GB/minutes, so it's fine to skip this for
changes clearly scoped to openai/gemini only.

```bash
docker build -f Dockerfile.flavor \
  --build-arg ORBIT_FLAVOR=ollama --build-arg INCLUDE_OLLAMA=true \
  -t orbit-flavor-test:ollama ..

docker rm -f orbit-flavor-test 2>/dev/null
docker run -d --name orbit-flavor-test -p 13000:3000 -p 15173:5173 \
  -v orbit-flavor-test-models:/orbit/models \
  orbit-flavor-test:ollama
```

Repeat the same health-check and chat-completion checks as above (no
`X-API-Key`/API-key env var needed — the ollama flavor requires no
credential), then clean up:

```bash
docker rm -f orbit-flavor-test 2>/dev/null
docker rmi orbit-flavor-test:ollama 2>/dev/null
docker volume rm orbit-flavor-test-models 2>/dev/null
```

```bash
docker rm -f orbit-flavor-test 2>/dev/null
docker rmi orbit-flavor-test:openai 2>/dev/null
```

## 5. Bump the version tag

Pick the next semver tag (check existing tags: `docker manifest inspect
schmitech/orbit-openai:latest` or the Docker Hub UI). There's no `:basic`
suffix or `-openai` config-dir tagging scheme here — each flavor is its own
repository, so the tag is just the version, e.g. `1.1.0`.

## 6. Build and publish all three flavors

```bash
cd docker
./publish-flavor.sh --publish --all-flavors --tag <NEW_VERSION>
```

This builds all three (`ollama` with `INCLUDE_OLLAMA=true`, `openai`/`gemini`
without) and pushes `:latest` + `:<NEW_VERSION>` to each repository. To
update a single flavor only (e.g. a fix that only touches the gemini
profile):

```bash
./publish-flavor.sh --publish --flavor gemini --tag <NEW_VERSION>
```

## 7. Verify what's actually live

Local build success doesn't confirm the push landed — pull it back down:

```bash
for repo in orbit-ollama orbit-openai orbit-gemini; do
  docker pull schmitech/$repo:latest
  docker pull schmitech/$repo:<NEW_VERSION>
done
```

Then do a clean pull-and-run exactly as documented in the main
[`README.md`](../README.md) quick start, from a directory without this
repository checked out, to confirm the published image works the way a new
user would experience it.

## 8. Record the change

Note the new version tag in your release notes / changelog if the project
keeps one. There's no separate "flavor images changelog" — these ride along
with the main ORBIT version.

## Known gap

`publish-flavor.sh` only builds from the current checkout — it does not
support `--source release`/`local-tarball` like `docker/publish.sh` does,
because `utils/scripts/build-tarball.sh` doesn't currently package
`clients/orbitchat/`. If you need to publish a flavor image from a tagged
release rather than a working checkout, update `build-tarball.sh` first (or
`git checkout` the release tag locally before running this playbook).
