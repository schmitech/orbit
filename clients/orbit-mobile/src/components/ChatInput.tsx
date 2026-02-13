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
import { useVoice } from '../hooks/useVoice';

interface Props {
  onSend: (message: string) => void;
  onStop: () => void;
  isLoading: boolean;
  theme: ThemeColors;
  audioEnabled?: boolean;
  audioOutputSupported?: boolean;
  onToggleAudio?: () => void;
}

export function ChatInput({
  onSend,
  onStop,
  isLoading,
  theme,
  audioEnabled = false,
  audioOutputSupported = false,
  onToggleAudio,
}: Props) {
  const [text, setText] = useState('');
  const inputRef = useRef<TextInput>(null);
  const insets = useSafeAreaInsets();

  const handleTranscript = useCallback(
    (transcript: string) => {
      setText((prev) => {
        const combined = prev ? prev + ' ' + transcript : transcript;
        return combined.slice(0, MAX_MESSAGE_LENGTH);
      });
    },
    []
  );

  const { isListening, isSupported: voiceSupported, startListening, stopListening } = useVoice(handleTranscript);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setText('');
  }, [text, isLoading, onSend]);

  const handleStopPress = useCallback(() => {
    onStop();
  }, [onStop]);

  const handleMicPress = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

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
        {/* Audio output toggle */}
        {audioOutputSupported && (
          <Pressable
            onPress={onToggleAudio}
            style={[
              styles.iconButton,
              audioEnabled && { backgroundColor: theme.primary + '20' },
            ]}
            hitSlop={6}
          >
            <Ionicons
              name={audioEnabled ? 'volume-high' : 'volume-mute'}
              size={20}
              color={audioEnabled ? theme.primary : theme.textTertiary}
            />
          </Pressable>
        )}

        <TextInput
          ref={inputRef}
          style={[
            styles.input,
            { color: theme.text },
            audioOutputSupported && styles.inputWithLeftButton,
          ]}
          placeholder="Message..."
          placeholderTextColor={theme.textTertiary}
          value={text}
          onChangeText={(t) => setText(t.slice(0, MAX_MESSAGE_LENGTH))}
          multiline
          maxLength={MAX_MESSAGE_LENGTH}
          returnKeyType="default"
          blurOnSubmit={false}
        />

        {/* Mic button - show when not loading, no text, and voice is supported */}
        {voiceSupported && !isLoading && !text.trim() && (
          <Pressable
            onPress={handleMicPress}
            style={[
              styles.button,
              {
                backgroundColor: isListening
                  ? theme.destructive + '20'
                  : theme.surfaceSecondary,
              },
            ]}
            hitSlop={8}
          >
            <Ionicons
              name={isListening ? 'mic-off' : 'mic'}
              size={18}
              color={isListening ? theme.destructive : theme.textTertiary}
            />
          </Pressable>
        )}

        {/* Stop button during loading */}
        {isLoading && (
          <Pressable
            onPress={handleStopPress}
            style={[styles.button, { backgroundColor: theme.destructive }]}
            hitSlop={8}
          >
            <Ionicons name="stop" size={16} color="#FFFFFF" />
          </Pressable>
        )}

        {/* Send button when there's text and not loading */}
        {!isLoading && text.trim() ? (
          <Pressable
            onPress={handleSend}
            style={[styles.button, { backgroundColor: theme.primary }]}
            hitSlop={8}
          >
            <Ionicons name="arrow-up" size={18} color="#FFFFFF" />
          </Pressable>
        ) : null}
      </View>

      {/* Listening indicator */}
      {isListening && (
        <Text style={[styles.listeningText, { color: theme.destructive }]}>
          Listening...
        </Text>
      )}

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
  inputWithLeftButton: {
    marginLeft: 4,
  },
  iconButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
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
  listeningText: {
    fontSize: 12,
    textAlign: 'center',
    paddingTop: 4,
    fontWeight: '500',
  },
  charCount: {
    fontSize: 12,
    textAlign: 'right',
    paddingTop: 4,
    paddingRight: 4,
  },
});
