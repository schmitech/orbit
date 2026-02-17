import React, { useEffect } from 'react';
import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useChatStore } from '../src/stores/chatStore';
import { useThemeStore } from '../src/stores/themeStore';
import { useTheme } from '../src/hooks/useTheme';

export default function RootLayout() {
  const router = useRouter();
  const hydrate = useChatStore((s) => s.hydrate);
  const hydrateTheme = useThemeStore((s) => s.hydrate);
  const { theme, isDark } = useTheme();

  useEffect(() => {
    hydrate();
    hydrateTheme();
  }, [hydrate, hydrateTheme]);

  return (
    <GestureHandlerRootView style={styles.root}>
      <StatusBar style={isDark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.headerBackground },
          headerTintColor: theme.text,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: theme.background },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="chat/[id]"
          options={{
            title: '',
            headerLeft: () => (
              <TouchableOpacity
                onPress={() => router.back()}
                hitSlop={8}
                activeOpacity={1}
                style={styles.backButton}
              >
                <Ionicons name="chevron-back" size={24} color={theme.text} />
              </TouchableOpacity>
            ),
          }}
        />
        <Stack.Screen
          name="chat/[id]/thread/[parentId]"
          options={{
            title: 'Replies',
            headerLeft: () => (
              <TouchableOpacity
                onPress={() => router.back()}
                hitSlop={8}
                activeOpacity={1}
                style={styles.backButton}
              >
                <Ionicons name="chevron-back" size={24} color={theme.text} />
              </TouchableOpacity>
            ),
          }}
        />
      </Stack>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  backButton: {
    paddingHorizontal: 4,
    paddingVertical: 2,
    backgroundColor: 'transparent',
  },
});
