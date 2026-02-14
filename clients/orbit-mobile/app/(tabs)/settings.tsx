import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Alert,
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

  const handleClearAll = useCallback(() => {
    Alert.alert(
      'Clear All Conversations',
      `Are you sure you want to delete all ${conversations.length} conversations? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete All',
          style: 'destructive',
          onPress: clearAllConversations,
        },
      ]
    );
  }, [conversations.length, clearAllConversations]);

  const handleThemeSelect = useCallback(
    (newMode: ThemeMode) => {
      setThemeMode(newMode);
    },
    [setThemeMode]
  );

  const version = Constants.expoConfig?.version || '1.0.0';

  return (
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
          <Pressable style={styles.row} onPress={handleClearAll}>
            <Text style={[styles.rowLabel, { color: theme.destructive }]}>
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
});
