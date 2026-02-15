import React, { useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Alert } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Message } from '../types';
import { ThemeColors } from '../theme/colors';
import { MarkdownContent } from './MarkdownContent';
import { StreamingCursor } from './StreamingCursor';

interface Props {
  message: Message;
  theme: ThemeColors;
}

export function ChatBubble({ message, theme }: Props) {
  const isUser = message.role === 'user';

  const handleLongPress = useCallback(() => {
    if (!isUser && message.content) {
      Clipboard.setStringAsync(message.content);
      Alert.alert('Copied', 'Message copied to clipboard');
    }
  }, [isUser, message.content]);

  return (
    <Pressable onLongPress={handleLongPress} delayLongPress={500}>
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
            <View style={styles.assistantContent}>
              {message.content
                ? message.isStreaming
                  ? (
                    <Text style={[styles.assistantStreamingText, { color: theme.assistantBubbleText }]}>
                      {message.content}
                    </Text>
                  )
                  : (
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
          )}
        </View>
      </View>
    </Pressable>
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
    alignItems: 'flex-start',
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
  assistantStreamingText: {
    fontSize: 16,
    lineHeight: 22,
  },
  streamingCursorWithText: {
    marginTop: 8,
  },
});
