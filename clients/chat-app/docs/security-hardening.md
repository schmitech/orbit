# Security Hardening Follow-Ups

The changes made for backend synchronization and adapter endpoint obfuscation are working well, but there are a few additional hardening steps worth tracking before shipping to production. Revisit these items when preparing the next release.

1. **Protect the middleware proxy**
   - Add lightweight authentication (shared secret header or token) so only trusted clients can reach `/api/*` when the proxy is exposed over a network.
   - ~~Rate-limit or log adapter selection attempts to detect brute-force adapter-name probes.~~ ✅ **DONE** - Redis-backed rate limiting implemented (see `docs/rate-limiting-architecture.md`). Limits apply per IP (60/min, 1000/hr) and per API key (120/min, 5000/hr). Exceeded limits are logged with IP/API key info.

2. **Tighten CORS/CSRF posture**
   - In `config/middleware_configurator.py`, restrict `allow_origins` to the actual UI origin instead of `"*"`.
   - Consider rejecting cross-site `POST` requests lacking an expected custom header to mitigate CSRF via the proxy.

3. **Reduce fingerprintable headers**
   - Strip or override headers such as `Server`, `X-Powered-By`, and Express defaults in both the middleware (Express) and FastAPI stacks.
   - Ensure reverse proxies / load balancers also hide internal infrastructure headers.

4. **Review client-side persistence**
   - `localStorage` currently holds API keys, adapter names, and session IDs; evaluate encrypting these values or moving them to `sessionStorage` if the app runs in shared environments.
   - Provide a UI action to nuke all local storage and session identifiers after logout/timeout.

5. **Document operational procedures**
   - Capture the above guardrails (auth requirements, CORS policy, header sanitation) in the deployment runbook so operators know the expectations for staging vs. production environments.

Tracking these items ensures the middleware layer stays opaque and limits exposure if the chat UI is deployed beyond localhost.
