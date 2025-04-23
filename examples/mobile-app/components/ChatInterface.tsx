import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Send, Mic } from 'lucide-react-native';
import { TouchableOpacity } from 'react-native-gesture-handler';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { useChatStore } from '@/stores/chat';
import { useQuery, useMutation } from '@tanstack/react-query';
import { format } from 'date-fns';

const AnimatedTouchableOpacity = Animated.createAnimatedComponent(TouchableOpacity);

const SUGGESTED_QUERIES = [
  "Where can I find the cheapest apples?",
  "Compare milk prices",
  "Best deals on bread today",
];

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
}

// Mock responses for demonstration
const MOCK_RESPONSES: { [key: string]: string } = {
  "Where can I find the cheapest apples?": "Based on current prices:\n\n🏪 Walmart: $1.99/lb\n🏪 Target: $2.49/lb\n🏪 Whole Foods: $2.99/lb\n\nBest deal: Walmart has the cheapest apples today!",
  "Compare milk prices": "Here's today's milk price comparison:\n\n🥛 Costco: $3.49/gallon\n🥛 Kroger: $3.99/gallon\n🥛 Safeway: $4.29/gallon\n\nTip: Costco has the best value, especially if buying in bulk!",
  "Best deals on bread today": "Today's bread prices:\n\n🍞 Aldi: $1.99/loaf\n🍞 Trader Joe's: $2.49/loaf\n🍞 Safeway: $2.99/loaf\n\nSpecial deal: Aldi has a buy-one-get-one-free promotion today!",
};

async function sendMessage(text: string): Promise<{ response: string }> {
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  // Check for exact matches in mock responses
  if (MOCK_RESPONSES[text]) {
    return { response: MOCK_RESPONSES[text] };
  }
  
  // Default response for unknown queries
  return {
    response: "I found these general grocery deals:\n\n🛒 Walmart: 20% off fresh produce\n🛒 Target: $5 off $50 grocery purchase\n🛒 Kroger: Buy 2, get 1 free on select items\n\nFor more specific prices, try asking about particular items!"
  };
}

export default function ChatInterface() {
  const [inputText, setInputText] = useState('');
  const flatListRef = useRef<FlatList>(null);
  const { messages, addMessage } = useChatStore();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const { mutate: sendMessageMutation, isPending } = useMutation({
    mutationFn: sendMessage,
    onSuccess: (data) => {
      addMessage({
        id: Date.now().toString(),
        text: data.response,
        sender: 'bot',
        timestamp: new Date(),
      });
      flatListRef.current?.scrollToEnd();
    },
    onError: (error) => {
      addMessage({
        id: Date.now().toString(),
        text: "Sorry, I couldn't process your request. Please try again.",
        sender: 'bot',
        timestamp: new Date(),
      });
    },
  });

  const handleSend = () => {
    if (!inputText.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputText.trim(),
      sender: 'user',
      timestamp: new Date(),
    };

    addMessage(userMessage);
    sendMessageMutation(inputText.trim());
    setInputText('');
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    // Simulate refresh delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    setIsRefreshing(false);
  };

  const renderMessage = ({ item }: { item: Message }) => (
    <Animated.View
      entering={FadeIn}
      style={[
        styles.messageContainer,
        item.sender === 'user' ? styles.userMessage : styles.botMessage,
      ]}
    >
      <Text style={[
        styles.messageText,
        item.sender === 'bot' && styles.botMessageText
      ]}>{item.text}</Text>
      <Text style={[
        styles.timestamp,
        item.sender === 'bot' && styles.botTimestamp
      ]}>
        {format(item.timestamp, 'HH:mm')}
      </Text>
    </Animated.View>
  );

  const renderWelcomeMessage = () => (
    <View style={styles.welcomeContainer}>
      <Text style={styles.welcomeTitle}>Welcome to GroceryBot! 🛒</Text>
      <Text style={styles.welcomeText}>
        I can help you find the best grocery deals. Try asking me about specific items
        or compare prices across stores.
      </Text>
      <Text style={styles.suggestedTitle}>Try asking:</Text>
      {SUGGESTED_QUERIES.map((query, index) => (
        <TouchableOpacity
          key={index}
          style={styles.suggestionButton}
          onPress={() => {
            setInputText(query);
          }}
        >
          <Text style={styles.suggestionText}>{query}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.container}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderMessage}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.messageList}
          ListEmptyComponent={renderWelcomeMessage}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
              tintColor="#007AFF"
            />
          }
        />
        <View style={styles.inputContainer}>
          <TextInput
            style={styles.input}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Type your message..."
            placeholderTextColor="#8E8E93"
            multiline
            maxLength={500}
          />
          <AnimatedTouchableOpacity
            style={styles.sendButton}
            onPress={handleSend}
            disabled={isPending || !inputText.trim()}
          >
            {isPending ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Send size={20} color="#FFFFFF" />
            )}
          </AnimatedTouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  messageList: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  messageContainer: {
    maxWidth: '80%',
    padding: 12,
    borderRadius: 16,
    marginBottom: 8,
  },
  userMessage: {
    backgroundColor: '#007AFF',
    alignSelf: 'flex-end',
  },
  botMessage: {
    backgroundColor: '#FFFFFF',
    alignSelf: 'flex-start',
  },
  messageText: {
    fontSize: 16,
    fontFamily: 'Inter_400Regular',
    color: '#FFFFFF',
  },
  botMessageText: {
    color: '#000000',
  },
  timestamp: {
    fontSize: 12,
    color: 'rgba(255, 255, 255, 0.7)',
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  botTimestamp: {
    color: 'rgba(0, 0, 0, 0.5)',
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#E5E5EA',
  },
  input: {
    flex: 1,
    marginRight: 8,
    padding: 12,
    backgroundColor: '#F2F2F7',
    borderRadius: 20,
    fontSize: 16,
    fontFamily: 'Inter_400Regular',
    maxHeight: 100,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  welcomeContainer: {
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    marginBottom: 16,
  },
  welcomeTitle: {
    fontSize: 24,
    fontFamily: 'Inter_700Bold',
    marginBottom: 8,
    color: '#000000',
  },
  welcomeText: {
    fontSize: 16,
    fontFamily: 'Inter_400Regular',
    color: '#3A3A3C',
    marginBottom: 16,
  },
  suggestedTitle: {
    fontSize: 18,
    fontFamily: 'Inter_600SemiBold',
    color: '#000000',
    marginBottom: 8,
  },
  suggestionButton: {
    backgroundColor: '#F2F2F7',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
  },
  suggestionText: {
    fontSize: 16,
    fontFamily: 'Inter_400Regular',
    color: '#007AFF',
  },
});