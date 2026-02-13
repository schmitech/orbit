import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  TextInput,
  Text,
  Pressable,
  StyleSheet,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../theme/colors';
import { MAX_MESSAGE_LENGTH } from '../config/constants';

interface Props {
  onSend: (message: string) => void;
  onStop: () => void;
  isLoading: boolean;
  theme: ThemeColors;
}

export function ChatInput({ onSend, onStop, isLoading, theme }: Props) {
  const [text, setText] = useState('');
  const inputRef = useRef<TextInput>(null);
  const insets = useSafeAreaInsets();

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setText('');
  }, [text, isLoading, onSend]);

  const handleStopPress = useCallback(() => {
    onStop();
  }, [onStop]);

  const atLimit = text.length >= MAX_MESSAGE_LENGTH;

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: theme.headerBackground,
          borderTopColor: theme.border,
          paddingBottom: Math.max(insets.bottom, 8),
        },
      ]}
    >
      <View style={[styles.inputWrapper, { backgroundColor: theme.inputBackground }]}>
        <TextInput
          ref={inputRef}
          style={[styles.input, { color: theme.text }]}
          placeholder="Message..."
          placeholderTextColor={theme.textTertiary}
          value={text}
          onChangeText={(t) => setText(t.slice(0, MAX_MESSAGE_LENGTH))}
          multiline
          maxLength={MAX_MESSAGE_LENGTH}
          returnKeyType="default"
          blurOnSubmit={false}
        />
        {isLoading ? (
          <Pressable
            onPress={handleStopPress}
            style={[styles.button, { backgroundColor: theme.destructive }]}
            hitSlop={8}
          >
            <Ionicons name="stop" size={16} color="#FFFFFF" />
          </Pressable>
        ) : (
          <Pressable
            onPress={handleSend}
            style={[
              styles.button,
              {
                backgroundColor: text.trim()
                  ? theme.primary
                  : theme.surfaceSecondary,
              },
            ]}
            disabled={!text.trim()}
            hitSlop={8}
          >
            <Ionicons
              name="arrow-up"
              size={18}
              color={text.trim() ? '#FFFFFF' : theme.textTertiary}
            />
          </Pressable>
        )}
      </View>
      {text.length > 0 && (
        <Text style={[styles.charCount, { color: atLimit ? theme.error : theme.textTertiary }]}>
          {text.length}/{MAX_MESSAGE_LENGTH}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    borderRadius: 22,
    paddingHorizontal: 14,
    paddingVertical: 6,
    minHeight: 44,
  },
  input: {
    flex: 1,
    fontSize: 16,
    lineHeight: 22,
    maxHeight: 120,
    paddingTop: Platform.OS === 'ios' ? 8 : 6,
    paddingBottom: Platform.OS === 'ios' ? 8 : 6,
  },
  button: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
    marginBottom: 2,
  },
  charCount: {
    fontSize: 12,
    textAlign: 'right',
    paddingTop: 4,
    paddingRight: 4,
  },
});
