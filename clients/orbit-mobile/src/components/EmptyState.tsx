import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { ThemeColors } from '../theme/colors';
import { MarkdownContent } from './MarkdownContent';
import { getConfig } from '../config/env';

interface Props {
  theme: ThemeColors;
  variant: 'chat' | 'conversations';
  adapterNotes?: string | null;
}

export function EmptyState({ theme, variant, adapterNotes }: Props) {
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
      <Text style={[styles.helperText, { color: theme.textSecondary }]}>
        Tap + to start a new chat.
      </Text>
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
  appTitle: {
    fontSize: 26,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 10,
  },
  helperText: {
    fontSize: 14,
    textAlign: 'center',
  },
  notesContainer: {
    width: '100%',
    paddingHorizontal: 2,
    paddingVertical: 2,
  },
});
