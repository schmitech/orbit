import React from 'react';
import { View, StyleSheet } from 'react-native';
import ChatInterface from '@/components/ChatInterface';

export default function ChatScreen() {
  return (
    <View style={styles.container}>
      <ChatInterface />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
});