import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  StyleSheet,
  Text,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Alert,
  Keyboard,
  ScrollView,
} from 'react-native';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useChatStore } from '../../../../src/stores/chatStore';
import { useTheme } from '../../../../src/hooks/useTheme';
import { ChatBubble } from '../../../../src/components/ChatBubble';
import { ChatInput } from '../../../../src/components/ChatInput';
import { MarkdownContent } from '../../../../src/components/MarkdownContent';
import { Message } from '../../../../src/types';
import { getConfig } from '../../../../src/config/env';

export default function ThreadScreen() {
  const { id, parentId, threadId: initialThreadId } = useLocalSearchParams<{
    id: string;
    parentId: string;
    threadId?: string;
  }>();
  const router = useRouter();
  const conversations = useChatStore((s) => s.conversations);
  const setCurrentConversation = useChatStore((s) => s.setCurrentConversation);
  const createThread = useChatStore((s) => s.createThread);
  const sendThreadMessage = useChatStore((s) => s.sendThreadMessage);
  const stopGeneration = useChatStore((s) => s.stopGeneration);
  const toggleAudioForConversation = useChatStore((s) => s.toggleAudioForConversation);
  const isLoading = useChatStore((s) => s.isLoading);
  const { theme, isDark } = useTheme();

  const [threadId, setThreadId] = useState<string | null>(
    typeof initialThreadId === 'string' && initialThreadId.length > 0 ? initialThreadId : null
  );
  const [isCreatingThread, setIsCreatingThread] = useState(false);
  const [isParentExpanded, setIsParentExpanded] = useState(false);
  const listRef = useRef<FlashListRef<Message>>(null);
  const audioOutputSupported = useMemo(() => getConfig().enableAudioOutput, []);

  const conversation = conversations.find((c) => c.id === id);
  const parentMessage = useMemo(() => {
    if (!conversation) return null;
    return conversation.messages.find((m) => m.id === parentId) ?? null;
  }, [conversation, parentId]);

  useEffect(() => {
    if (id) {
      setCurrentConversation(id);
    }
    return () => {
      setCurrentConversation(null);
    };
  }, [id, setCurrentConversation]);

  useEffect(() => {
    if (parentMessage?.threadInfo?.thread_id) {
      setThreadId(parentMessage.threadInfo.thread_id);
    }
  }, [parentMessage?.threadInfo?.thread_id]);

  useEffect(() => {
    if (!conversation || !parentMessage || threadId || isCreatingThread) return;

    let cancelled = false;
    setIsCreatingThread(true);
    createThread(parentMessage.id, conversation.sessionId)
      .then((info) => {
        if (!cancelled) {
          setThreadId(info.thread_id);
        }
      })
      .catch((error: any) => {
        if (!cancelled) {
          Alert.alert('Unable to create thread', error?.message || 'Please try again.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsCreatingThread(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [conversation, parentMessage, threadId, isCreatingThread, createThread]);

  const replies = useMemo(() => {
    if (!conversation || !parentMessage || !threadId) return [];
    return conversation.messages.filter((msg) => {
      if (!msg.isThreadMessage) return false;
      if (msg.parentMessageId === parentMessage.id) return true;
      return msg.threadId === threadId;
    });
  }, [conversation, parentMessage, threadId]);
  const threadReady = !!threadId && !isCreatingThread;
  const collapsedPreviewBackground = isDark ? '#F1F3F5' : '#1F2937';
  const collapsedPreviewText = isDark ? '#111827' : '#F9FAFB';
  const parentCardBackground = !isParentExpanded ? collapsedPreviewBackground : theme.surface;
  const parentCardBorder = !isParentExpanded ? collapsedPreviewBackground : theme.border;
  const parentHeaderColor = !isParentExpanded ? collapsedPreviewText : theme.textSecondary;

  useEffect(() => {
    if (!replies.length) return;
    requestAnimationFrame(() => {
      listRef.current?.scrollToEnd({ animated: true });
    });
  }, [replies.length, replies[replies.length - 1]?.content]);

  useEffect(() => {
    if (!threadReady || isLoading) return;
    const timer = setTimeout(() => {
      requestAnimationFrame(() => {
        listRef.current?.scrollToEnd({ animated: true });
      });
    }, 120);
    return () => clearTimeout(timer);
  }, [threadReady, isLoading]);

  useEffect(() => {
    const sub = Keyboard.addListener('keyboardDidShow', () => {
      requestAnimationFrame(() => {
        listRef.current?.scrollToEnd({ animated: true });
      });
    });
    return () => sub.remove();
  }, []);

  const handleSend = useCallback(async (content: string) => {
    if (!parentMessage || !conversation) return;
    const trimmed = content.trim();
    if (!trimmed || isLoading) return;

    let activeThreadId = threadId;
    if (!activeThreadId) {
      if (isCreatingThread) {
        Alert.alert('Preparing thread', 'Please wait a moment and try again.');
        return;
      }
      try {
        setIsCreatingThread(true);
        const info = await createThread(parentMessage.id, conversation.sessionId);
        activeThreadId = info.thread_id;
        setThreadId(info.thread_id);
      } catch (error: any) {
        Alert.alert('Unable to create thread', error?.message || 'Please try again.');
        return;
      } finally {
        setIsCreatingThread(false);
      }
    }

    try {
      await sendThreadMessage(activeThreadId, parentMessage.id, trimmed);
    } catch (error: any) {
      Alert.alert('Reply failed', error?.message || 'Please try again.');
    }
  }, [threadId, parentMessage, conversation, isLoading, isCreatingThread, createThread, sendThreadMessage]);

  const handleStop = useCallback(() => {
    stopGeneration();
  }, [stopGeneration]);

  const handleToggleAudio = useCallback(() => {
    if (typeof id === 'string') {
      toggleAudioForConversation(id);
    }
  }, [id, toggleAudioForConversation]);

  const renderReply = useCallback(
    ({ item }: { item: Message }) => (
      <ChatBubble message={item} theme={theme} showThreadActions={false} />
    ),
    [theme]
  );

  if (!conversation || !parentMessage) {
    return (
      <View style={[styles.centered, { backgroundColor: theme.background }]}>
        <Text style={[styles.emptyText, { color: theme.textSecondary }]}>Thread not found.</Text>
      </View>
    );
  }

  return (
    <>
      <Stack.Screen
        options={{
          title: 'Replies',
          headerRight: () => (
            <Pressable onPress={() => router.back()} hitSlop={8} style={styles.mainChatButton}>
              <Text style={[styles.mainChatButtonText, { color: theme.primary }]}>Main chat</Text>
            </Pressable>
          ),
        }}
      />
      <KeyboardAvoidingView
        style={[styles.container, { backgroundColor: theme.background }]}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        <View style={[styles.parentCard, { borderColor: parentCardBorder, backgroundColor: parentCardBackground }]}>
          <View style={styles.parentHeaderRow}>
            <Text style={[styles.parentLabel, { color: parentHeaderColor }]}>Replying to</Text>
            <View style={styles.parentHeaderRight}>
              <Pressable
                onPress={() => setIsParentExpanded((prev) => !prev)}
                hitSlop={8}
                style={styles.parentToggleButton}
              >
                <Ionicons
                  name={isParentExpanded ? 'chevron-up' : 'chevron-down'}
                  size={16}
                  color={parentHeaderColor}
                />
              </Pressable>
            </View>
          </View>
          {!isParentExpanded ? (
            <View style={styles.parentCollapsedPreview} pointerEvents="none">
              <View style={styles.parentCollapsedPreviewContent}>
                <MarkdownContent
                  content={parentMessage.content}
                  theme={theme}
                  variant="preview"
                  textColor={collapsedPreviewText}
                />
              </View>
            </View>
          ) : null}
          {isParentExpanded ? (
            <View style={styles.parentCardContent}>
              <ScrollView
                style={styles.parentCardScroll}
                contentContainerStyle={styles.parentCardScrollContent}
                nestedScrollEnabled
                keyboardShouldPersistTaps="handled"
              >
                <ChatBubble message={parentMessage} theme={theme} showThreadActions={false} />
              </ScrollView>
            </View>
          ) : null}
        </View>

        <FlashList
          ref={listRef}
          style={styles.repliesListContainer}
          data={replies}
          renderItem={renderReply}
          keyExtractor={(item) => item.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.repliesList}
        />

        <ChatInput
          onSend={handleSend}
          onStop={handleStop}
          isLoading={isLoading}
          theme={theme}
          autoFocus
          placeholder="Ask a follow-up question."
          audioEnabled={conversation.audioSettings?.enabled ?? false}
          audioOutputSupported={audioOutputSupported}
          onToggleAudio={handleToggleAudio}
        />
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  parentCard: {
    marginHorizontal: 10,
    marginTop: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 14,
    overflow: 'hidden',
  },
  parentCardContent: {
    maxHeight: 260,
  },
  parentCollapsedPreview: {
    height: 30,
    marginHorizontal: 12,
    marginBottom: 8,
    paddingHorizontal: 0,
    paddingVertical: 0,
    overflow: 'hidden',
  },
  parentCollapsedPreviewContent: {
    flex: 1,
    justifyContent: 'center',
  },
  parentCardScroll: {
    maxHeight: 260,
  },
  parentCardScrollContent: {
    paddingBottom: 4,
  },
  parentHeaderRow: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 12,
  },
  parentHeaderRight: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 6,
  },
  parentToggleButton: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  parentLabel: {
    fontSize: 12,
    fontWeight: '600',
  },
  repliesListContainer: {
    flex: 1,
  },
  repliesList: {
    paddingVertical: 12,
    paddingBottom: 18,
  },
  emptyText: {
    textAlign: 'center',
    marginTop: 24,
    fontSize: 14,
    paddingHorizontal: 24,
  },
  mainChatButton: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  mainChatButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
});
