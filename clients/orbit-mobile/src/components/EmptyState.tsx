import React from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../theme/colors';
import { MarkdownContent } from './MarkdownContent';
import { getConfig } from '../config/env';

interface Props {
  theme: ThemeColors;
  variant: 'chat' | 'conversations';
  onPress?: () => void;
  adapterNotes?: string | null;
}

export function EmptyState({ theme, variant, onPress, adapterNotes }: Props) {
  if (variant === 'chat') {
    return (
      <View style={styles.chatContainer}>
        {adapterNotes?.trim() ? (
          <ScrollView
            style={styles.notesScroll}
            contentContainerStyle={styles.notesScrollContent}
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.notesContainer}>
              <MarkdownContent
                content={adapterNotes}
                theme={theme}
                variant="notes"
                textColor={theme.text}
              />
            </View>
          </ScrollView>
        ) : null}
      </View>
    );
  }

  const { appTitle } = getConfig();
  return (
    <View style={styles.container}>
      <Text style={[styles.appTitle, { color: theme.text }]}>
        {appTitle}
      </Text>
      <Pressable
        style={({ pressed }) => [
          styles.newChatButton,
          { backgroundColor: theme.primary },
          pressed && styles.pressed,
        ]}
        onPress={onPress}
      >
        <Ionicons name="add" size={22} color="#FFFFFF" />
        <Text style={styles.newChatButtonText}>New Chat</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    paddingBottom: 96,
  },
  chatContainer: {
    flex: 1,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  notesScroll: {
    flex: 1,
  },
  notesScrollContent: {
    paddingBottom: 12,
  },
  pressed: {
    opacity: 0.8,
  },
  appTitle: {
    fontSize: 26,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 16,
  },
  newChatButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    paddingHorizontal: 28,
    borderRadius: 14,
    gap: 8,
  },
  newChatButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  notesContainer: {
    width: '100%',
    paddingHorizontal: 2,
    paddingVertical: 2,
  },
});
