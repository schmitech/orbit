/**
 * E2E tests for the inline prompt edit + regenerate feature.
 *
 * Covers all scenarios from tests/playbooks/edit-regenerate-regression-playbook.md.
 * Each test mocks /api/v1/chat via page.route() so no real ORBIT backend is needed.
 *
 * Run:
 *   npx playwright test
 *   npx playwright test --headed          # watch the browser
 *   npx playwright test -g "Scenario 2"   # single scenario
 */

import { test, expect, type Page } from '@playwright/test';
import {
  injectTestConfig,
  mockNextChat,
  mockHangThenRespond,
  mockStopEndpoint,
} from './helpers/mock-chat';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/** Navigate to the app and wait for the chat input to be ready. */
async function openApp(page: Page) {
  await page.addInitScript(injectTestConfig);
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: /message/i })).toBeVisible({ timeout: 10_000 });
}

/** Type `text` into the main composer and submit. */
async function sendMessage(page: Page, text: string) {
  const input = page.getByRole('textbox', { name: /message/i });
  await input.fill(text);
  await input.press('Enter');
}

/** Wait until no assistant bubble is in streaming state. */
async function waitForStreamDone(page: Page) {
  await expect(page.locator('.message-bubble-user')).toBeVisible();
  // The loading state clears when isStreaming = false on the last assistant message
  await expect(page.locator('.streaming-cursor')).toHaveCount(0, { timeout: 15_000 });
}

/** Hover over the last user bubble and click the edit pencil. */
async function clickEditOnLastUserMessage(page: Page) {
  const bubble = page.locator('.message-bubble-user').last();
  await bubble.hover();
  await page.getByRole('button', { name: /edit message/i }).click();
}

// ---------------------------------------------------------------------------
// Before each: inject config + mock the stop endpoint
// ---------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await mockStopEndpoint(page);
});

// ---------------------------------------------------------------------------
// Scenario 1 — Normal send still streams and persists
// ---------------------------------------------------------------------------

test('Scenario 1: normal send streams and persists across reload', async ({ page }) => {
  await mockNextChat(page, 'Item one Item two Item three');
  await openApp(page);
  await sendMessage(page, 'Write a list');
  await waitForStreamDone(page);

  // Response appears in one assistant bubble
  await expect(page.locator('.message-bubble-assistant, .message-bubble')).toContainText('Item one');

  // Persist check — reload and the conversation is still there
  await page.reload();
  await expect(page.locator('.message-bubble-user')).toContainText('Write a list');
  await expect(page.getByText('Item one')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Scenario 2 — Edit while active stream is running
// ---------------------------------------------------------------------------

test('Scenario 2: edit during active stream does not corrupt regenerated response', async ({ page }) => {
  const EDIT_RESPONSE = 'EDIT REGENERATION TARGET';
  const { releaseHang } = mockHangThenRespond(page, EDIT_RESPONSE);

  await openApp(page);
  await sendMessage(page, 'Write a long explanation of HTTP caching');

  // App enters loading state (stream has started but not finished)
  await expect(page.locator('.message-bubble-user')).toBeVisible();

  // Edit the user message while the stream is still running
  await clickEditOnLastUserMessage(page);
  const textarea = page.locator('.message-bubble-user textarea').last();
  await expect(textarea).toBeVisible();
  await textarea.fill('Reply with exactly: EDIT REGENERATION TARGET');

  // Release the hanging stream so stopStreaming() can complete
  releaseHang();

  await textarea.press('Enter');
  await waitForStreamDone(page);

  // Edited prompt is shown, no old HTTP caching text leaks in
  await expect(page.locator('.message-bubble-user').last()).toContainText('EDIT REGENERATION TARGET');
  const assistantContent = await page.locator('.message-bubble').last().textContent();
  expect(assistantContent).not.toContain('HTTP caching');
  expect(assistantContent).toContain('EDIT REGENERATION TARGET');
});

// ---------------------------------------------------------------------------
// Scenario 3 — Edit/regenerate persists across reload
// ---------------------------------------------------------------------------

test('Scenario 3: edited branch survives page reload', async ({ page }) => {
  await mockNextChat(page, 'ORIGINAL PROMPT RESPONSE');
  await openApp(page);
  await sendMessage(page, 'Reply with exactly: ORIGINAL PROMPT RESPONSE');
  await waitForStreamDone(page);

  // Edit the message
  await mockNextChat(page, 'EDITED PROMPT RESPONSE');
  await clickEditOnLastUserMessage(page);
  const textarea = page.locator('.message-bubble-user textarea').last();
  await textarea.fill('Reply with exactly: EDITED PROMPT RESPONSE');
  await textarea.press('Enter');
  await waitForStreamDone(page);

  // Verify edited content before reload
  await expect(page.locator('.message-bubble-user').last()).toContainText('EDITED PROMPT RESPONSE');
  await expect(page.getByText('ORIGINAL PROMPT RESPONSE')).toHaveCount(0);

  // Reload — edited branch must still be present
  await page.reload();
  await expect(page.locator('.message-bubble-user')).toContainText('EDITED PROMPT RESPONSE');
  await expect(page.getByText('ORIGINAL PROMPT RESPONSE')).toHaveCount(0);

  // localStorage spot-check
  const stored = await page.evaluate(() => {
    const raw = Object.values(localStorage).find(v => v.includes('conversations'));
    return raw ?? '';
  });
  expect(stored).toContain('EDITED PROMPT RESPONSE');
  expect(stored).not.toContain('ORIGINAL PROMPT RESPONSE');
});

// ---------------------------------------------------------------------------
// Scenario 4 — Edit after completed stream (keyboard: Enter submits)
// ---------------------------------------------------------------------------

test('Scenario 4: edit after completed stream; Enter key submits', async ({ page }) => {
  await mockNextChat(page, 'Red Blue Green');
  await openApp(page);
  await sendMessage(page, 'Give me three colors');
  await waitForStreamDone(page);

  await mockNextChat(page, 'Apple Banana Cherry');
  await clickEditOnLastUserMessage(page);
  const textarea = page.locator('.message-bubble-user textarea').last();
  await textarea.fill('Give me three fruits');
  await textarea.press('Enter'); // must submit, not insert newline
  await waitForStreamDone(page);

  await expect(page.locator('.message-bubble-user').last()).toContainText('Give me three fruits');
  await expect(page.getByText('Apple')).toBeVisible();
  await expect(page.getByText('Red')).toHaveCount(0); // old response gone

  // Reload persistence
  await page.reload();
  await expect(page.locator('.message-bubble-user')).toContainText('Give me three fruits');
});

// ---------------------------------------------------------------------------
// Scenario 5 — Stop button still works
// ---------------------------------------------------------------------------

test('Scenario 5: stop button leaves UI in sane state; next message is clean', async ({ page }) => {
  const { releaseHang } = mockHangThenRespond(page, 'AFTER STOP');

  await openApp(page);
  await sendMessage(page, 'Write a 2000 word essay');

  // Click stop while loading
  await expect(page.locator('.message-bubble-user')).toBeVisible();
  const stopBtn = page.getByRole('button', { name: /stop/i });
  await expect(stopBtn).toBeVisible({ timeout: 5_000 });
  releaseHang();
  await stopBtn.click();

  // UI should exit loading state
  await expect(page.locator('.streaming-cursor')).toHaveCount(0, { timeout: 10_000 });

  // Send a new message — must work and not be contaminated
  await mockNextChat(page, 'AFTER STOP');
  await sendMessage(page, 'Reply with: AFTER STOP');
  await waitForStreamDone(page);
  await expect(page.getByText('AFTER STOP')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Scenario 6 — Regenerate existing assistant response
// ---------------------------------------------------------------------------

test('Scenario 6: regenerate still streams, finalises, and persists', async ({ page }) => {
  await mockNextChat(page, 'WebSockets original response');
  await openApp(page);
  await sendMessage(page, 'Summarise WebSockets');
  await waitForStreamDone(page);

  await mockNextChat(page, 'WebSockets regenerated response');
  const regenBtn = page.getByRole('button', { name: /regenerate/i });
  await regenBtn.click();
  await waitForStreamDone(page);

  await expect(page.getByText('regenerated response')).toBeVisible();

  await page.reload();
  await expect(page.getByText('regenerated response')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Scenario 7 — Repeat edit shows current content, not original
// ---------------------------------------------------------------------------

test('Scenario 7: second edit textarea shows post-edit content', async ({ page }) => {
  await mockNextChat(page, 'FIRST SEND response');
  await openApp(page);
  await sendMessage(page, 'Reply with exactly: FIRST SEND');
  await waitForStreamDone(page);

  // First edit
  await mockNextChat(page, 'FIRST EDIT response');
  await clickEditOnLastUserMessage(page);
  let textarea = page.locator('.message-bubble-user textarea').last();
  await textarea.fill('Reply with exactly: FIRST EDIT');
  await textarea.press('Enter');
  await waitForStreamDone(page);

  // Second edit — textarea must show FIRST EDIT, not FIRST SEND
  await clickEditOnLastUserMessage(page);
  textarea = page.locator('.message-bubble-user textarea').last();
  await expect(textarea).toHaveValue('Reply with exactly: FIRST EDIT');
  expect(await textarea.inputValue()).not.toContain('FIRST SEND');

  // Cancel without submitting
  await page.keyboard.press('Escape');
  await expect(textarea).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// Scenario 8 — Cancel, unchanged submit, and empty submit are no-ops
// ---------------------------------------------------------------------------

test('Scenario 8a: Escape closes edit without regenerating', async ({ page }) => {
  await mockNextChat(page, 'one animal response');
  await openApp(page);
  await sendMessage(page, 'Give me one animal');
  await waitForStreamDone(page);

  // Track whether a second /api/v1/chat request fires
  let regenerationFired = false;
  await page.route('**/api/v1/chat', () => { regenerationFired = true; });

  await clickEditOnLastUserMessage(page);
  await page.keyboard.press('Escape');

  // Textarea closed, no request made
  await expect(page.locator('.message-bubble-user textarea')).toHaveCount(0);
  expect(regenerationFired).toBe(false);
});

test('Scenario 8b: submitting unchanged content is a no-op', async ({ page }) => {
  await mockNextChat(page, 'one animal response');
  await openApp(page);
  await sendMessage(page, 'Give me one animal');
  await waitForStreamDone(page);

  let regenerationFired = false;
  await page.route('**/api/v1/chat', () => { regenerationFired = true; });

  await clickEditOnLastUserMessage(page);
  // Press Enter without changing the text
  await page.keyboard.press('Enter');

  await expect(page.locator('.message-bubble-user textarea')).toHaveCount(0);
  expect(regenerationFired).toBe(false);
});

test('Scenario 8c: submitting empty content is a no-op', async ({ page }) => {
  await mockNextChat(page, 'one animal response');
  await openApp(page);
  await sendMessage(page, 'Give me one animal');
  await waitForStreamDone(page);

  let regenerationFired = false;
  await page.route('**/api/v1/chat', () => { regenerationFired = true; });

  await clickEditOnLastUserMessage(page);
  const textarea = page.locator('.message-bubble-user textarea').last();
  await textarea.selectText();
  await textarea.press('Delete');
  await textarea.press('Enter');

  await expect(page.locator('.message-bubble-user textarea')).toHaveCount(0);
  expect(regenerationFired).toBe(false);
});

// ---------------------------------------------------------------------------
// Scenario 9 — Edit button visibility and placement
// ---------------------------------------------------------------------------

test('Scenario 9: edit button hidden by default, visible on hover, not on assistant', async ({ page }) => {
  await mockNextChat(page, 'assistant reply');
  await openApp(page);
  await sendMessage(page, 'Hello');
  await waitForStreamDone(page);

  const editBtn = page.getByRole('button', { name: /edit message/i });

  // Button not visible without hover
  await expect(editBtn).toHaveCSS('opacity', '0');

  // Hover user bubble — button appears
  await page.locator('.message-bubble-user').hover();
  await expect(editBtn).toBeVisible();

  // Move off — button fades
  await page.mouse.move(0, 0);
  await expect(editBtn).toHaveCSS('opacity', '0');

  // No edit button on assistant message
  await page.locator('.message-bubble-assistant, .message-bubble').first().hover();
  await expect(editBtn).toHaveCount(0);
});
