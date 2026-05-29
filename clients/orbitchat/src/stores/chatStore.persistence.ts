import { Conversation } from '../types';
import { debugWarn, logError } from '../utils/debug';

const LOCALSTORAGE_SAVE_DELAY = 300; // ms
let localStorageSaveTimeout: ReturnType<typeof setTimeout> | null = null;

export const debouncedSaveToLocalStorage = (
  getState: () => { conversations: Conversation[]; currentConversationId: string | null }
) => {
  if (localStorageSaveTimeout) {
    clearTimeout(localStorageSaveTimeout);
  }
  localStorageSaveTimeout = setTimeout(() => {
    localStorageSaveTimeout = null;
    try {
      const currentState = getState();
      // Exclude large binary data (audio, image, video, document) from persistence to reduce localStorage size
      const conversationsForStorage = currentState.conversations.map(conv => ({
        ...conv,
        messages: conv.messages.map(msg => {
          const hasLargeData = msg.audio || msg.image || msg.video || msg.document;
          if (!hasLargeData) return msg;
          return Object.fromEntries(
            Object.entries(msg).filter(([k]) => k !== 'audio' && k !== 'image' && k !== 'video' && k !== 'document')
          ) as typeof msg;
        }),
      }));
      localStorage.setItem(
        'chat-state',
        JSON.stringify({
          conversations: conversationsForStorage,
          currentConversationId: currentState.currentConversationId,
        })
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        debugWarn('[chatStore] localStorage quota exceeded — skipping save');
      } else {
        logError('[chatStore] Failed to save state to localStorage:', error);
      }
    }
  }, LOCALSTORAGE_SAVE_DELAY);
};
