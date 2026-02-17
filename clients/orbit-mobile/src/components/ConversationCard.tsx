import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
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
  const topLevelUserMessages = conversation.messages.filter(
    (msg) => msg.role === 'user' && !msg.isThreadMessage
  );
  const lastTopLevelUserMessage = topLevelUserMessages[topLevelUserMessages.length - 1];
  const title = conversation.adapterInfo?.adapter_name || conversation.title;
  const preview = lastTopLevelUserMessage
    ? lastTopLevelUserMessage.content.slice(0, 140) + (lastTopLevelUserMessage.content.length > 140 ? '...' : '')
    : 'No messages yet';

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.container,
        {
          backgroundColor: pressed ? theme.surface : theme.card,
          borderColor: theme.border,
        },
      ]}
    >
      <View style={styles.content}>
        <View style={styles.mainRow}>
          <View style={styles.leftColumn}>
            <Text
              style={[styles.title, { color: theme.text }]}
              numberOfLines={1}
            >
              {title}
            </Text>
            <Text
              style={[styles.preview, { color: theme.textSecondary }]}
              numberOfLines={2}
            >
              {preview}
            </Text>
          </View>
          <View style={styles.rightColumn}>
            <Text style={[styles.timestamp, { color: theme.textTertiary }]} numberOfLines={1}>
              {formatTimestamp(conversation.updatedAt)}
            </Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    marginVertical: 6,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
  },
  content: {
    flex: 1,
  },
  mainRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  leftColumn: {
    flex: 1,
    marginRight: 12,
    minWidth: 0,
  },
  rightColumn: {
    width: 112,
    alignItems: 'flex-end',
    justifyContent: 'flex-start',
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
  },
  timestamp: {
    fontSize: 12,
  },
  preview: {
    fontSize: 14,
    lineHeight: 18,
    marginTop: 8,
  },
});
