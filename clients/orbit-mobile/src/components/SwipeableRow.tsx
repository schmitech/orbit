import React, { useCallback, useRef, useState } from 'react';
import { StyleSheet, View, Text, Modal, Pressable } from 'react-native';
import { RectButton } from 'react-native-gesture-handler';
import Swipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../hooks/useTheme';

interface Props {
  children: React.ReactNode;
  onDelete: () => void;
}

export function SwipeableRow({ children, onDelete }: Props) {
  const swipeableRef = useRef<any>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const { theme } = useTheme();

  const handleDelete = useCallback(() => {
    setShowConfirm(true);
  }, []);

  const handleCancel = useCallback(() => {
    setShowConfirm(false);
    swipeableRef.current?.close();
  }, []);

  const handleConfirm = useCallback(() => {
    setShowConfirm(false);
    swipeableRef.current?.close();
    onDelete();
  }, [onDelete]);

  const renderRightActions = () => (
    <RectButton style={styles.deleteButton} onPress={handleDelete}>
      <Ionicons name="trash-outline" size={22} color="#FFFFFF" />
      <Text style={styles.deleteText}>Delete</Text>
    </RectButton>
  );

  return (
    <>
      <Swipeable
        ref={swipeableRef}
        renderRightActions={renderRightActions}
        overshootRight={false}
        friction={2}
      >
        {children}
      </Swipeable>
      <Modal
        visible={showConfirm}
        transparent
        animationType="fade"
        onRequestClose={handleCancel}
      >
        <Pressable style={styles.overlay} onPress={handleCancel}>
          <View
            style={[styles.dialog, { backgroundColor: theme.card, borderColor: theme.border }]}
            onStartShouldSetResponder={() => true}
          >
            <Text style={[styles.dialogTitle, { color: theme.text }]}>
              Delete Conversation
            </Text>
            <Text style={[styles.dialogMessage, { color: theme.textSecondary }]}>
              Are you sure you want to delete this conversation?
            </Text>
            <View style={[styles.dialogActions, { borderTopColor: theme.border }]}>
              <Pressable
                style={({ pressed }) => [
                  styles.dialogButton,
                  { borderRightColor: theme.border, borderRightWidth: StyleSheet.hairlineWidth },
                  pressed && { backgroundColor: theme.surface },
                ]}
                onPress={handleCancel}
              >
                <Text style={[styles.cancelText, { color: theme.primary }]}>Cancel</Text>
              </Pressable>
              <Pressable
                style={({ pressed }) => [
                  styles.dialogButton,
                  pressed && { backgroundColor: theme.surface },
                ]}
                onPress={handleConfirm}
              >
                <Text style={styles.confirmDeleteText}>Delete</Text>
              </Pressable>
            </View>
          </View>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  deleteButton: {
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
    width: 80,
    flexDirection: 'column',
    marginVertical: 6,
    marginRight: 12,
    borderRadius: 14,
  },
  deleteText: {
    color: '#FFFFFF',
    fontSize: 12,
    marginTop: 4,
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
  cancelText: {
    fontSize: 17,
    fontWeight: '400',
  },
  confirmDeleteText: {
    fontSize: 17,
    fontWeight: '600',
    color: '#FF3B30',
  },
});
