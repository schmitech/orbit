import React, { useRef } from 'react';
import { Animated, StyleSheet, View, Text, Alert } from 'react-native';
import { RectButton } from 'react-native-gesture-handler';
import Swipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  children: React.ReactNode;
  onDelete: () => void;
}

export function SwipeableRow({ children, onDelete }: Props) {
  const swipeableRef = useRef<any>(null);

  const handleDelete = () => {
    Alert.alert(
      'Delete Conversation',
      'Are you sure you want to delete this conversation?',
      [
        { text: 'Cancel', style: 'cancel', onPress: () => swipeableRef.current?.close() },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => {
            swipeableRef.current?.close();
            onDelete();
          },
        },
      ]
    );
  };

  const renderRightActions = () => (
    <RectButton style={styles.deleteButton} onPress={handleDelete}>
      <Ionicons name="trash-outline" size={22} color="#FFFFFF" />
      <Text style={styles.deleteText}>Delete</Text>
    </RectButton>
  );

  return (
    <Swipeable
      ref={swipeableRef}
      renderRightActions={renderRightActions}
      overshootRight={false}
      friction={2}
    >
      {children}
    </Swipeable>
  );
}

const styles = StyleSheet.create({
  deleteButton: {
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
    width: 80,
    flexDirection: 'column',
  },
  deleteText: {
    color: '#FFFFFF',
    fontSize: 12,
    marginTop: 4,
  },
});
