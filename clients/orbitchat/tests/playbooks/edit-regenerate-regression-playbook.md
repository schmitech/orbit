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

## Scenario 9: Cursor Position While Editing

Purpose: Verify the caret stays where the user clicked/typed instead of jumping to the
end of the text on every keystroke.

> **Regression note:** an earlier bug combined the focus/cursor-placement effect with the
> textarea auto-resize effect on the same dependency array, so every content change
> (auto-resize recalculation) also re-ran the cursor-reset logic. Keep these two `useEffect`
> hooks on separate dependency arrays (cursor placement depending only on `isEditing`,
> auto-resize depending on `[isEditing, editContent]`).

Steps:

1. Create a new conversation and send:

   ```text
   The quick brown fox jumps over the lazy dog
   ```

2. Wait for the assistant response to finish.
3. Click the edit (pencil) button on the user message.
4. Click in the **middle** of the text (e.g., between "quick" and "brown").
5. Type a few characters (e.g., `XXX`).

Pass criteria:

- The caret stays at the position where you clicked and typed; text is inserted there.
- The textarea still auto-resizes as content grows.

Fail indicators:

- The caret jumps to the end of the textarea after any typed character.
- Typing in the middle of existing text is effectively impossible because the cursor keeps resetting.

## Scenario 10: Regenerate a Non-Final (Earlier) Turn

Purpose: Confirm that regenerating an assistant response that is **not** the last turn
in the conversation keeps its original position in the conversation, instead of jumping
to the end after later turns.

> **Regression note (server):** the server-side fix for the regenerate/edit
> duplicate-turn bug (chat_history_service.py) originally stamped a fresh `timestamp`
> on the replaced user/assistant rows. Since conversation history is ordered by
> timestamp, regenerating an earlier turn moved it to the end of the session, silently
> reordering the whole conversation on the next reload. The fix stopped touching the
> timestamp on replace.
>
> **Regression note (client):** `appendToLastMessage` and `updateLastAssistantMessage`
> (chatStore.ts) originally targeted whichever message was *last* in the conversation's
> in-memory array, not the specific message actually streaming. That's only correct when
> the streaming message genuinely is the last one — regenerating a non-final turn leaves
> a different, already-completed message last, so streamed text was silently dropped
> (the regenerated bubble stayed empty) and/or misattributed to the wrong message. The
> fix threads the target `assistantMessageId` through both helpers and the streaming
> buffer instead of relying on array position. There is no unit-test harness for
> chatStore.ts (`npm test` only covers plain `.js` proxy/CLI tests, not the Zustand
> store), so this scenario is the only regression coverage for that fix — don't skip it.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Give me one color.
   ```

3. Wait for completion.
4. Send a second message:

   ```text
   Give me one animal.
   ```

5. Wait for completion. The conversation now has two exchanges.
6. Use the regenerate response action on the **first** assistant message (the color
   answer), not the most recent one.
7. **While it is streaming**, watch both assistant bubbles — don't wait for completion
   before checking.
8. Wait for completion.
9. Reload the page.

Pass criteria:

- While streaming, the regenerated (first) bubble fills in with new content, and the
  second exchange's answer ("Dog." or similar) remains visible and unchanged throughout.
- Before and after reload, the order is: color question, regenerated color answer,
  animal question, animal answer — the regenerated turn stays **first**.
- The animal exchange is untouched and does not move, and its content is not blanked,
  duplicated, or overwritten at any point.
- No duplicate turns appear.

Fail indicators:

- The first (regenerating) bubble stays empty/blank once streaming finishes.
- The second exchange's assistant message disappears, goes blank, or gets overwritten
  with the first turn's regenerated content while the first turn is streaming.
- A reload restores both messages correctly (content is fine in the database) but the
  live UI was wrong during/after the regenerate action — this indicates the bug is in
  chatStore.ts's client-side message targeting, not server-side persistence.
- After reload, the regenerated color turn appears **after** the animal exchange
  instead of before it.
- A duplicate color question/answer pair appears anywhere in the conversation.

## Scenario 11: Edit a Non-Final (Earlier) Turn

Purpose: Confirm that editing a user message that is **not** the last turn keeps every
later exchange intact — distinct from Scenario 10, which only exercises regenerate.

> **Regression note:** `editMessageAndRegenerate`'s array splice replaced the edited user
> message and its old assistant reply (`messageIndex` and `messageIndex + 1`) but never
> re-appended anything after that point — unlike `regenerateResponse`, which correctly
> preserves `...conv.messages.slice(messageIndex + 1)`. Editing any turn that wasn't the
> last one silently truncated the entire rest of the conversation from local state the
> instant the edit was submitted (before any streaming even started). A reload masked
> it, because `syncConversationsWithBackend` reloads from the server, which was never
> affected — server-side persistence for this turn was already correct. The fix appends
> `...conv.messages.slice(tailStartIndex)` after the replacement.

Steps:

1. Create a new conversation.
2. Send:

   ```text
   Give me one color.
   ```

3. Wait for completion.
4. Send a second message:

   ```text
   Give me one animal.
   ```

5. Wait for completion. The conversation now has two exchanges.
6. Click the edit (pencil) button on the **first** user message (the color question)
   and change it to:

   ```text
   Give me one supercolor.
   ```

7. Submit the edit. **Immediately** (don't wait for streaming to finish) check whether
   the second exchange (animal question + answer) is still visible.
8. Wait for completion.
9. Reload the page.

Pass criteria:

- The second exchange (animal question + answer) remains visible the entire time —
  immediately after submitting the edit, while the first turn streams, and after
  completion.
- After reload, both exchanges are present and in order: edited color question,
  regenerated color answer, animal question, animal answer.
- No duplicate turns appear.

Fail indicators:

- The second exchange disappears from the UI as soon as the edit is submitted (before
  or during streaming), even though a reload correctly restores it — this confirms the
  bug is the client-side array-splice truncation in `editMessageAndRegenerate`, not a
  server-side persistence issue.
- After reload, the animal exchange is missing, duplicated, or reordered.

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
- `setSelectionRange`

Pass criteria:

- No uncaught exceptions.
- No repeated render/update warnings.
- No failed state updates after a stream is cancelled.

## Final Signoff

Mark the update as passing only if:

- `npm run lint` passes.
- `npm run build` passes.
- Scenarios 1 through 11 pass.
- Reload behavior is correct after edit/regenerate.
- No cancelled-stream text appears in a regenerated assistant message.
