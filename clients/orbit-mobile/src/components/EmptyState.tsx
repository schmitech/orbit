import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../theme/colors';

interface Props {
  theme: ThemeColors;
  variant: 'chat' | 'conversations';
  onPress?: () => void;
}

export function EmptyState({ theme, variant, onPress }: Props) {
  if (variant === 'chat') {
    return (
      <View style={styles.container}>
        <View style={[styles.iconCircle, { backgroundColor: theme.primaryLight }]}>
          <Ionicons name="sparkles" size={32} color={theme.primary} />
        </View>
        <Text style={[styles.title, { color: theme.text }]}>
          How can I help you?
        </Text>
        <Text style={[styles.subtitle, { color: theme.textSecondary }]}>
          Send a message to start chatting
        </Text>
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
});
