# Inline Edit Bug Reproduction Playbook

Use this playbook to reproduce the two bugs fixed in `fix/216-editable-prompt` before merging.
Work through each scenario on the **unfixed branch** first (e.g. the commit just before
`fix: reposition user message edit button` / `Address PR feedback for inline edit feature`) to
confirm you can reproduce the failure, then re-run on the fixed branch to confirm they are resolved.

## Setup

1. Start the app:

   ```bash
   npm run dev
   ```

2. Open the local Vite URL shown in the terminal.
3. Open browser DevTools **before** testing. Keep the **Console** tab visible throughout.
4. Use any adapter/model that produces a visible streaming text response.

Before each scenario, start from a clean conversation unless stated otherwise.

## Baseline Checks

Run these once before manual testing:

```bash
npm run lint
npm run build
```

Pass criteria:

- Both commands exit with code 0.
- The browser console has no new uncaught errors during the scenarios below.

---

## Bug 1: Edit Button Renders Outside the Bubble (Far-Right Misplacement)

**Branch introduced:** `feat: inline editable user messages` (`c6f69a35`)  
**Fixed by:** `fix: reposition user message edit button` (`98521632`)

### What the bug is

When the inline edit feature was first implemented, the pencil (pencil) button was placed in a
separate full-width row **outside** the user bubble. On wider viewports this caused the icon
to render far to the right of the bubble — sometimes at the edge of the viewport — instead
of sitting neatly inside the bubble corner.

### Steps to reproduce (on the unfixed branch)

1. Checkout the unfixed commit:

   ```bash
   git checkout c6f69a35
   npm install
   npm run dev
   ```

2. Create a new conversation and send any short message, e.g.:

   ```text
   Hello
   ```

3. Wait for the assistant response to finish streaming.
4. Move your mouse over the **user** message bubble ("Hello").
5. Observe the position of the pencil icon that appears.

### Actual result (bug present)

- The pencil icon appears **outside** the bubble — rendering to the far right, separated from
  the message text, or near the right edge of the screen.
- On a narrow viewport the icon may be clipped.

### Expected result (after fix)

- The pencil icon appears **inside** the user bubble, overlaid in the top-right corner of the
  bubble, aligned vertically with a single-line or multi-line message.
- Text inside the bubble wraps before reaching the icon (`pr-10` padding reserves the space).
- The icon is invisible when the mouse is not hovering the bubble, and becomes visible only
  on hover.

### Fail indicators (confirms bug is present on unfixed branch)

- Pencil icon is not visually contained within the bubble borders.
- Pencil icon appears horizontally beyond the bubble boundary.
- Icon overlaps content or appears on the wrong side.

---

## Bug 2: Cursor Jumps to End of Text on Every Keystroke During Edit

**Branch introduced:** `feat: inline editable user messages` (`c6f69a35`)  
**Fixed by:** `fix: reposition user message edit button` (`98521632`)

### What the bug is

The original implementation combined two `useEffect` hooks into one: focus-and-cursor-placement
_and_ textarea auto-resize both ran together on the same dependency. Because auto-resize
recalculates `scrollHeight` on every content change, the focus/cursor-placement logic also
re-ran on every keystroke, resetting the cursor position to the **end of the text** each time.

### Steps to reproduce (on the unfixed branch)

1. Checkout the unfixed commit (if not already done):

   ```bash
   git checkout c6f69a35
   npm run dev
   ```

2. Create a new conversation and send:

   ```text
   The quick brown fox jumps over the lazy dog
   ```

3. Wait for the assistant response to finish.
4. Hover the user message bubble and click the pencil icon to open the edit textarea.
5. Click somewhere in the **middle** of the text (e.g., between "quick" and "brown").
6. Type a few characters (e.g., `XXX`).

### Actual result (bug present)

- After each character you type, the cursor **jumps to the end** of the textarea.
- Typing feels broken — you cannot insert text at an arbitrary position.

### Expected result (after fix)

- The cursor stays at the position where you clicked and typed.
- Text is inserted at the current caret position without any jumping.
- The textarea still auto-resizes as content grows.

### Fail indicators (confirms bug is present on unfixed branch)

- Any typed character causes the caret to jump away from its position.
- Typing in the middle of existing text is impossible because the cursor resets.

---

## Confirming the Fixes

After validating both bugs above on the unfixed branch, switch to the fixed tip:

```bash
git checkout fix/216-editable-prompt   # or the merge target branch
npm run dev
```

Re-run **both** scenarios. Confirm:

- [ ] Pencil icon renders inside the bubble, centered vertically.
- [ ] Cursor stays at the typed position during edit.
- [ ] `npm run lint` and `npm run build` both pass.
- [ ] No new console errors during either scenario.

> **Tip:** Also run the full [edit-regenerate-regression-playbook.md](./edit-regenerate-regression-playbook.md)
> to ensure the broader edit/regenerate streaming behavior is still correct after these UI fixes.

## Console Spot Check

During every scenario, watch for errors related to:

- `setSelectionRange`
- `focus`
- `ResizeObserver loop`
- `Maximum update depth exceeded`

Pass criteria:

- No uncaught exceptions.
- No repeated render/update warnings.
- No failed state updates.

---

## Bug 3: PR Feedback Items (Duplicate UI & Code Debt)

**Fixed by:** `Address PR feedback for inline edit feature` (`8cbb3944`)

During the PR review, 5 specific feedback items were identified and fixed. While some are code-quality improvements, you should verify the user-facing ones:

### The 5 Feedback Items Addressed

1. **Duplicate Edit Button**: When the new absolute-positioned edit button was added to the top right of the message bubble, the original floating button wasn't removed. This caused two pencil icons to appear on hover. (Fixed by removing the old floating `div` in `Message.tsx`).
2. **Duplicated Streaming Logic**: The text-streaming loop was duplicated across both `regenerateResponse` and `editUserMessage`. (Fixed by extracting it into a DRY `_runStreamIntoMessage` helper in `chatStore.ts`).
3. **Unused `onEditMessage` Prop**: The `MessageList.tsx` component was receiving and passing down an `onEditMessage` prop that was no longer necessary after refactoring. (Fixed by removing it from the interface and props).
4. **Stale Abort Controllers**: Ensured that the stream abort controllers and request IDs are properly reset to `null` regardless of how the stream exits in the new helper.
5. **Debounced Local Storage Consistency**: Unified the call to `debouncedSaveToLocalStorage(get)` to ensure the conversation branch is reliably saved when the newly extracted stream helper finishes.

### Steps to Verify the Duplicate Button Bug (on unfixed branch)

1. Checkout the unfixed commit (e.g. `98521632` which repositioned the button but didn't remove the old one).
2. Create a conversation and send a message.
3. Hover over the user message.
4. **Expected Result (Bug present)**: You will see **two** pencil edit buttons. One inside the bubble, and one floating outside to the right.
5. **Expected Result (Fixed)**: Only one pencil edit button appears inside the top right corner of the user bubble.
