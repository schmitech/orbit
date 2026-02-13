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
            styles.bubble,
            isUser
              ? [styles.userBubble, { backgroundColor: theme.userBubble }]
              : [
                  styles.assistantBubble,
                  { backgroundColor: theme.assistantBubble },
                ],
          ]}
        >
          {isUser ? (
            <Text style={[styles.userText, { color: theme.userBubbleText }]}>
              {message.content}
            </Text>
          ) : (
            <View style={styles.assistantContent}>
              {message.content ? (
                <MarkdownContent content={message.content} theme={theme} />
              ) : null}
              {message.isStreaming && !message.content && (
                <StreamingCursor color={theme.textTertiary} />
              )}
              {message.isStreaming && message.content ? (
                <StreamingCursor color={theme.primary} />
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
    paddingVertical: 4,
  },
  userContainer: {
    alignItems: 'flex-end',
  },
  assistantContainer: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '85%',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  userBubble: {
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    borderBottomLeftRadius: 4,
  },
  userText: {
    fontSize: 16,
    lineHeight: 22,
  },
  assistantContent: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'flex-end',
  },
});
