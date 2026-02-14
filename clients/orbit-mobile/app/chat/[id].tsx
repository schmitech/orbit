import React, { useCallback, useEffect, useRef, useMemo } from 'react';
import {
  View,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Text,
} from 'react-native';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useChatStore } from '../../src/stores/chatStore';
import { useTheme } from '../../src/hooks/useTheme';
import { ChatBubble } from '../../src/components/ChatBubble';
import { ChatInput } from '../../src/components/ChatInput';
import { EmptyState } from '../../src/components/EmptyState';
import { Message } from '../../src/types';
import { getConfig } from '../../src/config/env';

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const conversations = useChatStore((s) => s.conversations);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stopGeneration = useChatStore((s) => s.stopGeneration);
  const isLoading = useChatStore((s) => s.isLoading);
  const setCurrentConversation = useChatStore((s) => s.setCurrentConversation);
  const toggleAudioForConversation = useChatStore((s) => s.toggleAudioForConversation);
  const fetchAdapterInfo = useChatStore((s) => s.fetchAdapterInfo);
  const setConversationAdapterInfo = useChatStore((s) => s.setConversationAdapterInfo);
  const { theme } = useTheme();

  const audioOutputSupported = useMemo(() => getConfig().enableAudioOutput, []);
  const listRef = useRef<FlashListRef<Message>>(null);

  const conversation = conversations.find((c) => c.id === id);

  useEffect(() => {
    if (id) {
      setCurrentConversation(id);
    }
    return () => {
      setCurrentConversation(null);
    };
  }, [id, setCurrentConversation]);

  useEffect(() => {
    let cancelled = false;

    const hydrateAdapterInfo = async () => {
      if (!conversation || conversation.adapterInfo) return;
      const info = await fetchAdapterInfo();
      if (!cancelled && info) {
        setConversationAdapterInfo(conversation.id, info);
      }
    };

    hydrateAdapterInfo();

    return () => {
      cancelled = true;
    };
  }, [conversation, fetchAdapterInfo, setConversationAdapterInfo]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (conversation?.messages.length) {
      setTimeout(() => {
        listRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [conversation?.messages.length, conversation?.messages[conversation?.messages.length - 1]?.content.length]);

  const handleSend = useCallback(
    (content: string) => {
      sendMessage(content);
    },
    [sendMessage]
  );

  const handleStop = useCallback(() => {
    stopGeneration();
  }, [stopGeneration]);

  const handleToggleAudio = useCallback(() => {
    if (id) {
      toggleAudioForConversation(id);
    }
  }, [id, toggleAudioForConversation]);

  const renderItem = useCallback(
    ({ item }: { item: Message }) => (
      <ChatBubble message={item} theme={theme} />
    ),
    [theme]
  );

  const title = conversation?.adapterInfo?.adapter_name || conversation?.title || 'Chat';
  const modelBadge = conversation?.adapterInfo?.model;

  if (!conversation) {
    return (
      <View style={[styles.container, { backgroundColor: theme.background }]}>
        <Text style={[styles.errorText, { color: theme.textSecondary }]}>
          Conversation not found
        </Text>
      </View>
    );
  }

  return (
    <>
      <Stack.Screen
        options={{
          headerTitle: () => (
            <View style={styles.headerTitleContainer}>
              <Text
                style={[styles.headerMetaText, { color: theme.text }]}
                numberOfLines={1}
              >
                <Text style={styles.headerLabel}>AI Agent: </Text>
                <Text style={styles.headerValue}>{title}</Text>
              </Text>
              {modelBadge ? (
                <Text
                  style={[styles.headerMetaText, styles.modelMetaText, { color: theme.text }]}
                  numberOfLines={1}
                >
                  <Text style={styles.headerLabel}>AI Model: </Text>
                  <Text style={styles.headerValue}>{modelBadge}</Text>
                </Text>
              ) : null}
            </View>
          ),
        }}
      />
      <KeyboardAvoidingView
        style={[styles.container, { backgroundColor: theme.background }]}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        {conversation.messages.length === 0 ? (
          <EmptyState
            theme={theme}
            variant="chat"
            adapterNotes={conversation.adapterInfo?.notes}
          />
        ) : (
          <FlashList
            ref={listRef}
            data={conversation.messages}
            renderItem={renderItem}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.messageList}
          />
        )}
        <ChatInput
          onSend={handleSend}
          onStop={handleStop}
          isLoading={isLoading}
          theme={theme}
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
  messageList: {
    paddingVertical: 12,
  },
  errorText: {
    textAlign: 'center',
    marginTop: 40,
    fontSize: 16,
  },
  headerTitleContainer: {
    flexDirection: 'column',
    alignItems: 'flex-start',
    width: '100%',
    paddingTop: 4,
    paddingRight: 12,
  },
  headerMetaText: {
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
    includeFontPadding: false,
  },
  modelMetaText: {
    marginTop: 4,
  },
  headerLabel: {
    fontWeight: '700',
  },
  headerValue: {
    fontWeight: '400',
  },
});
