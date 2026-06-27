# E2E Tests — OrbitChat

Playwright test suite covering the inline prompt edit + regenerate feature and its regression scenarios. All tests mock `/api/v1/chat` via `page.route()` — no real ORBIT backend is required.

## Setup

### 1. Install Playwright

```bash
cd clients/orbitchat
npm install
npx playwright install chromium
```

`@playwright/test` is already listed in `devDependencies`, so `npm install` handles the Node package. The `playwright install` step downloads the browser binary (≈ 130 MB, one-time).

### 2. Verify the dev server starts

The Playwright config (`playwright.config.ts`) spins up `npm run dev` automatically before each test run. If you already have a Vite server running on port 5173, it will be reused.

No `orbitchat.yaml` is needed — tests inject a minimal `window.ORBIT_CHAT_CONFIG` via `page.addInitScript()`.

---

## Running tests

```bash
# All scenarios (headless, default)
npm run test:e2e

# Watch mode — see the browser
npm run test:e2e:headed

# Single scenario by name
npx playwright test -g "Scenario 3"

# Specific file
npx playwright test tests/e2e/edit-regenerate.spec.ts

# Open HTML report after a run
npm run test:e2e:report
```

---

## Test structure

```
tests/
  e2e/
    README.md                    ← this file
    edit-regenerate.spec.ts      ← 11 tests covering all 9 playbook scenarios
    helpers/
      mock-chat.ts               ← SSE mock utilities, config injection
  playbooks/
    edit-regenerate-regression-playbook.md   ← manual test guide (source of truth)
```

### Helpers (`helpers/mock-chat.ts`)

| Export | Purpose |
|--------|---------|
| `chatSse(text)` | Build a multi-chunk SSE body from plain text |
| `mockNextChat(page, text)` | One-shot route mock — responds then unregisters itself |
| `mockHangThenRespond(page, text)` | First request hangs (simulates active stream); second responds. Returns `releaseHang()`. |
| `mockStopEndpoint(page)` | Mocks `/api/v1/chat/stop` → `{}` |
| `injectTestConfig()` | Browser-side function to set `window.ORBIT_CHAT_CONFIG` — call via `page.addInitScript()` |

---

## Playbook → spec mapping

| Playbook scenario | Spec test name |
|-------------------|---------------|
| 1 — Normal send persists | `Scenario 1: normal send streams and persists across reload` |
| 2 — Edit during active stream | `Scenario 2: edit during active stream does not corrupt regenerated response` |
| 3 — Edited branch persists | `Scenario 3: edited branch survives page reload` |
| 4 — Edit after stream (Enter key) | `Scenario 4: edit after completed stream; Enter key submits` |
| 5 — Stop button | `Scenario 5: stop button leaves UI in sane state; next message is clean` |
| 6 — Regenerate | `Scenario 6: regenerate still streams, finalises, and persists` |
| 7 — Repeat edit shows current content | `Scenario 7: second edit textarea shows post-edit content` |
| 8 — No-op cases | `Scenario 8a/8b/8c: Escape / unchanged / empty submit` |
| 9 — Button visibility | `Scenario 9: edit button hidden by default, visible on hover, not on assistant` |

---

## CI

Add this step to your GitHub Actions workflow after `npm install`:

```yaml
- name: Install Playwright browsers
  run: npx playwright install --with-deps chromium

- name: Run E2E tests
  run: npm run test:e2e
  env:
    CI: true

- name: Upload Playwright report
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: playwright-report
    path: playwright-report/
    retention-days: 7
```

With `CI=true`, `playwright.config.ts` enables 2 retries per test and always starts a fresh dev server.

---

## Troubleshooting

**`Error: No tests found`** — make sure `testDir` in `playwright.config.ts` points to `./tests/e2e` and the spec filename ends in `.spec.ts`.

**Port 5173 already in use** — either stop the existing dev server or set `reuseExistingServer: true` (already set for non-CI runs). In CI, the server is always started fresh.

**Opacity assertions flaky** — Tailwind's `group-hover` transitions can lag. If `Scenario 9` is flaky, add a brief `waitForTimeout(200)` after hover actions, or check that the `group` class is on the correct ancestor element in `Message.tsx`.

**`mockHangThenRespond` times out** — call `releaseHang()` before the test times out. In tests that test the stop button, call it just before or just after clicking stop.
