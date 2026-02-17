import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Modal,
  Animated,
  ActivityIndicator,
} from 'react-native';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import { useChatStore } from '../../src/stores/chatStore';
import { useTheme } from '../../src/hooks/useTheme';

type ThemeMode = 'light' | 'dark' | 'system';

export default function SettingsScreen() {
  const clearAllConversations = useChatStore((s) => s.clearAllConversations);
  const validateConnection = useChatStore((s) => s.validateConnection);
  const conversations = useChatStore((s) => s.conversations);
  const { theme, isDark, mode, setThemeMode } = useTheme();

  const [connectionStatus, setConnectionStatus] = useState<
    'checking' | 'connected' | 'error'
  >('checking');

  useEffect(() => {
    checkConnection();
  }, []);

  const checkConnection = useCallback(async () => {
    setConnectionStatus('checking');
    const valid = await validateConnection();
    setConnectionStatus(valid ? 'connected' : 'error');
  }, [validateConnection]);

  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const toastOpacity = useRef(new Animated.Value(0)).current;
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToastMessage(message);
    Animated.timing(toastOpacity, { toValue: 1, duration: 200, useNativeDriver: true }).start();
    toastTimer.current = setTimeout(() => {
      Animated.timing(toastOpacity, { toValue: 0, duration: 400, useNativeDriver: true }).start();
    }, 2000);
  }, [toastOpacity]);

  const handleClearAll = useCallback(() => {
    if (conversations.length === 0) return;
    setShowClearConfirm(true);
  }, [conversations.length]);

  const handleClearCancel = useCallback(() => {
    setShowClearConfirm(false);
  }, []);

  const handleClearConfirm = useCallback(() => {
    const count = conversations.length;
    setShowClearConfirm(false);
    clearAllConversations();
    showToast(`${count} conversation${count !== 1 ? 's' : ''} deleted`);
  }, [conversations.length, clearAllConversations, showToast]);

  const handleThemeSelect = useCallback(
    (newMode: ThemeMode) => {
      setThemeMode(newMode);
    },
    [setThemeMode]
  );

  const version = Constants.expoConfig?.version || '1.0.0';

  return (
    <>
    <ScrollView
      style={[styles.container, { backgroundColor: theme.background }]}
      contentContainerStyle={styles.content}
    >
      {/* Connection Status */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.textSecondary }]}>
          CONNECTION
        </Text>
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.border }]}>
          <Pressable style={styles.row} onPress={checkConnection}>
            <View style={styles.rowLeft}>
              {connectionStatus === 'checking' ? (
                <ActivityIndicator size="small" color={theme.primary} />
              ) : (
                <View
                  style={[
                    styles.statusDot,
                    {
                      backgroundColor:
                        connectionStatus === 'connected'
                          ? theme.success
                          : theme.error,
                    },
                  ]}
                />
              )}
              <Text style={[styles.rowLabel, { color: theme.text }]}>
                Server Status
              </Text>
            </View>
            <Text style={[styles.rowValue, { color: theme.textSecondary }]}>
              {connectionStatus === 'checking'
                ? 'Checking...'
                : connectionStatus === 'connected'
                ? 'Connected'
                : 'Disconnected'}
            </Text>
          </Pressable>

        </View>
      </View>

      {/* Theme */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.textSecondary }]}>
          APPEARANCE
        </Text>
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.border }]}>
          {(['system', 'light', 'dark'] as ThemeMode[]).map((themeMode, index) => (
            <React.Fragment key={themeMode}>
              {index > 0 && (
                <View style={[styles.divider, { backgroundColor: theme.border }]} />
              )}
              <Pressable
                style={styles.row}
                onPress={() => handleThemeSelect(themeMode)}
              >
                <View style={styles.rowLeft}>
                  <Ionicons
                    name={
                      themeMode === 'system'
                        ? 'phone-portrait-outline'
                        : themeMode === 'light'
                        ? 'sunny-outline'
                        : 'moon-outline'
                    }
                    size={20}
                    color={theme.text}
                    style={styles.rowIcon}
                  />
                  <Text style={[styles.rowLabel, { color: theme.text }]}>
                    {themeMode.charAt(0).toUpperCase() + themeMode.slice(1)}
                  </Text>
                </View>
                {mode === themeMode && (
                  <Ionicons name="checkmark" size={20} color={theme.primary} />
                )}
              </Pressable>
            </React.Fragment>
          ))}
        </View>
      </View>

      {/* Data */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.textSecondary }]}>
          DATA
        </Text>
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.border }]}>
          <View style={styles.row}>
            <Text style={[styles.rowLabel, { color: theme.text }]}>
              Conversations
            </Text>
            <Text style={[styles.rowValue, { color: theme.textSecondary }]}>
              {conversations.length}
            </Text>
          </View>
          <View style={[styles.divider, { backgroundColor: theme.border }]} />
          <Pressable
            style={styles.row}
            onPress={handleClearAll}
            disabled={conversations.length === 0}
          >
            <Text style={[styles.rowLabel, { color: conversations.length === 0 ? theme.textTertiary : theme.destructive }]}>
              Clear All Conversations
            </Text>
          </Pressable>
        </View>
      </View>

      {/* About */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: theme.textSecondary }]}>
          ABOUT
        </Text>
        <View style={[styles.card, { backgroundColor: theme.card, borderColor: theme.border }]}>
          <View style={styles.row}>
            <Text style={[styles.rowLabel, { color: theme.text }]}>
              Version
            </Text>
            <Text style={[styles.rowValue, { color: theme.textSecondary }]}>
              {version}
            </Text>
          </View>
        </View>
      </View>
    </ScrollView>
    <Modal
      visible={showClearConfirm}
      transparent
      animationType="fade"
      onRequestClose={handleClearCancel}
    >
      <Pressable style={styles.overlay} onPress={handleClearCancel}>
        <View
          style={[styles.dialog, { backgroundColor: theme.card, borderColor: theme.border }]}
          onStartShouldSetResponder={() => true}
        >
          <Text style={[styles.dialogTitle, { color: theme.text }]}>
            Clear All Conversations
          </Text>
          <Text style={[styles.dialogMessage, { color: theme.textSecondary }]}>
            Are you sure you want to delete all {conversations.length} conversations? This cannot be undone.
          </Text>
          <View style={[styles.dialogActions, { borderTopColor: theme.border }]}>
            <Pressable
              style={({ pressed }) => [
                styles.dialogButton,
                { borderRightColor: theme.border, borderRightWidth: StyleSheet.hairlineWidth },
                pressed && { backgroundColor: theme.surface },
              ]}
              onPress={handleClearCancel}
            >
              <Text style={[styles.dialogButtonText, { color: theme.primary }]}>Cancel</Text>
            </Pressable>
            <Pressable
              style={({ pressed }) => [
                styles.dialogButton,
                pressed && { backgroundColor: theme.surface },
              ]}
              onPress={handleClearConfirm}
            >
              <Text style={[styles.dialogButtonText, styles.dialogDeleteText]}>Delete All</Text>
            </Pressable>
          </View>
        </View>
      </Pressable>
    </Modal>
    {toastMessage ? (
      <Animated.View
        style={[styles.toast, { backgroundColor: theme.surface, borderColor: theme.border, opacity: toastOpacity }]}
        pointerEvents="none"
      >
        <Ionicons name="checkmark-circle" size={18} color={theme.success} />
        <Text style={[styles.toastText, { color: theme.text }]}>{toastMessage}</Text>
      </Animated.View>
    ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingVertical: 20,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    letterSpacing: 0.5,
    paddingHorizontal: 20,
    marginBottom: 8,
  },
  card: {
    marginHorizontal: 16,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    minHeight: 48,
  },
  rowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  rowIcon: {
    marginRight: 12,
  },
  rowLabel: {
    fontSize: 16,
  },
  rowValue: {
    fontSize: 15,
    maxWidth: '60%',
    textAlign: 'right',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 12,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 16,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
  },
  dialog: {
    width: '100%',
    maxWidth: 300,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  dialogTitle: {
    fontSize: 17,
    fontWeight: '600',
    textAlign: 'center',
    paddingTop: 20,
    paddingHorizontal: 20,
  },
  dialogMessage: {
    fontSize: 13,
    textAlign: 'center',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 20,
    lineHeight: 18,
  },
  dialogActions: {
    flexDirection: 'row',
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  dialogButton: {
    flex: 1,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dialogButtonText: {
    fontSize: 17,
  },
  dialogDeleteText: {
    fontWeight: '600',
    color: '#FF3B30',
  },
  toast: {
    position: 'absolute',
    bottom: 48,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
  },
  toastText: {
    fontSize: 14,
    fontWeight: '500',
  },
});
