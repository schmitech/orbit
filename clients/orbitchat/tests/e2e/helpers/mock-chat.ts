import type { Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// SSE body builder
// ---------------------------------------------------------------------------

interface Chunk {
  text?: string;
  done?: boolean;
  request_id?: string;
  assistant_message_id?: string;
}

function buildSseBody(chunks: Chunk[]): string {
  return chunks.map(c => `data: ${JSON.stringify(c)}\n\n`).join('');
}

/** Build a complete SSE body that streams `text` word-by-word then closes. */
export function chatSse(text: string, { requestId = 'req-test', assistantId = 'asst-test' } = {}): string {
  const words = text.split(' ');
  const chunks: Chunk[] = [
    { request_id: requestId }, // request_id-only first chunk (matches app expectation)
    ...words.map((w, i) => ({ text: i === 0 ? w : ` ${w}`, done: false })),
    { done: true, assistant_message_id: assistantId },
  ];
  return buildSseBody(chunks);
}

const SSE_HEADERS = {
  'Content-Type': 'text/event-stream',
  'Cache-Control': 'no-cache',
  'X-Accel-Buffering': 'no',
};

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

/** Mock the next chat request to respond with `responseText`. Unroutes itself after one use. */
export async function mockNextChat(page: Page, responseText: string): Promise<void> {
  await page.route('**/api/v1/chat', async route => {
    await page.unroute('**/api/v1/chat');
    await route.fulfill({ status: 200, headers: SSE_HEADERS, body: chatSse(responseText) });
  });
}

/**
 * Mock chat so the first request hangs indefinitely (simulating an active stream)
 * and subsequent requests respond with `editResponseText`.
 *
 * Returns a `releaseHang` function — call it to resolve the hanging request
 * early (e.g. after stopStreaming fires), or just let Playwright time it out.
 */
export function mockHangThenRespond(
  page: Page,
  editResponseText: string,
): { releaseHang: () => void } {
  let release: (() => void) | null = null;
  let callCount = 0;

  page.route('**/api/v1/chat', async route => {
    callCount++;
    if (callCount === 1) {
      // Hang until released or the test times out
      await new Promise<void>(resolve => { release = resolve; });
      // Respond with an empty done after release so the app stream loop exits
      await route.fulfill({
        status: 200,
        headers: SSE_HEADERS,
        body: buildSseBody([{ done: true, assistant_message_id: 'asst-cancelled' }]),
      });
    } else {
      await page.unroute('**/api/v1/chat');
      await route.fulfill({ status: 200, headers: SSE_HEADERS, body: chatSse(editResponseText) });
    }
  });

  return { releaseHang: () => release?.() };
}

/** Mock the stop endpoint so stopStreaming() resolves cleanly. */
export async function mockStopEndpoint(page: Page): Promise<void> {
  await page.route('**/api/v1/chat/stop', route =>
    route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json' }, body: '{}' }),
  );
}

// ---------------------------------------------------------------------------
// App config injection
// ---------------------------------------------------------------------------

/**
 * Inject a minimal ORBIT_CHAT_CONFIG so the app starts in single-adapter mode
 * without needing a real orbitchat.yaml or backend.
 * Call this in page.addInitScript() before navigation.
 */
export function injectTestConfig(): void {
  // This runs in the browser context — no imports allowed
  (window as Window & { ORBIT_CHAT_CONFIG?: object }).ORBIT_CHAT_CONFIG = {
    agentMode: { mode: 'single', defaultAdapterId: 'e2e-agent' },
    adapters: [{ id: 'e2e-agent', name: 'E2E Test Agent', apiUrl: 'http://localhost:3000' }],
    application: {
      name: 'ORBIT Chat',
      inputPlaceholder: 'Message ORBIT...',
      locale: 'en-US',
      favicon: '',
    },
    features: {
      enableUpload: false,
      enableVoice: false,
      enableFeedback: false,
      enableConversationThreads: false,
    },
    rateLimit: { maxRequestsPerWindow: 100, windowMs: 60000 },
  };
}
