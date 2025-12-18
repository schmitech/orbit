import { MessageSquare, Heart, MessageCircle, HelpCircle, Info, Bot, Sparkles } from 'lucide-react';
import type { IconConfig } from '../types/widget.types';

export const icons: IconConfig[] = [
  { id: 'message-square', name: 'Message Square', icon: MessageSquare },
  { id: 'heart', name: 'Heart', icon: Heart },
  { id: 'message-circle', name: 'Message Circle', icon: MessageCircle },
  { id: 'help-circle', name: 'Help Circle', icon: HelpCircle },
  { id: 'info', name: 'Info', icon: Info },
  { id: 'bot', name: 'Bot', icon: Bot },
  { id: 'sparkles', name: 'Sparkles', icon: Sparkles }
];