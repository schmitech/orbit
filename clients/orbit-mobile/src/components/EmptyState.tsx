import React from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../theme/colors';
import { MarkdownContent } from './MarkdownContent';

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
            <View style={[styles.notesContainer, { borderColor: theme.border, backgroundColor: theme.card }]}>
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

  return (
    <Pressable
      style={({ pressed }) => [
        styles.container,
        pressed && styles.pressed,
      ]}
      onPress={onPress}
    >
      <View style={[styles.iconCircle, { backgroundColor: theme.primaryLight }]}>
        <Ionicons name="add" size={36} color={theme.primary} />
      </View>
      <Text style={[styles.title, { color: theme.text }]}>
        Start a new chat
      </Text>
      <Text style={[styles.subtitle, { color: theme.textSecondary }]}>
        Tap here to begin a conversation
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
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
    opacity: 0.6,
  },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 15,
    textAlign: 'center',
    lineHeight: 22,
  },
  notesContainer: {
    width: '100%',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
});
