import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Conversation } from '../types';
import { ThemeColors } from '../theme/colors';

interface Props {
  conversation: Conversation;
  onPress: () => void;
  theme: ThemeColors;
}

function formatTimestamp(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function ConversationCard({ conversation, onPress, theme }: Props) {
  const lastMessage = conversation.messages[conversation.messages.length - 1];
  const preview = lastMessage
    ? lastMessage.content.slice(0, 80) + (lastMessage.content.length > 80 ? '...' : '')
    : 'No messages yet';

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.container,
        { backgroundColor: pressed ? theme.surface : theme.card },
      ]}
    >
      <View style={styles.iconContainer}>
        <Ionicons name="chatbubble-outline" size={20} color={theme.primary} />
      </View>
      <View style={styles.content}>
        <View style={styles.header}>
          <Text
            style={[styles.title, { color: theme.text }]}
            numberOfLines={1}
          >
            {conversation.title}
          </Text>
          <Text style={[styles.timestamp, { color: theme.textTertiary }]}>
            {formatTimestamp(conversation.updatedAt)}
          </Text>
        </View>
        <Text
          style={[styles.preview, { color: theme.textSecondary }]}
          numberOfLines={2}
        >
          {preview}
        </Text>
        {conversation.adapterInfo && (
          <Text style={[styles.model, { color: theme.textTertiary }]}>
            {conversation.adapterInfo.model || conversation.adapterInfo.adapter_name}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 14,
    alignItems: 'flex-start',
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
    marginTop: 2,
  },
  content: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
    marginRight: 8,
  },
  timestamp: {
    fontSize: 13,
  },
  preview: {
    fontSize: 14,
    lineHeight: 20,
  },
  model: {
    fontSize: 12,
    marginTop: 4,
  },
});
