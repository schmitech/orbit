import React, { useCallback, useEffect } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useChatStore } from '../../src/stores/chatStore';
import { useTheme } from '../../src/hooks/useTheme';
import { ConversationCard } from '../../src/components/ConversationCard';
import { EmptyState } from '../../src/components/EmptyState';
import { SwipeableRow } from '../../src/components/SwipeableRow';
import { Conversation } from '../../src/types';

export default function ConversationsScreen() {
  const conversations = useChatStore((s) => s.conversations);
  const createConversation = useChatStore((s) => s.createConversation);
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const setCurrentConversation = useChatStore((s) => s.setCurrentConversation);
  const fetchAdapterInfo = useChatStore((s) => s.fetchAdapterInfo);
  const setConversationAdapterInfo = useChatStore((s) => s.setConversationAdapterInfo);
  const { theme } = useTheme();

  const sortedConversations = [...conversations].sort(
    (a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()
  );

  const handleNewChat = useCallback(() => {
    const id = createConversation();
    router.push(`/chat/${id}`);
  }, [createConversation]);

  const handleOpenChat = useCallback(
    (id: string) => {
      setCurrentConversation(id);
      router.push(`/chat/${id}`);
    },
    [setCurrentConversation]
  );

  const renderItem = useCallback(
    ({ item }: { item: Conversation }) => (
      <SwipeableRow onDelete={() => deleteConversation(item.id)}>
        <ConversationCard
          conversation={item}
          onPress={() => handleOpenChat(item.id)}
          theme={theme}
        />
      </SwipeableRow>
    ),
    [theme, deleteConversation, handleOpenChat]
  );

  useEffect(() => {
    let cancelled = false;

    const hydrateMissingAdapterInfo = async () => {
      const missingAdapterInfo = conversations.filter((c) => !c.adapterInfo);
      if (missingAdapterInfo.length === 0) return;

      const info = await fetchAdapterInfo();
      if (!info || cancelled) return;

      for (const conversation of missingAdapterInfo) {
        setConversationAdapterInfo(conversation.id, info);
      }
    };

    hydrateMissingAdapterInfo();

    return () => {
      cancelled = true;
    };
  }, [conversations, fetchAdapterInfo, setConversationAdapterInfo]);

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      {sortedConversations.length === 0 ? (
        <EmptyState theme={theme} variant="conversations" onPress={handleNewChat} />
      ) : (
        <>
          <FlashList
            data={sortedConversations}
            renderItem={renderItem}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.listContent}
          />
          <Pressable
            onPress={handleNewChat}
            style={[styles.fab, { backgroundColor: theme.primary }]}
          >
            <Ionicons name="add" size={28} color="#FFFFFF" />
          </Pressable>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  listContent: {
    paddingVertical: 6,
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 8,
  },
});
