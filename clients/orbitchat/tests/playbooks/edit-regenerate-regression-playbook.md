# Edit and Regenerate Regression Playbook

Use this playbook to verify the edit/regenerate streaming fixes and nearby chat behavior before release.

## Setup

1. Start the app:

   ```bash
   npm run dev
   ```

2. Open the local Vite URL shown in the terminal.
3. Use a real adapter/model that streams text visibly. For timing-sensitive scenarios (2, 5), use the **slowest available model** or prepend your prompt with `"Respond very slowly, one word at a time."` to keep the stream running long enough to interact with.
4. Open browser DevTools before testing.
5. Keep the Console and Application > Local Storage panels available.

Before each scenario, start from a clean conversation unless the scenario says otherwise.

## Baseline Checks

Run these once before manual testing:

```bash
npm run lint
npm run build
```

Pass criteria:

- Both commands exit with code 0.
- The browser console has no new uncaught errors during the manual scenarios.

## Scenario 1: Normal Send Still Streams and Persists

Purpose: Confirm the normal send path still works after the stream buffer changes.

Steps:

1. Create a new conversation.
2. Send: `Write a numbered list from 1 to 50, one item per line, slowly if possible.`
3. Wait for streaming to finish.
4. Reload the page.
5. Reopen the same conversation.

Pass criteria:

- The assistant response appears in one assistant bubble.
- The response does not duplicate chunks.
- The final assistant message is no longer in a loading/streaming state.
- After reload, both the user prompt and assistant response are still present.

Fail indicators:

- The response disappears after reload.
- The assistant message remains stuck as streaming.
- Text is duplicated, reordered, or appended to the wrong message.

## Scenario 2: Edit While Active Stream Is Running

Purpose: Verify cancelled-stream buffered chunks do not corrupt the regenerated assistant bubble.

> **Timing tip:** Use the slowest available model or add `"Respond very slowly, one word at a time."` to the prompt so the stream runs long enough to edit mid-flight.

Steps:

1. Create a new conversation.
2. Send a prompt likely to stream for several seconds:

   ```text
   Write a long explanation of how HTTP caching works. Include 20 short sections.
   ```

3. While the assistant is still streaming, edit the user message.
4. Replace the prompt with:

   ```text
   Reply with exactly this sentence and nothing else: EDIT REGENERATION TARGET
   ```

5. Submit the edit/regenerate action immediately.
6. Wait for the regenerated assistant response to finish.

Pass criteria:

- The visible conversation contains the edited user prompt, not the original prompt.
- The regenerated assistant response is in the new assistant bubble.
- The regenerated assistant response does not contain leftover text from the cancelled HTTP caching answer.
- There is no second late assistant bubble created by the cancelled stream.
- The assistant bubble exits streaming state.

Fail indicators:

- Any old HTTP caching text appears in the regenerated response.
- Text from the cancelled stream is appended after `EDIT REGENERATION TARGET`.
- A stale loading indicator remains after the regenerated response completes.

## Scenario 3: Edit/Regenerate Persists Across Reload

Purpose: Verify the edited branch is saved to localStorage after regeneration completes.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Reply with exactly: ORIGINAL PROMPT RESPONSE
   ```

3. Wait for the assistant response to finish.
4. Edit the user message to:

   ```text
   Reply with exactly: EDITED PROMPT RESPONSE
   ```

5. Submit the edit/regenerate action.
6. Wait for the regenerated assistant response to finish.
7. Reload the page.
8. Reopen the same conversation.

Pass criteria:

- The user message still shows `Reply with exactly: EDITED PROMPT RESPONSE`.
- The assistant message still corresponds to `EDITED PROMPT RESPONSE`.
- The old `ORIGINAL PROMPT RESPONSE` branch does not reappear.

Fail indicators:

- Reload restores the original user prompt.
- Reload restores the original assistant response.
- The edited conversation is missing or truncated.

## Scenario 4: Edit After Completed Stream

Purpose: Confirm the edit/regenerate path works when no cancellation is involved.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Give me three colors.
   ```

3. Wait for completion.
4. Edit the user message to:

   ```text
   Give me three fruits.
   ```

5. Press **Enter** (without Shift) to submit — confirm the keyboard shortcut triggers regeneration.
6. Wait for completion.

Pass criteria:

- The user message changes to the fruit prompt.
- The assistant answer is regenerated from the fruit prompt.
- The earlier color response is removed from the active branch.
- Reload keeps the edited prompt and regenerated response.

Fail indicators:

- Enter key does not submit and instead inserts a newline.
- The color response is still present after the edit.

## Scenario 5: Stop Button Still Works

Purpose: Confirm explicit cancellation still leaves the UI in a sane state.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Write a 2000 word essay about distributed systems.
   ```

3. Click the stop/cancel streaming control while text is still streaming.
4. Wait two seconds.
5. Send a new normal message:

   ```text
   Reply with: AFTER STOP
   ```

Pass criteria:

- The first assistant message stops changing after cancellation settles.
- The UI allows a new message to be sent.
- `AFTER STOP` appears in the new assistant response.
- No delayed chunks from the cancelled essay append to the `AFTER STOP` response.

## Scenario 6: Regenerate Existing Assistant Response

Purpose: Confirm the existing non-edit regenerate flow still streams, finalizes, and persists.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Give me a one-paragraph summary of WebSockets.
   ```

3. Wait for completion.
4. Use the regenerate response action on the assistant message.
5. Wait for completion.
6. Reload the page.

Pass criteria:

- The regenerated response replaces the previous assistant response in the expected location.
- The response does not get mixed with stale chunks.
- After reload, the regenerated response remains visible.

## Scenario 7: Repeat Edit of the Same Message

Purpose: Verify that editing the same message twice always shows current content in the textarea, not the original pre-edit content.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Reply with exactly: FIRST SEND
   ```

3. Wait for completion.
4. Edit the user message to:

   ```text
   Reply with exactly: FIRST EDIT
   ```

5. Submit the edit/regenerate action. Wait for the regenerated response to finish.
6. Click the edit button on the **same** user message again.
7. Inspect the textarea content before typing anything.

Pass criteria:

- The textarea shows `Reply with exactly: FIRST EDIT`, not `Reply with exactly: FIRST SEND`.
- Submitting a further change regenerates from the new content correctly.

Fail indicators:

- The textarea shows the original pre-edit content (`FIRST SEND`) instead of the post-edit content.
- Submitting from the stale textarea content re-sends the old prompt.

## Scenario 8: Cancel Edit and Unchanged Edit Are No-ops

Purpose: Verify that cancelling an edit or submitting unchanged content does not trigger a regeneration.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Give me one animal.
   ```

3. Wait for completion. Note the assistant response.
4. Click the edit button on the user message.
5. Press **Escape**. Confirm the edit mode closes without regenerating.
6. Verify the conversation is unchanged (same user prompt, same assistant response).
7. Click the edit button again.
8. Without changing any text, press **Enter** or click **Send**.
9. Confirm no regeneration fires.
10. Click the edit button again.
11. Delete all content, leaving the textarea empty. Click **Send**.
12. Confirm no regeneration fires and the edit is cancelled.

Pass criteria:

- Escape closes the textarea without making any network request.
- Submitting the unchanged prompt does not create a new assistant message or trigger a loading state.
- Submitting an empty prompt does not trigger regeneration.
- The conversation is identical to step 3 throughout.

Fail indicators:

- A new assistant bubble appears after any of these no-op actions.
- A loading spinner appears briefly.
- The user message content changes unexpectedly.

## Scenario 9: Edit Button Visibility and Placement

Purpose: Confirm the edit button appears correctly on hover and is not visible otherwise.

Steps:

1. Create a new conversation with at least two exchanges (two user messages, two assistant responses).
2. Move the mouse away from the message list entirely.
3. Slowly hover over the first user message bubble.
4. Move the mouse away again.
5. Hover over the second user message bubble.
6. Hover over an assistant message bubble.

Pass criteria:

- The edit (pencil) button is invisible when the mouse is not over a user message.
- The edit button appears to the **left** of the user bubble when hovering.
- The button disappears when moving the mouse away.
- No edit button appears on assistant messages at any point.

Fail indicators:

- The edit button is always visible (not hidden when not hovering).
- The edit button appears on the wrong side or overlaps the bubble content.
- The edit button appears on assistant messages.

## Local Storage Spot Check

Use this after Scenarios 2, 3, and 7.

Steps:

1. Open DevTools > Application > Local Storage.
2. Select the app origin.
3. Find the key used by the chat store (search for a key whose value is a JSON object containing `conversations`).
4. In the stored JSON, search for the edited prompt text (e.g. `EDITED PROMPT RESPONSE` or `FIRST EDIT`).

Pass criteria:

- The edited prompt exists in localStorage after regeneration completes.
- The old pre-edit prompt is not present in the active conversation branch.

## Console Spot Check

During every scenario, watch for errors related to:

- `appendToLastMessage`
- `flushStreamingBuffer`
- `stopStreaming`
- `Edit-regenerate`
- `Maximum update depth exceeded`

Pass criteria:

- No uncaught exceptions.
- No repeated render/update warnings.
- No failed state updates after a stream is cancelled.

## Final Signoff

Mark the update as passing only if:

- `npm run lint` passes.
- `npm run build` passes.
- Scenarios 1 through 9 pass.
- Reload behavior is correct after edit/regenerate.
- No cancelled-stream text appears in a regenerated assistant message.
