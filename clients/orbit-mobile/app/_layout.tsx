import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet } from 'react-native';
import { useChatStore } from '../src/stores/chatStore';
import { useThemeStore } from '../src/stores/themeStore';
import { useTheme } from '../src/hooks/useTheme';

export default function RootLayout() {
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
            headerBackTitle: 'Back',
          }}
        />
        <Stack.Screen
          name="chat/[id]/thread/[parentId]"
          options={{
            title: 'Replies',
            headerBackTitle: 'Chat',
          }}
        />
      </Stack>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
