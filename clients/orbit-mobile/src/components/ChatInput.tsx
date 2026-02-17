import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  TextInput,
  Text,
  Pressable,
  StyleSheet,
  Platform,
  NativeSyntheticEvent,
  TextInputKeyPressEventData,
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
  autoFocus?: boolean;
  placeholder?: string;
  audioEnabled?: boolean;
  audioOutputSupported?: boolean;
  onToggleAudio?: () => void;
}

export function ChatInput({
  onSend,
  onStop,
  isLoading,
  theme,
  autoFocus = false,
  placeholder = 'Ask me anything...',
  audioEnabled = false,
  audioOutputSupported = false,
  onToggleAudio,
}: Props) {
  const [text, setText] = useState('');
  const [isMultiline, setIsMultiline] = useState(false);
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

  const handleKeyPress = useCallback(
    (e: NativeSyntheticEvent<TextInputKeyPressEventData>) => {
      if (Platform.OS === 'web' && e.nativeEvent.key === 'Enter' && !(e as any).shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleContentSizeChange = useCallback(
    (e: any) => {
      const height = e.nativeEvent.contentSize.height;
      setIsMultiline(height > 30);
    },
    []
  );

  const atLimit = text.length >= MAX_MESSAGE_LENGTH;

  return (
    <View
      style={[
        styles.container,
        {
          paddingBottom: Math.max(insets.bottom, 8),
        },
      ]}
    >
      <View style={[styles.inputWrapper, { backgroundColor: theme.inputBackground, borderColor: theme.border }]}>
        {/* Character count - shown when input expands to multiple lines */}
        {isMultiline && text.length > 0 && (
          <Text
            style={[
              styles.charCount,
              { color: atLimit ? theme.error : theme.textSecondary },
            ]}
          >
            {text.length}/{MAX_MESSAGE_LENGTH}
          </Text>
        )}

        {/* Audio output toggle */}
        {audioOutputSupported && (
          <Pressable
            onPress={onToggleAudio}
            style={[
              styles.button,
              { marginRight: 4 },
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
          placeholder={placeholder}
          placeholderTextColor={theme.textTertiary}
          value={text}
          onChangeText={(t) => setText(t.slice(0, MAX_MESSAGE_LENGTH))}
          multiline
          maxLength={MAX_MESSAGE_LENGTH}
          returnKeyType="send"
          blurOnSubmit={false}
          onSubmitEditing={handleSend}
          onKeyPress={handleKeyPress}
          onContentSizeChange={handleContentSizeChange}
          autoFocus={autoFocus}
        />

        {/* Mic button - keep visible for consistent UX, disable when unsupported */}
        {!isLoading && !text.trim() && (
          <Pressable
            onPress={voiceSupported ? handleMicPress : undefined}
            style={[
              styles.button,
              {
                marginLeft: 8,
                backgroundColor: isListening
                  ? theme.destructive + '20'
                  : theme.surfaceSecondary,
                opacity: voiceSupported ? 1 : 0.45,
              },
            ]}
            disabled={!voiceSupported}
            hitSlop={8}
          >
            <Ionicons
              name={
                !voiceSupported
                  ? 'mic-off-outline'
                  : isListening
                    ? 'mic-off'
                    : 'mic'
              }
              size={18}
              color={isListening ? theme.destructive : theme.textSecondary}
            />
          </Pressable>
        )}

        {/* Stop button during loading */}
        {isLoading && (
          <Pressable
            onPress={handleStopPress}
            style={[styles.button, { marginLeft: 8, backgroundColor: theme.destructive }]}
            hitSlop={8}
          >
            <Ionicons name="stop" size={16} color="#FFFFFF" />
          </Pressable>
        )}

        {/* Send button when there's text and not loading */}
        {!isLoading && text.trim() ? (
          <Pressable
            onPress={handleSend}
            style={[styles.button, { marginLeft: 8, backgroundColor: theme.primary }]}
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

    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 24,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 14,
    paddingVertical: 6,
    minHeight: 48,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 3,
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
  button: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
  listeningText: {
    fontSize: 12,
    textAlign: 'center',
    paddingTop: 4,
    fontWeight: '500',
  },
  charCount: {
    position: 'absolute',
    top: -18,
    right: 14,
    fontSize: 10,
    opacity: 0.7,
  },
});
