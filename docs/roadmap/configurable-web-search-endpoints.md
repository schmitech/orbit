# Configurable Web Search Provider Endpoints — Implementation Plan

## Summary

Every provider in `server/web_search/providers/*.py` hardcodes its API URL
(e.g. `serper.py`'s `https://google.serper.dev/search`,
`webz.py`'s `https://api.webz.io/newsApiLite`). This was fine while each
provider exposed exactly one endpoint, but Webz.io exposes several distinct
endpoints under the same API key (News API Lite, Dark Web, Reviews,
Conversations, etc.), each with a different purpose. An operator should be
able to pick which Webz.io endpoint — or any future provider's alternate
endpoint — an adapter talks to, via config, without a code change.

Today two providers already have an ad hoc version of this: Perplexity's
`api_url` kwarg and SearXNG's required `query_url`. The goal is to
generalize that into one first-class config option, `endpoint_url`, that
every `httpx`-based provider accepts — operator sets it in
`config/adapters/*.yaml`, no code change.

**Scope correction from the original draft:** this plan previously proposed
`base_url` and used Webz.io's Dark Web endpoint as the worked example. Both
need revision before implementation:

- Webz.io's Dark Web search lives at `/cyberFilter` and returns a
  `cyberDocs` array, not `posts` — the `webz.py` provider added alongside
  this plan only parses `posts` (News API Lite's shape). Pointing
  `endpoint_url` at `/cyberFilter` today would get a 200 response that
  normalizes to zero results, silently. Dark Web access is also a
  separately-gated Webz.io product tier, so it may 403 for accounts without
  it regardless. The first worked example in this doc instead uses Webz.io's
  **Blogs** endpoint, `https://api.webz.io/api/blogs` — documented by
  Webz.io as `posts`-shaped, the same response shape `webz.py` already
  parses, so the example is provably correct with no new parsing code.
  (Webz.io's older `/filterWebContent` path is documented as deprecated in
  favor of `/api/blogs` — don't use it in the shipped example or docs.)
  Dark Web support is a separate follow-up that needs its own response
  parser and fixture test (see "Follow-up: Dark Web support" below), not a
  same-shape URL swap.
- `base_url` implied a host-only override with a fixed path appended by the
  provider. That's not what's needed here — Webz.io's different endpoints
  are different full paths (`/newsApiLite` vs. `/filterWebContent` vs.
  `/cyberFilter`), not just different hosts. Naming the option `endpoint_url`
  makes clear it's the complete request URL, path included.

## Current state

- `server/web_search/base.py` — shared `SearchResult` + `get_filtered_results`.
- `server/web_search/registry.py` — `PROVIDERS: dict[str, callable]` maps a
  provider name to its `search_<name>` function.
- `server/inference/pipeline/steps/web_search.py` (`WebSearchStep.process`) —
  reads the adapter's `web_search` block, strips `provider`/`result_count`/
  `filter_list`, and passes everything else through as `**provider_kwargs` to
  the resolved `search_fn`.
- Each `search_<name>(api_key, query, count, filter_list=None, ...)` function
  hardcodes its own URL as a local variable and ignores any URL-like kwarg
  except `perplexity.py`, which already accepts `api_url` and defaults it.

Because `WebSearchStep` already forwards arbitrary extra keys from the
`web_search` block as kwargs, no pipeline change is strictly required to let
*one* provider accept a URL override — `webz.py` could add an `endpoint`
parameter today and it would work. The actual gap is consistency and
discoverability: every provider should accept the override the same way, with
the same key name, a sane default, and basic validation, rather than each
provider inventing its own convention (`api_url` vs. `endpoint` vs. nothing).

## Design

### 1. Standardize on one override key: `endpoint_url`

- Every `httpx`-based provider gains an optional `endpoint_url: str | None`
  parameter — the full request URL, path included — defaulting to that
  provider's current hardcoded URL when omitted. No behavior change for
  existing configs that don't set it.
- `duckduckgo.py` is explicitly **excluded**: it calls the `ddgs` SDK
  (`DDGS(...).text(...)`), not an HTTP endpoint directly — there is no URL
  for it to accept. Its existing `backend` kwarg remains the only way to
  steer it.
- Perplexity's `api_url` and SearXNG's `query_url` become **aliases** for
  `endpoint_url`, not replacements:
  - Both providers accept all three of `endpoint_url`, their legacy name,
    and neither — `endpoint_url` takes precedence if more than one is set.
  - This avoids a breaking change for existing `PERPLEXITY_API_URL`/
    `SEARXNG_URL`-based configs while giving every provider one documented,
    consistent name going forward.
  - SearXNG keeps its current **required** semantics for the resolved value
    (`endpoint_url` or `query_url` — one of the two must be present; neither
    gets a hardcoded default, since there's no single correct public SearXNG
    instance). This is a behavior-preserving rename-with-alias, not a
    relaxation of the existing requirement.

### 2. Provider signature convention

`resolve_endpoint_url()` — not a bare `or` — is the only way a provider
resolves its URL, so every provider enforces the same validation contract
(Design §3) instead of each reimplementing it slightly differently:

```python
DEFAULT_ENDPOINT_URL = "https://api.webz.io/newsApiLite"  # unchanged from today's hardcoded default

async def search_webz(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    *,
    endpoint_url: str | None = None,
) -> list[SearchResult]:
    url = resolve_endpoint_url(endpoint_url, DEFAULT_ENDPOINT_URL, provider="webz")
    ...
```

Module-level `DEFAULT_ENDPOINT_URL` constants (rather than inline literals)
make the default visible without reading the function body. `endpoint_url`
is keyword-only (`*,`) on every provider from the start, so it never
contends for a positional slot.

For Perplexity (aliasing case — `api_url` keeps its existing fifth
positional slot unchanged; only the new `endpoint_url` is keyword-only):

```python
async def search_perplexity(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    api_url: str = _DEFAULT_API_URL,   # existing positional slot, unchanged
    *,
    endpoint_url: str | None = None,   # new, keyword-only
) -> list[SearchResult]:
    # `is not None`, not truthy — an explicitly blank "" must still hit
    # resolve_endpoint_url() and raise, rather than silently falling through
    # to api_url because "" is falsy (that's the blank-overrides-a-valid-
    # alias case from Design §3).
    if endpoint_url is not None:
        url = resolve_endpoint_url(endpoint_url, _DEFAULT_API_URL, provider="perplexity")
    else:
        if api_url != _DEFAULT_API_URL:
            log.warning("perplexity: 'api_url' is deprecated, use 'endpoint_url'")
        url = resolve_endpoint_url(api_url, _DEFAULT_API_URL, provider="perplexity")
    ...
```

A blank `endpoint_url` (e.g. `endpoint_url: ""` from an unresolved `${VAR}`)
raises via `resolve_endpoint_url()` even when a valid `api_url` is also
present — an explicitly-set-but-empty new key is a configuration error on
its own terms, not something a working legacy alias should paper over.

SearXNG needs one additional change beyond the Perplexity shape:
`query_url` is currently a **required positional** parameter
(`search_searxng(query_url, query, count, ...)`), so a call passing only
`endpoint_url` would raise `TypeError: missing required argument 'query_url'`
before `resolve_endpoint_url()` ever runs. `query_url` becomes optional
(`query_url: str | None = None`), keeping its existing position so existing
positional callers are unaffected.

`query` and `count` sit after `query_url` in that same positional list, so
giving `query_url` a default forces Python's own syntax rules to require a
default on them too — but they must stay genuinely required, not quietly
become optional with a throwaway value. Giving them real-looking defaults
(e.g. `query: str = ""`, `count: int = 5`) would satisfy the interpreter
while silently breaking the "required" contract: a caller that omits `query`
would search for `""` instead of getting a `TypeError`. Use a sentinel
instead, so Python's syntax is satisfied but omission is still caught and
raised explicitly:

```python
_REQUIRED = object()  # sentinel — query/count must stay required despite
                       # needing *some* default so query_url can precede them

async def search_searxng(
    query_url: str | None = None,   # existing positional slot, now optional
    query: str = _REQUIRED,
    count: int = _REQUIRED,
    filter_list: list[str | None] | None = None,
    *,
    endpoint_url: str | None = None,   # new, keyword-only
    **kwargs,
) -> list[SearchResult]:
    if query is _REQUIRED or count is _REQUIRED:
        raise TypeError("search_searxng() missing required argument: 'query' and/or 'count'")

    if endpoint_url is not None:
        url = resolve_endpoint_url(endpoint_url, None, provider="searxng")
    elif query_url is not None:
        url = resolve_endpoint_url(query_url, None, provider="searxng")
    else:
        raise ValueError("searxng: one of 'endpoint_url' or 'query_url' is required")
    ...
```

(`resolve_endpoint_url(value, None, ...)` — a `None` default — still raises
on a blank/malformed *value*; it just has no fallback to use when the value
is *omitted* entirely, which is handled by the `elif`/`else` above instead,
preserving SearXNG's "no hardcoded default" property from Design §1.)

### 3. Fallback and runtime-selection behavior (explicit)

- **Omitted** (`endpoint_url` key absent from the `web_search` block): use
  the provider's `DEFAULT_ENDPOINT_URL` — today's behavior, unchanged.
- **Blank** (`endpoint_url: ""`, including an unresolved `${VAR}` that
  collapses to an empty string): treat as a configuration error, not as
  "use the default." Raise/`context.set_error(...)` with a message naming
  the provider and the empty key, surfaced the same way `WebSearchStep`
  already surfaces a `ValueError` from `get_provider`. This is a change from
  the original draft, which had `endpoint_url or DEFAULT` silently fall back
  on empty string — that hides a broken env var behind what looks like
  correct behavior (e.g. an operator who meant to point at Dark Web
  silently gets News results instead).
- **Malformed** (fails URL parsing, scheme isn't `http`/`https`, or no
  hostname — e.g. `endpoint_url` must be an absolute URL like
  `https://api.webz.io/api/blogs`, not a bare path such as `/api/blogs` or a
  scheme-only value): same explicit-error treatment as blank — fail fast
  with a clear message rather than letting `httpx` raise its own
  lower-level connection error.
- **Blank overrides a valid legacy alias.** If both `endpoint_url` and a
  provider's legacy alias (`api_url`/`query_url`) are set, and
  `endpoint_url` is blank, that is still a configuration error — the
  presence of a working legacy value does not rescue an explicitly-set-but-
  empty new key. Only an *omitted* `endpoint_url` key falls through to the
  legacy alias (or the default).
- URLs stay entirely in operator-controlled config (`config/adapters/*.yaml`
  / env vars) — never user/request-controlled — since the resolved URL
  determines where that provider's API key and the user's search query are
  sent. No request-time field may set or influence `endpoint_url`.
- **Runtime provider selection** (`allowed_search_providers` /
  `runtime_search_provider_overrides`, see `web_search.py:45-48`): a
  selected entry *replaces* the adapter's static `web_search` block
  entirely, so `endpoint_url` must be set on each `allowed_search_providers`
  entry that needs a non-default URL — it is **not** inherited from the
  adapter's base `web_search` block. Document this explicitly (it's an easy
  mistake: setting `endpoint_url` only on the static block and expecting a
  runtime-selected `"webz"` override to pick it up). Test both paths:
  static `web_search.endpoint_url` and an `allowed_search_providers` entry's
  own `endpoint_url`.

### 4. Documentation

- `docs/adapters/web-search.md`:
  - `web_search` block options table: add `endpoint_url` / "All
    `httpx`-based providers (not DuckDuckGo) — overrides the provider's
    default request URL." Keep `api_url` (Perplexity) and `query_url`
    (SearXNG) rows, marked as deprecated aliases for `endpoint_url`.
  - Supported search backends table: add a note next to `webz` that it
    exposes multiple endpoints (News, Blogs, Forums, Reviews, Dark Web,
    etc., each a different path) and that `endpoint_url` selects one.
  - "Adding a New External Search Provider" checklist: add a step to define
    a `DEFAULT_ENDPOINT_URL` constant and accept `endpoint_url` for any new
    `httpx`-based provider.
  - New subsection on runtime provider selection: `endpoint_url` must be
    repeated per `allowed_search_providers` entry, per point 3 above.
- `config/adapters/web-search-providers.yaml` header comment: document
  `endpoint_url` alongside the existing `api_key`/`query_url`/`api_url`
  option list, noting the alias/precedence rule, and add a second
  `web-search-webz-blogs` example adapter using
  `endpoint_url: "https://api.webz.io/api/blogs"` (not Dark Web — see
  Summary) showing the override in use.

## Tasks

- [x] Implement `resolve_endpoint_url(value, default, *, provider)` in
      `server/web_search/base.py` first — every other task depends on it.
      Enforces Design §3: omitted → `default`; blank → raise; not an
      absolute `http(s)` URL with a hostname → raise. One shared
      implementation, not reimplemented per provider.
- [x] Add `DEFAULT_ENDPOINT_URL` + keyword-only `endpoint_url` param (via
      `resolve_endpoint_url()`) to every `httpx`-based provider in
      `server/web_search/providers/`: `brave.py`, `deepseek.py`,
      `google_pse.py`, `serper.py`, `tavily.py`, `webz.py`. `webz.py`'s
      `DEFAULT_ENDPOINT_URL` stays `https://api.webz.io/newsApiLite` — the
      existing hardcoded default, unchanged, so adapters that don't set
      `endpoint_url` keep getting News results exactly as today. The
      `https://api.webz.io/api/blogs` URL from the shipped example is set
      only on the new example adapter's `endpoint_url`, never as the
      provider's default.
      `duckduckgo.py` is excluded (SDK-based, no URL — see Design §1).
- [x] `perplexity.py`: add keyword-only `endpoint_url`, resolved via
      `resolve_endpoint_url()`. Preserve `api_url`'s existing fifth
      positional slot and default unchanged — do not move it or make it
      keyword-only — so existing positional callers (if any) and the
      existing `allowed_search_providers`/`web_search` kwarg usage keep
      working. Log a deprecation warning when `api_url` is set to a
      non-default value and `endpoint_url` is omitted.
- [ ] `searxng.py`: make `query_url` optional (`str | None = None`, keeping
      its existing position so current positional callers are unaffected)
      and add keyword-only `endpoint_url`, same precedence rule. `query` and
      `count` must stay genuinely required even though they now sit after an
      optional parameter — use the sentinel-default + explicit
      `is _REQUIRED` check from Design §2's SearXNG example (not a
      throwaway default like `""`/`5`), so an omitted `query`/`count` still
      raises `TypeError` instead of silently searching for an empty string.
      The "one of the two URL keys required" check moves inside the
      function body — a call passing only `endpoint_url` must not raise
      `TypeError` on a still-required `query_url` before validation ever
      runs. Keep the `<query>`-placeholder-stripping behavior unchanged for
      whichever of the two URL keys resolves.
- [ ] Update `docs/adapters/web-search.md` and the
      `config/adapters/web-search-providers.yaml` header comment per
      "Documentation" above, including the runtime-selection caveat.
- [ ] `env.example`: add `WEBZ_BLOGS_API_URL=https://api.webz.io/api/blogs`
      as the example override var, paired with a `${VAR:-default}` fallback
      so plain `WEBZ_API_KEY` users see no change.
- [ ] Tests — `webz.py`, `perplexity.py`, **and** `searxng.py` each need
      their own coverage; the two alias providers have different
      compatibility requirements (a defaulted positional `api_url` vs. a
      required-with-no-default `query_url`), so testing only one leaves a
      gap in the other's contract:
      - **`webz.py`**: two separate assertions on *which URL was called*,
        not just that the call succeeded — (a) omitting `endpoint_url`
        calls `https://api.webz.io/newsApiLite` (the unchanged default);
        (b) setting `endpoint_url: "https://api.webz.io/api/blogs"` calls
        that URL instead. Blank/malformed `endpoint_url` raises. A fixture
        response shaped like the Blogs example (one post, `posts`-shaped)
        normalizes to a `SearchResult` when fetched via the override — this
        both verifies the override and proves the shipped example actually
        works end to end (see "Documentation").
      - **`perplexity.py`**: default (`api_url` at its default, no
        `endpoint_url`) unchanged; legacy `api_url` set to a non-default
        value with `endpoint_url` omitted still works and logs the
        deprecation warning; `endpoint_url` set wins over a simultaneously-
        set non-default `api_url`; blank `endpoint_url` raises even when
        `api_url` is validly set (Design §3's "blank overrides a valid
        alias" case).
      - **`searxng.py`**: existing `query_url`-only path still works
        unchanged, including its `<query>`-placeholder-stripping behavior
        and existing positional call signature; a call supplying **only**
        `endpoint_url` (`query_url` omitted entirely) succeeds and is
        resolved — this is the case that would previously raise
        `TypeError` before the signature change, so it's the one test that
        actually proves the fix in Design §2; both `endpoint_url` and
        `query_url` omitted raises `ValueError` (today's "one required"
        behavior, preserved); `endpoint_url` set wins when both are set;
        blank `endpoint_url` raises even when `query_url` is validly set;
        **omitting `query` or `count`** (the two now sitting after an
        optional `query_url`) still raises `TypeError`, proving the
        sentinel-default didn't quietly turn them into optional args with a
        throwaway value.
      - An `allowed_search_providers` entry's own `endpoint_url` is honored
        independently of the adapter's static `web_search` block (one test,
        any provider).

## Follow-up: Dark Web support (separate change)

Out of scope for this plan's first cut (see Summary). Once a `posts`-shaped
endpoint ships `endpoint_url` successfully:

- [ ] Add Dark Web response handling: `/cyberFilter` returns `cyberDocs`, not
      `posts` — `webz.py` needs a second parsing path (or the registry needs
      a `webz_darkweb` provider entry with its own function) since the field
      names and likely the available metadata differ.
- [ ] Fixture-based test asserting the `cyberDocs` shape normalizes to
      `SearchResult` correctly.
- [ ] Document the separate Webz.io product-tier/permission requirement for
      Dark Web access, so a 403 from an unentitled account isn't mistaken for
      a config bug.

## Non-goals

- No admin-panel UI work — this is a YAML/env config capability only, same
  scope as the rest of `web-search-providers.yaml`.
- No change to `WebSearchStep` itself — the existing pass-through-kwargs
  mechanism already supports this; this plan is purely about giving each
  provider function a consistent parameter to receive it, plus the shared
  validation helper in `base.py`.
- No multi-endpoint-per-request support (e.g. querying News + Dark Web in
  one call and merging results) — each adapter/skill targets one endpoint,
  matching today's one-provider-per-adapter model. Fan-out across endpoints
  is a composite-adapter concern, out of scope here.

## Known gaps

- `duckduckgo.py` has no URL-override mechanism and isn't getting one here
  (see Design §1) — operators needing a specific DuckDuckGo deployment are
  out of scope.
- `endpoint_url`, once resolved and validated as a well-formed `http(s)` URL,
  is still forwarded to `httpx` as-is; a URL that's syntactically valid but
  wrong (points at an unrelated or unreachable host) fails at request time
  with the provider's own exception, surfaced by `WebSearchStep`'s existing
  `except Exception` → `context.set_error(...)` path. That's unchanged from
  today's behavior for a bad `api_key` and is intentionally not expanded —
  ORBIT can't validate that an arbitrary operator-supplied URL is "the right"
  endpoint, only that it's well-formed.
