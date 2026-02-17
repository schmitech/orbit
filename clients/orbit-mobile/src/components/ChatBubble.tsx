import React, { useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Alert } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { Message } from '../types';
import { ThemeColors } from '../theme/colors';
import { MarkdownContent } from './MarkdownContent';
import { StreamingCursor } from './StreamingCursor';

interface Props {
  message: Message;
  theme: ThemeColors;
  onReplyInThread?: (message: Message) => void;
  showThreadActions?: boolean;
}

export function ChatBubble({
  message,
  theme,
  onReplyInThread,
  showThreadActions = true,
}: Props) {
  const isUser = message.role === 'user';
  const canCopyAssistantMessage = !isUser && !!message.content;

  const handleLongPress = useCallback(() => {
    if (!isUser && message.content) {
      Clipboard.setStringAsync(message.content);
      Alert.alert('Copied', 'Message copied to clipboard');
    }
  }, [isUser, message.content]);

  return (
    <View
      style={[
        styles.container,
        isUser ? styles.userContainer : styles.assistantContainer,
      ]}
    >
      <View
        style={[
          styles.bubbleBase,
          isUser
            ? [styles.bubbleConstrained, styles.userBubble, { backgroundColor: theme.userBubble }]
            : styles.assistantBubble,
        ]}
      >
        {isUser ? (
          <Text style={[styles.userText, { color: theme.userBubbleText }]}>
            {message.content}
          </Text>
        ) : (
          <>
            <Pressable
              onLongPress={handleLongPress}
              delayLongPress={500}
              disabled={!canCopyAssistantMessage}
            >
              <View style={styles.assistantContent}>
              {message.content
                ? (
                  <MarkdownContent content={message.content} theme={theme} />
                )
                : null}
              {message.isStreaming && !message.content && (
                <StreamingCursor color={theme.textTertiary} />
              )}
              {message.isStreaming && message.content ? (
                <View style={styles.streamingCursorWithText}>
                  <StreamingCursor color={theme.primary} />
                </View>
              ) : null}
              </View>
            </Pressable>
            {!message.isStreaming && showThreadActions && message.supportsThreading && onReplyInThread ? (
              <View style={styles.actionsRow}>
                <Pressable
                  onPress={() => onReplyInThread(message)}
                  style={({ pressed }) => [
                    styles.replyButton,
                    {
                      borderColor: theme.primary + '33',
                      backgroundColor: pressed ? theme.primary + '1F' : theme.primary + '14',
                    },
                  ]}
                >
                  <Ionicons
                    name={message.threadInfo ? 'chatbubbles-outline' : 'chatbubble-ellipses-outline'}
                    size={15}
                    color={theme.primary}
                  />
                  <Text style={[styles.replyButtonText, { color: theme.primary }]}>
                    {message.threadInfo ? 'Open replies' : 'Reply in thread'}
                  </Text>
                </Pressable>
              </View>
            ) : null}
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  userContainer: {
    alignItems: 'flex-end',
  },
  assistantContainer: {
    alignItems: 'stretch',
  },
  bubbleBase: {},
  bubbleConstrained: {
    maxWidth: '85%',
  },
  userBubble: {
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomRightRadius: 4,
    overflow: 'hidden',
  },
  assistantBubble: {
    borderRadius: 0,
    paddingHorizontal: 0,
    paddingVertical: 0,
    backgroundColor: 'transparent',
  },
  userText: {
    fontSize: 16,
    lineHeight: 22,
  },
  assistantContent: {
    width: '100%',
    flexDirection: 'column',
    alignItems: 'stretch',
  },
  streamingCursorWithText: {
    marginTop: 8,
  },
  actionsRow: {
    marginTop: 10,
    flexDirection: 'row',
  },
  replyButton: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  replyButtonText: {
    fontSize: 14,
    fontWeight: '700',
  },
});
