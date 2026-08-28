import { AdapterInfo } from '../types';

// chatStore.selectConversation and useChatAgentSelection's refreshAdapterInfo
// effect both fetch adapter info for a conversation that lacks it cached yet.
// Selecting a conversation updates React state synchronously but the store's
// fetch only starts after awaiting ensureApiConfigured(), so the hook's effect
// can still see no cached adapterInfo and start its own request before the
// store's request resolves. Sharing the in-flight promise here (keyed by
// conversationId:adapterName) makes the second caller await the same request
// instead of issuing a duplicate authenticated call.
const inFlightRequests = new Map<string, Promise<AdapterInfo>>();

export function fetchAdapterInfoOnce(
  key: string,
  fetcher: () => Promise<AdapterInfo>
): Promise<AdapterInfo> {
  const existing = inFlightRequests.get(key);
  if (existing) {
    return existing;
  }

  const request = fetcher().finally(() => {
    inFlightRequests.delete(key);
  });
  inFlightRequests.set(key, request);
  return request;
}
