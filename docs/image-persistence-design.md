# Image Persistence After Page Refresh

## Problem

Generated images in chat messages (main and thread replies) are intentionally excluded from localStorage to avoid the browser 5 MB quota:

```ts
// clients/orbitchat/src/stores/chatStore.ts
const hasLargeData = msg.audio || msg.image;
if (!hasLargeData) return msg;
return Object.fromEntries(
  Object.entries(msg).filter(([k]) => k !== 'audio' && k !== 'image')
) as typeof msg;
```

As a result, after a page refresh the message is present but its image is gone. This affects both main conversation messages and thread replies.

---

## Option A — Backend Storage (recommended)

Store generated images server-side and return a URL instead of raw base64. The URL is small, survives localStorage, and works across devices and sessions.

### Changes required

**Server (`server/`)**

1. When an image is generated (e.g. via DALL-E or a local diffusion model), save the bytes to object storage (S3, MinIO, local disk) and return a signed/stable URL in the response instead of base64.
2. Add a route (or reuse an existing file-serving route) to serve stored images: `GET /api/images/{image_id}`.
3. Set a TTL or manual cleanup policy for stored images.

**Frontend (`clients/orbitchat/src/`)**

1. In `apiClient.ts`, update the `StreamResponse` type: replace `image?: string` (base64) with `image_url?: string`.
2. In `ImageDisplay.tsx`, accept an `imageUrl` prop in addition to/instead of `image` (base64). Render `<img src={imageUrl} />` directly.
3. In `chatStore.ts`, remove the `msg.image` exclusion from `debouncedSaveToLocalStorage` once images are URLs (they're tiny).
4. In `Message.tsx`, pass `imageUrl` to `ImageDisplay` when available.

### Pros
- Works across devices and sessions
- No client-side storage complexity
- Thread reply images survive refresh

### Cons
- Requires backend changes and storage infrastructure
- Need a cleanup strategy for old images

---

## Option B — IndexedDB (client-only)

Store image blobs in IndexedDB (no quota issues) keyed by message ID. localStorage continues to hold everything except raw image data.

### Changes required

**Frontend only (`clients/orbitchat/src/`)**

1. Create `src/services/imageStore.ts` — a small IndexedDB wrapper:
   ```ts
   // save(messageId: string, base64: string): Promise<void>
   // load(messageId: string): Promise<string | null>
   // remove(messageId: string): Promise<void>
   // clear(): Promise<void>
   ```
   Use the `idb` package (already common in React projects) or raw `indexedDB` API.

2. In `debouncedSaveToLocalStorage`, keep stripping `msg.image` from localStorage but also call `imageStore.save(msg.id, msg.image)` for any message that has an image.

3. In `initializeStore` (the localStorage restore path), after messages are loaded, call `imageStore.load(msg.id)` for messages that are missing an image and rehydrate them.

4. In `deleteConversation` / `deleteAllConversations`, also call `imageStore.remove()` / `imageStore.clear()` to avoid orphan blobs.

### Pros
- No backend changes
- Works offline
- Images persist across refreshes on the same device

### Cons
- More complex client code
- Only works on the device where the image was generated
- IndexedDB can still be cleared by the browser (private mode, storage pressure)

---

## Recommended path

**Short term:** Option B is self-contained and can be implemented without touching the server. It fixes the refresh problem immediately.

**Long term:** Option A is cleaner — images become proper resources with stable URLs, enabling sharing, multi-device access, and no client-side storage management.

Both options can coexist during a migration: store images in IndexedDB now, and once the backend URL approach lands, prefer the URL and let the IndexedDB entries expire.
